from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from ai_usage.paths import build_linked_env, build_profile_env, default_app_dir
from ai_usage.providers import get_adapter
from ai_usage.setup import run_setup
from ai_usage.wake import CliWaker
from ai_usage.store import Store

PROVIDERS = ["claude", "codex"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-usage")
    parser.add_argument("--root", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser("profile")
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command", required=True)

    add_parser = profile_subparsers.add_parser("add", help="create an isolated profile (needs its own login)")
    add_parser.add_argument("provider", choices=PROVIDERS)
    add_parser.add_argument("name")
    add_parser.add_argument("--label", default=None)

    link_parser = profile_subparsers.add_parser(
        "link", help="read usage from an existing CLI config dir (e.g. ~/.claude-work, ~/.codex)"
    )
    link_parser.add_argument("provider", choices=PROVIDERS)
    link_parser.add_argument("name")
    link_parser.add_argument("config_dir", type=Path)
    link_parser.add_argument("--label", default=None)

    remove_parser = profile_subparsers.add_parser("remove")
    remove_parser.add_argument("profile_id")

    profile_subparsers.add_parser("list")

    login_parser = profile_subparsers.add_parser("login")
    login_parser.add_argument("provider", choices=PROVIDERS)
    login_parser.add_argument("name")

    setup_parser = subparsers.add_parser(
        "setup", help="link detected ~/.claude* and ~/.codex dirs, enable the probe timer and GNOME extension"
    )
    setup_parser.add_argument("--interval", default="5min", help="probe interval (systemd time span)")
    setup_parser.add_argument("--no-system", action="store_true", help="only link profiles")

    probe_parser = subparsers.add_parser("probe")
    probe_parser.add_argument(
        "--no-wake", action="store_true", help="do not run the CLIs to refresh expired tokens"
    )

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--json", action="store_true")

    return parser


def probe(store: Store, wake: bool = True) -> int:
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    previous = store.load_status_entries()
    profiles = store.load_profiles()
    waker = CliWaker(store.paths.root / "wake", store.load_tools()) if wake else None

    def run(profile):
        config_dir = store.paths.provider_config_dir(profile)
        entry = get_adapter(profile.provider).probe(profile, config_dir, now_iso, wake=waker)
        return store.keep_last_known(entry, previous.get(profile.id))

    with ThreadPoolExecutor(max_workers=max(1, len(profiles))) as pool:
        entries = list(pool.map(run, profiles))
    store.write_status(entries, updated_at=now_iso)
    for entry in entries:
        if entry.error:
            print(f"{entry.id}: {entry.state} ({entry.error.code}) {entry.error.message}", file=sys.stderr)
    return 0


def print_status(store: Store, as_json: bool) -> int:
    status_path = store.paths.status_path
    if as_json:
        print(status_path.read_text() if status_path.exists() else '{"updated_at": null, "profiles": []}')
        return 0
    for entry in store.load_status_entries().values():
        windows = ", ".join(f"{item.label or item.window} {item.used_percent}%" for item in entry.usage) or "-"
        print(f"{entry.id:<20} {entry.state:<6} {entry.account or '-':<32} {windows}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root or default_app_dir()
    store = Store(root)

    if args.command == "profile" and args.profile_command == "add":
        store.add_profile(args.provider, args.name, args.label)
        return 0

    if args.command == "profile" and args.profile_command == "link":
        if not args.config_dir.expanduser().is_dir():
            print(f"Not a directory: {args.config_dir}", file=sys.stderr)
            return 1
        store.link_profile(args.provider, args.name, args.config_dir, args.label)
        return 0

    if args.command == "profile" and args.profile_command == "remove":
        if not store.remove_profile(args.profile_id):
            print(f"No such profile: {args.profile_id}", file=sys.stderr)
            return 1
        return 0

    if args.command == "profile" and args.profile_command == "list":
        for profile in store.load_profiles():
            print(f"{profile.id:<20} {profile.label:<20} {profile.config_dir or '(isolated)'}")
        return 0

    if args.command == "profile" and args.profile_command == "login":
        profile_id = f"{args.provider}-{args.name}"
        adapter = get_adapter(args.provider)
        linked = next((item for item in store.load_profiles() if item.id == profile_id and item.config_dir), None)
        if linked:
            config_dir = Path(linked.config_dir)
            env = build_linked_env(args.provider, config_dir)
            return subprocess.call(adapter.login_command, cwd=config_dir, env=env)
        profile_home = store.paths.profile_home(profile_id)
        profile_home.mkdir(parents=True, exist_ok=True)
        profile_home.chmod(0o700)
        return subprocess.call(adapter.login_command, cwd=profile_home, env=build_profile_env(profile_home))

    if args.command == "setup":
        return run_setup(store, args.root, args.interval, with_system=not args.no_system)

    if args.command == "probe":
        return probe(store, wake=not args.no_wake)

    if args.command == "status":
        return print_status(store, args.json)

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

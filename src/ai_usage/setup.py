from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ai_usage.store import Store

EXTENSION_UUID = "ai-usage@marekbartczak.github.io"
SERVICE_NAME = "ai-usage-probe.service"
TIMER_NAME = "ai-usage-probe.timer"


@dataclass(frozen=True)
class Candidate:
    provider: str
    name: str
    label: str
    config_dir: Path
    account_key: str | None


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _claude_account(config_dir: Path) -> dict:
    for path in (config_dir / ".claude.json", config_dir.parent / ".claude.json"):
        account = _read_json(path).get("oauthAccount")
        if isinstance(account, dict):
            return account
    return {}


def _dir_suffix(config_dir: Path, base: str) -> str:
    name = config_dir.name.lstrip(".")
    if name == base:
        return "default"
    return name.removeprefix(f"{base}-") or "default"


def detect_claude(home: Path, env: dict[str, str]) -> list[Candidate]:
    dirs = [Path(env["CLAUDE_CONFIG_DIR"])] if env.get("CLAUDE_CONFIG_DIR") else []
    dirs += [home / ".claude", *sorted(home.glob(".claude-*"))]
    found: list[Candidate] = []
    seen: set[Path] = set()
    for config_dir in dirs:
        config_dir = config_dir.expanduser().resolve()
        credentials = config_dir / ".credentials.json"
        if config_dir in seen or not credentials.is_file():
            continue
        if not isinstance(_read_json(credentials).get("claudeAiOauth"), dict):
            continue
        seen.add(config_dir)
        suffix = _dir_suffix(config_dir, "claude")
        account = _claude_account(config_dir)
        found.append(
            Candidate(
                provider="claude",
                name=suffix,
                label="Claude" if suffix == "default" else f"Claude {suffix.title()}",
                config_dir=config_dir,
                account_key=account.get("accountUuid") or account.get("emailAddress"),
            )
        )
    return _dedupe_accounts(found)


def detect_codex(home: Path, env: dict[str, str]) -> list[Candidate]:
    dirs = [Path(env["CODEX_HOME"])] if env.get("CODEX_HOME") else []
    dirs += [home / ".codex", *sorted(home.glob(".codex-*"))]
    found: list[Candidate] = []
    seen: set[Path] = set()
    for config_dir in dirs:
        config_dir = config_dir.expanduser().resolve()
        tokens = _read_json(config_dir / "auth.json").get("tokens")
        if config_dir in seen or not isinstance(tokens, dict):
            continue
        seen.add(config_dir)
        suffix = _dir_suffix(config_dir, "codex")
        found.append(
            Candidate(
                provider="codex",
                name=suffix,
                label="Codex" if suffix == "default" else f"Codex {suffix.title()}",
                config_dir=config_dir,
                account_key=tokens.get("account_id"),
            )
        )
    return found


def _dedupe_accounts(candidates: list[Candidate]) -> list[Candidate]:
    """Two config dirs logged into the same account show identical numbers; keep the freshest one."""
    best: dict[str, Candidate] = {}
    result: list[Candidate] = []
    for candidate in candidates:
        if candidate.account_key is None:
            result.append(candidate)
            continue
        current = best.get(candidate.account_key)
        if current is None or _mtime(candidate) > _mtime(current):
            best[candidate.account_key] = candidate
    result.extend(best.values())
    return sorted(result, key=lambda item: (item.name != "default", item.name))


def _mtime(candidate: Candidate) -> float:
    try:
        return (candidate.config_dir / ".credentials.json").stat().st_mtime
    except OSError:
        return 0.0


def link_detected(store: Store, home: Path, env: dict[str, str]) -> list[Candidate]:
    existing_dirs = {profile.config_dir for profile in store.load_profiles()}
    existing_ids = {profile.id for profile in store.load_profiles()}
    linked: list[Candidate] = []
    for candidate in detect_claude(home, env) + detect_codex(home, env):
        profile_id = f"{candidate.provider}-{candidate.name}"
        if str(candidate.config_dir) in existing_dirs or profile_id in existing_ids:
            continue
        store.link_profile(candidate.provider, candidate.name, candidate.config_dir, candidate.label)
        linked.append(candidate)
    return linked


def _probe_command(root: Path | None) -> str:
    executable = shutil.which("ai-usage")
    command = [executable] if executable else [sys.executable, "-m", "ai_usage.cli"]
    if root is not None:
        command += ["--root", str(root)]
    return shlex.join(command + ["probe"])


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, check=False)


def install_timer(root: Path | None, interval: str) -> str:
    if shutil.which("systemctl") is None:
        return "systemctl not found; run `ai-usage probe` periodically yourself"

    packaged = _systemctl("cat", SERVICE_NAME).returncode == 0 and root is None and interval == "5min"
    if not packaged:
        unit_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / SERVICE_NAME).write_text(
            "[Unit]\nDescription=Probe Claude and Codex usage limits\nAfter=network-online.target\n\n"
            f"[Service]\nType=oneshot\nExecStart={_probe_command(root)}\n"
        )
        (unit_dir / TIMER_NAME).write_text(
            "[Unit]\nDescription=Probe Claude and Codex usage limits periodically\n\n"
            f"[Timer]\nOnStartupSec=30s\nOnUnitActiveSec={interval}\nAccuracySec=30s\n\n"
            "[Install]\nWantedBy=timers.target\n"
        )
        _systemctl("daemon-reload")

    result = _systemctl("enable", "--now", TIMER_NAME)
    if result.returncode != 0:
        return f"could not enable {TIMER_NAME}: {result.stderr.strip()}"
    _systemctl("start", SERVICE_NAME)
    return f"{TIMER_NAME} enabled (every {interval})"


def enable_extension() -> str:
    if shutil.which("gnome-extensions") is None:
        return "gnome-extensions not found; is this a GNOME session?"
    result = subprocess.run(["gnome-extensions", "enable", EXTENSION_UUID], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return "GNOME extension enabled"
    return (
        "GNOME Shell does not see the extension yet. Log out and back in "
        f"(X11: Alt+F2 → r), then run: gnome-extensions enable {EXTENSION_UUID}"
    )


def run_setup(store: Store, root: Path | None, interval: str, with_system: bool = True) -> int:
    linked = link_detected(store, Path.home(), dict(os.environ))
    profiles = store.load_profiles()

    for candidate in linked:
        print(f"linked   {candidate.provider}-{candidate.name:<12} {candidate.config_dir}")
    if not linked:
        print("no new Claude/Codex config dirs found")
    if not profiles:
        print("No logged-in Claude Code or Codex CLI found. Log in first (`claude`, `codex login`) and rerun setup.")
        return 1

    if with_system:
        print(install_timer(root, interval))
        print(enable_extension())
    return 0

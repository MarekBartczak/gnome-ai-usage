from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from pathlib import Path

from ai_usage.models import Profile, StatusEntry, UsageWindow
from ai_usage.paths import AppPaths


class Store:
    def __init__(self, root: Path):
        self.paths = AppPaths(root)

    def add_profile(self, provider: str, name: str, label: str | None = None) -> Profile:
        profile_id = f"{provider}-{name}"
        profile = Profile(id=profile_id, provider=provider, name=name, label=label or profile_id)
        home = self.paths.profile_home(profile_id)
        home.mkdir(parents=True, exist_ok=True)
        home.chmod(0o700)
        self._bootstrap_provider_home(provider, home)
        self._save_profile(profile)
        return profile

    def link_profile(self, provider: str, name: str, config_dir: Path, label: str | None = None) -> Profile:
        profile_id = f"{provider}-{name}"
        profile = Profile(
            id=profile_id,
            provider=provider,
            name=name,
            label=label or profile_id,
            config_dir=str(config_dir.expanduser().resolve()),
        )
        self._save_profile(profile)
        return profile

    def remove_profile(self, profile_id: str) -> bool:
        profiles = self.load_profiles()
        remaining = [item for item in profiles if item.id != profile_id]
        if len(remaining) == len(profiles):
            return False
        self._write_config(profiles=remaining)
        return True

    def _load_config(self) -> dict:
        if not self.paths.config_path.exists():
            return {}
        return json.loads(self.paths.config_path.read_text())

    def _write_config(self, profiles: list[Profile] | None = None, tools: dict[str, str] | None = None) -> None:
        payload = self._load_config()
        if profiles is not None:
            payload["profiles"] = [asdict(item) for item in profiles]
        if tools is not None:
            payload["tools"] = tools
        self._atomic_write_json(self.paths.config_path, payload)

    def load_tools(self) -> dict[str, str]:
        """Absolute CLI paths recorded by `setup`; the systemd timer runs with a minimal PATH."""
        tools = self._load_config().get("tools")
        return tools if isinstance(tools, dict) else {}

    def save_tools(self, tools: dict[str, str]) -> None:
        self._write_config(tools={**self.load_tools(), **tools})

    def load_profiles(self) -> list[Profile]:
        if not self.paths.config_path.exists():
            return []
        data = self._load_config()
        return [Profile(**item) for item in data.get("profiles", [])]

    def load_status_entries(self) -> dict[str, StatusEntry]:
        try:
            data = json.loads(self.paths.status_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        entries: dict[str, StatusEntry] = {}
        for item in data.get("profiles", []):
            try:
                usage = [UsageWindow(**window) for window in item.get("usage", [])]
                entries[item["id"]] = StatusEntry(**{**item, "usage": usage, "error": None})
            except (KeyError, TypeError):
                continue
        return entries

    def write_status(self, entries: list[StatusEntry], updated_at: str) -> None:
        payload = {
            "updated_at": updated_at,
            "profiles": [entry.to_dict() for entry in entries],
        }
        self._atomic_write_json(self.paths.status_path, payload)

    @staticmethod
    def keep_last_known(entry: StatusEntry, previous: StatusEntry | None) -> StatusEntry:
        """On a failed probe keep the last good numbers, marked stale, instead of blanking the panel."""
        if entry.state == "ok" or previous is None or not previous.usage:
            return entry
        return replace(
            entry,
            state="stale",
            usage=previous.usage,
            account=entry.account or previous.account,
            plan=entry.plan or previous.plan,
            last_ok_at=previous.last_ok_at,
        )

    def _save_profile(self, profile: Profile) -> None:
        profiles = [item for item in self.load_profiles() if item.id != profile.id]
        profiles.append(profile)
        self._write_config(profiles=profiles)

    def _bootstrap_provider_home(self, provider: str, home: Path) -> None:
        if provider != "claude":
            return
        settings_path = home / ".claude.json"
        if settings_path.exists():
            payload = json.loads(settings_path.read_text())
        else:
            payload = {}
        payload.update(
            {
                "hasCompletedOnboarding": True,
                "hasIdeAutoConnectDialogBeenShown": True,
                "autoUpdates": False,
            }
        )
        projects = payload.setdefault("projects", {})
        project = projects.setdefault(str(home), {})
        project["hasTrustDialogAccepted"] = True
        project.setdefault("allowedTools", [])
        project.setdefault("mcpContextUris", [])
        project.setdefault("mcpServers", {})
        project.setdefault("enabledMcpjsonServers", [])
        project.setdefault("disabledMcpjsonServers", [])
        self._atomic_write_json(settings_path, payload)

    def _atomic_write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(tmp_path, path)

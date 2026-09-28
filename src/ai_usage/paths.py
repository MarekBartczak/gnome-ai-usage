from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ai_usage.models import Profile


def default_app_dir() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "ai-usage-module"


DEFAULT_APP_DIR = default_app_dir()
PROVIDER_DIR_ENV = {"claude": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME"}
PROVIDER_DIR_NAME = {"claude": ".claude", "codex": ".codex"}


@dataclass(frozen=True)
class AppPaths:
    root: Path = DEFAULT_APP_DIR

    @property
    def profiles_dir(self) -> Path:
        return self.root / "profiles"

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def status_path(self) -> Path:
        return self.root / "status.json"

    def profile_dir(self, profile_id: str) -> Path:
        return self.profiles_dir / profile_id

    def profile_home(self, profile_id: str) -> Path:
        return self.profile_dir(profile_id) / "home"

    def provider_config_dir(self, profile: Profile) -> Path:
        if profile.config_dir:
            return Path(profile.config_dir).expanduser()
        return self.profile_home(profile.id) / PROVIDER_DIR_NAME[profile.provider]


def build_profile_env(profile_home: Path, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env if base_env is not None else os.environ)
    env["HOME"] = str(profile_home)
    env["XDG_CONFIG_HOME"] = str(profile_home / ".config")
    env["XDG_DATA_HOME"] = str(profile_home / ".local" / "share")
    env["XDG_STATE_HOME"] = str(profile_home / ".local" / "state")
    env["XDG_CACHE_HOME"] = str(profile_home / ".cache")
    # An inherited config dir would silently point the CLI at the user's real account.
    for name in PROVIDER_DIR_ENV.values():
        env.pop(name, None)
    return env


def build_linked_env(provider: str, config_dir: Path, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env if base_env is not None else os.environ)
    for name in PROVIDER_DIR_ENV.values():
        env.pop(name, None)
    env[PROVIDER_DIR_ENV[provider]] = str(config_dir)
    return env

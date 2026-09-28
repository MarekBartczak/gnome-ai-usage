from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Profile:
    id: str
    provider: str
    name: str
    label: str
    # Existing CLI config dir (CLAUDE_CONFIG_DIR / CODEX_HOME) the profile reads from.
    # None means an isolated profile living under the app data dir.
    config_dir: str | None = None


@dataclass(frozen=True)
class UsageWindow:
    window: str
    used_percent: int | None
    remaining_percent: int | None
    reset_at: str | None
    label: str | None = None


@dataclass(frozen=True)
class ProbeError:
    code: str
    message: str


@dataclass(frozen=True)
class StatusEntry:
    id: str
    provider: str
    label: str
    account: str | None
    state: str
    last_probe_at: str
    usage: list[UsageWindow]
    error: ProbeError | None
    plan: str | None = None
    last_ok_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

"""Let the real CLI refresh its own OAuth token.

Refresh tokens rotate, so `ai-usage` must never refresh a linked config dir itself. Instead, when a
token has expired (or is about to), it runs the CLI with a tiny non-interactive prompt: the CLI then
refreshes and stores the token exactly as it would in an interactive session. Local-only commands
(`auth status`, `doctor`, `/cost`) do not refresh reliably.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from ai_usage.models import Profile
from ai_usage.paths import build_linked_env

PING = "Reply with: ok"
WAKE_ARGS = {
    "claude": ["-p", PING, "--model", "haiku", "--max-turns", "1", "--tools", "", "--no-session-persistence"],
    "codex": ["exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", PING],
}
FALLBACK_DIRS = ["~/.local/bin", "~/.claude/local", "~/.npm-global/bin", "~/.bun/bin", "/usr/local/bin", "/usr/bin"]
MIN_INTERVAL_SECONDS = 30 * 60
TIMEOUT_SECONDS = 120


def find_cli(provider: str, recorded: str | None = None) -> str | None:
    if recorded and os.access(recorded, os.X_OK):
        return recorded
    search = os.pathsep.join([os.environ.get("PATH", ""), *(os.path.expanduser(item) for item in FALLBACK_DIRS)])
    return shutil.which(provider, path=search)


class CliWaker:
    def __init__(self, state_dir: Path, tools: dict[str, str], min_interval: float = MIN_INTERVAL_SECONDS):
        self.state_dir = state_dir
        self.tools = tools
        self.min_interval = min_interval

    def _stamp(self, profile: Profile) -> Path:
        return self.state_dir / f"{profile.id}.stamp"

    def _throttled(self, profile: Profile) -> bool:
        try:
            return time.time() - self._stamp(profile).stat().st_mtime < self.min_interval
        except OSError:
            return False

    def __call__(self, profile: Profile, config_dir: Path) -> bool:
        """Run the CLI once so it refreshes its token. Returns True when the CLI ran successfully."""
        if profile.config_dir is None or profile.provider not in WAKE_ARGS or self._throttled(profile):
            return False
        executable = find_cli(profile.provider, self.tools.get(profile.provider))
        if executable is None:
            return False

        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._stamp(profile).touch()
        env = build_linked_env(profile.provider, config_dir)
        # codex is a node script: its interpreter lives next to it (nvm), not on the timer's PATH.
        env["PATH"] = os.pathsep.join([str(Path(executable).parent), env.get("PATH", "")])
        try:
            result = subprocess.run(
                [executable, *WAKE_ARGS[profile.provider]],
                cwd=self.state_dir,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

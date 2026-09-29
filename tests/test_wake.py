import json
import time
from pathlib import Path

from ai_usage.models import Profile
from ai_usage.providers import ClaudeAdapter
from ai_usage.wake import CliWaker


def linked(config_dir: Path, provider: str = "claude") -> Profile:
    return Profile(id=f"{provider}-work", provider=provider, name="work", label="Work", config_dir=str(config_dir))


def write_credentials(config_dir: Path, token: str, expires_in: float) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": token, "expiresAt": int((time.time() + expires_in) * 1000)}})
    )


def fake_cli(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "bin" / "claude"
    script.parent.mkdir(exist_ok=True)
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(0o755)
    return script


def test_expired_token_wakes_cli_and_retries(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "claude-work"
    write_credentials(config_dir, "old", expires_in=-60)
    seen = []
    monkeypatch.setattr(
        "ai_usage.providers.http_get",
        lambda url, headers, name: seen.append(headers["Authorization"]) or '{"five_hour":{"utilization":12}}',
    )

    def wake(profile, directory):
        write_credentials(directory, "fresh", expires_in=8 * 3600)
        return True

    entry = ClaudeAdapter().probe(linked(config_dir), config_dir, "now", wake=wake)

    assert entry.state == "ok"
    assert seen == ["Bearer fresh"]


def test_token_close_to_expiry_is_refreshed_early(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "claude-work"
    write_credentials(config_dir, "old", expires_in=5 * 60)
    monkeypatch.setattr("ai_usage.providers.http_get", lambda url, headers, name: '{"five_hour":{"utilization":1}}')
    woken = []

    def wake(profile, directory):
        woken.append(profile.id)
        write_credentials(directory, "fresh", expires_in=8 * 3600)
        return True

    ClaudeAdapter().probe(linked(config_dir), config_dir, "now", wake=wake)

    assert woken == ["claude-work"]


def test_failed_wake_reports_auth_expired(tmp_path: Path):
    config_dir = tmp_path / "claude-work"
    write_credentials(config_dir, "old", expires_in=-60)

    entry = ClaudeAdapter().probe(linked(config_dir), config_dir, "now", wake=lambda profile, directory: False)

    assert entry.state == "error"
    assert entry.error.code == "auth_expired"


def test_cli_waker_runs_cli_with_config_dir_and_clean_env(tmp_path: Path, monkeypatch):
    marker = tmp_path / "env.txt"
    script = fake_cli(tmp_path, f'printf "%s|%s|%s" "$CLAUDE_CONFIG_DIR" "${{CLAUDECODE:-unset}}" "$1" > {marker}\n')
    monkeypatch.setenv("CLAUDECODE", "1")
    config_dir = tmp_path / "claude-work"
    waker = CliWaker(tmp_path / "wake", {"claude": str(script)})

    assert waker(linked(config_dir), config_dir) is True
    assert marker.read_text() == f"{config_dir}|unset|-p"


def test_cli_waker_is_throttled_and_skips_isolated_profiles(tmp_path: Path):
    runs = tmp_path / "runs.txt"
    script = fake_cli(tmp_path, f"echo run >> {runs}\n")
    config_dir = tmp_path / "claude-work"
    waker = CliWaker(tmp_path / "wake", {"claude": str(script)})

    assert waker(linked(config_dir), config_dir) is True
    assert waker(linked(config_dir), config_dir) is False
    isolated = Profile(id="claude-iso", provider="claude", name="iso", label="Iso")
    assert waker(isolated, config_dir) is False
    assert runs.read_text().count("run") == 1


def test_cli_waker_reports_cli_failure(tmp_path: Path):
    script = fake_cli(tmp_path, "exit 1\n")
    config_dir = tmp_path / "claude-work"

    assert CliWaker(tmp_path / "wake", {"claude": str(script)})(linked(config_dir), config_dir) is False

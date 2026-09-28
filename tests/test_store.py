import json
from pathlib import Path

from ai_usage.models import StatusEntry, UsageWindow
from ai_usage.store import Store


def test_store_creates_profile_home_with_private_permissions(tmp_path: Path):
    store = Store(tmp_path)
    profile = store.add_profile("claude", "work", "Claude Work")

    assert profile.id == "claude-work"
    assert (tmp_path / "profiles" / "claude-work" / "home").is_dir()
    assert oct((tmp_path / "profiles" / "claude-work" / "home").stat().st_mode & 0o777) == "0o700"


def test_store_bootstraps_claude_onboarding_settings(tmp_path: Path):
    store = Store(tmp_path)

    store.add_profile("claude", "work", "Claude Work")

    data = json.loads((tmp_path / "profiles" / "claude-work" / "home" / ".claude.json").read_text())
    home = str(tmp_path / "profiles" / "claude-work" / "home")
    assert data["hasCompletedOnboarding"] is True
    assert data["hasIdeAutoConnectDialogBeenShown"] is True
    assert data["autoUpdates"] is False
    assert data["projects"][home]["hasTrustDialogAccepted"] is True


def test_store_preserves_existing_claude_settings(tmp_path: Path):
    settings_path = tmp_path / "profiles" / "claude-work" / "home" / ".claude.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"oauthAccount":{"email":"user@example.com"},"hasCompletedOnboarding":false}\n')
    store = Store(tmp_path)

    store.add_profile("claude", "work", "Claude Work")

    data = json.loads(settings_path.read_text())
    home = str(tmp_path / "profiles" / "claude-work" / "home")
    assert data["oauthAccount"] == {"email": "user@example.com"}
    assert data["hasCompletedOnboarding"] is True
    assert data["projects"][home]["hasTrustDialogAccepted"] is True


def test_store_writes_status_json(tmp_path: Path):
    store = Store(tmp_path)
    entry = StatusEntry(
        id="claude-work",
        provider="claude",
        label="Claude Work",
        account="user@example.com",
        state="ok",
        last_probe_at="2026-05-05T10:00:00Z",
        usage=[
            UsageWindow(
                window="current_session",
                used_percent=98,
                remaining_percent=2,
                reset_at="2026-05-05T13:20:00+02:00",
            )
        ],
        error=None,
    )

    store.write_status([entry], updated_at="2026-05-05T10:00:00Z")

    data = json.loads((tmp_path / "status.json").read_text())
    assert data["profiles"][0]["id"] == "claude-work"
    assert data["profiles"][0]["usage"][0]["used_percent"] == 98

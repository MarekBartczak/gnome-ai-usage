import json
import os
from pathlib import Path

from ai_usage.cli import main


def test_profile_add_creates_config(tmp_path: Path):
    code = main(["--root", str(tmp_path), "profile", "add", "claude", "work", "--label", "Claude Work"])

    assert code == 0
    data = json.loads((tmp_path / "config.json").read_text())
    assert data["profiles"][0]["id"] == "claude-work"


def test_status_prints_existing_status(tmp_path: Path, capsys):
    (tmp_path / "status.json").write_text('{"updated_at":"now","profiles":[]}\n')

    code = main(["--root", str(tmp_path), "status", "--json"])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["profiles"] == []


def test_profile_login_uses_isolated_home(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "login-home.txt"
    fake_claude = bin_dir / "claude"
    fake_claude.write_text(
        "#!/usr/bin/env sh\n"
        "if [ \"$1 $2\" = \"auth login\" ]; then\n"
        f"  printf '%s' \"$HOME\" > {marker}\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n"
    )
    fake_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    assert main(["--root", str(tmp_path), "profile", "add", "claude", "work"]) == 0
    assert main(["--root", str(tmp_path), "profile", "login", "claude", "work"]) == 0

    assert marker.read_text() == str(tmp_path / "profiles" / "claude-work" / "home")


def test_profile_link_stores_config_dir(tmp_path: Path):
    config_dir = tmp_path / "claude-work"
    config_dir.mkdir()

    assert main(["--root", str(tmp_path), "profile", "link", "claude", "work", str(config_dir)]) == 0

    data = json.loads((tmp_path / "config.json").read_text())
    assert data["profiles"][0]["config_dir"] == str(config_dir.resolve())
    assert not (tmp_path / "profiles").exists()


def test_profile_login_does_not_leak_real_config_dir(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "login-env.txt"
    fake_claude = bin_dir / "claude"
    fake_claude.write_text(f"#!/usr/bin/env sh\nprintf '%s' \"${{CLAUDE_CONFIG_DIR:-unset}}\" > {marker}\n")
    fake_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/home/someone/.claude-real")

    assert main(["--root", str(tmp_path), "profile", "login", "claude", "work"]) == 0

    assert marker.read_text() == "unset"


def test_probe_keeps_last_known_usage_when_probe_fails(tmp_path: Path):
    config_dir = tmp_path / "missing-claude"
    config_dir.mkdir()
    assert main(["--root", str(tmp_path), "profile", "link", "claude", "work", str(config_dir)]) == 0
    (tmp_path / "status.json").write_text(json.dumps({
        "updated_at": "old",
        "profiles": [{
            "id": "claude-work", "provider": "claude", "label": "claude-work", "account": "a@example.com",
            "state": "ok", "last_probe_at": "old", "last_ok_at": "old", "plan": None, "error": None,
            "usage": [{"window": "current_session", "used_percent": 40, "remaining_percent": 60, "reset_at": None}],
        }],
    }))

    assert main(["--root", str(tmp_path), "probe"]) == 0

    entry = json.loads((tmp_path / "status.json").read_text())["profiles"][0]
    assert entry["state"] == "stale"
    assert entry["usage"][0]["used_percent"] == 40
    assert entry["last_ok_at"] == "old"
    assert entry["error"]["code"] == "credentials_missing"

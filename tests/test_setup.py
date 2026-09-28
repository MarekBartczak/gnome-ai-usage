import json
import os
from pathlib import Path

from ai_usage.setup import detect_claude, detect_codex, link_detected
from ai_usage.store import Store


def make_claude(home: Path, dirname: str, account_uuid: str, mtime: float) -> Path:
    config_dir = home / dirname
    config_dir.mkdir()
    credentials = config_dir / ".credentials.json"
    credentials.write_text(json.dumps({"claudeAiOauth": {"accessToken": "at"}}))
    os.utime(credentials, (mtime, mtime))
    (config_dir / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": account_uuid}}))
    return config_dir


def test_detect_claude_finds_named_dirs_and_dedupes_same_account(tmp_path: Path):
    make_claude(tmp_path, ".claude", "acc-work", mtime=100)
    work = make_claude(tmp_path, ".claude-work", "acc-work", mtime=200)
    personal = make_claude(tmp_path, ".claude-personal", "acc-personal", mtime=100)
    (tmp_path / ".claude-empty").mkdir()

    found = detect_claude(tmp_path, {})

    assert [(item.name, item.label, item.config_dir) for item in found] == [
        ("personal", "Claude Personal", personal),
        ("work", "Claude Work", work),
    ]


def test_detect_codex_requires_chatgpt_tokens(tmp_path: Path):
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "auth.json").write_text(json.dumps({"tokens": {"access_token": "x", "account_id": "a"}}))
    (tmp_path / ".codex-apikey").mkdir()
    (tmp_path / ".codex-apikey" / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": "sk"}))

    found = detect_codex(tmp_path, {})

    assert [(item.name, item.label) for item in found] == [("default", "Codex")]


def test_link_detected_is_idempotent(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    make_claude(home, ".claude", "acc", mtime=100)
    store = Store(tmp_path / "data")

    assert [item.name for item in link_detected(store, home, {})] == ["default"]
    assert link_detected(store, home, {}) == []
    assert [profile.id for profile in store.load_profiles()] == ["claude-default"]

import base64
import json
import time

from ai_usage.models import Profile
from ai_usage.providers import (
    ClaudeAdapter,
    CodexAdapter,
    ProbeFailure,
    claude_access_token,
    fetch_codex_usage,
    parse_claude_usage_response,
    parse_codex_usage_response,
)


def fake_jwt(exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.sig"


def write_claude_dir(config_dir, expires_at_ms, email="user@example.com"):
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "at", "refreshToken": "rt", "expiresAt": expires_at_ms}})
    )
    (config_dir / ".claude.json").write_text(json.dumps({"oauthAccount": {"emailAddress": email}}))


def test_parse_claude_usage_response_from_oauth_endpoint():
    raw = """{
      "five_hour": {"utilization": 77.0, "resets_at": "2026-05-14T12:40:00.212900+00:00"},
      "seven_day": {"utilization": 42.0, "resets_at": "2026-05-14T23:00:00.212922+00:00"}
    }"""

    usage = parse_claude_usage_response(raw)

    assert [(item.window, item.used_percent, item.remaining_percent) for item in usage] == [
        ("current_session", 77, 23),
        ("current_week", 42, 58),
    ]
    assert usage[0].reset_at.startswith("2026-05-14")


def test_parse_claude_usage_response_accepts_fractional_utilization():
    usage = parse_claude_usage_response('{"five_hour": {"utilization": 0.77, "resets_at": null}}')

    assert usage[0].used_percent == 77


def test_parse_claude_usage_response_reads_scoped_limits_and_extra_usage():
    raw = json.dumps(
        {
            "five_hour": {"utilization": 11.0, "resets_at": "2026-09-28T16:39:59+00:00"},
            "seven_day": {"utilization": 34.0, "resets_at": "2026-10-01T05:59:59+00:00"},
            "extra_usage": {"is_enabled": True, "utilization": 100.0},
            "limits": [
                {"kind": "session", "percent": 11},
                {
                    "kind": "weekly_scoped",
                    "percent": 10,
                    "resets_at": "2026-10-01T05:59:59+00:00",
                    "scope": {"model": {"display_name": "Fable"}},
                },
            ],
        }
    )

    usage = parse_claude_usage_response(raw)

    assert [(item.window, item.label, item.used_percent) for item in usage] == [
        ("current_session", None, 11),
        ("current_week", None, 34),
        ("week_fable", "Week Fable", 10),
        ("extra_usage", "Extra usage", 100),
    ]


def test_parse_claude_usage_response_skips_disabled_extra_usage():
    raw = '{"five_hour": {"utilization": 5}, "extra_usage": {"is_enabled": false, "utilization": 0}}'

    assert [item.window for item in parse_claude_usage_response(raw)] == ["current_session"]


def test_parse_codex_usage_response_from_wham_endpoint():
    raw = """{
      "email": "user@example.com",
      "plan_type": "team",
      "rate_limit": {
        "primary_window": {"used_percent": 6, "limit_window_seconds": 18000, "reset_at": 1778777094},
        "secondary_window": {"used_percent": 17, "limit_window_seconds": 604800, "reset_at": 1779200469}
      }
    }"""

    account, plan, usage = parse_codex_usage_response(raw)

    assert (account, plan) == ("user@example.com", "team")
    assert [(item.window, item.used_percent, item.remaining_percent) for item in usage] == [
        ("five_hour", 6, 94),
        ("current_week", 17, 83),
    ]
    assert usage[0].reset_at is not None


def test_parse_codex_usage_response_classifies_windows_by_length():
    raw = """{"rate_limit": {
        "primary_window": {"used_percent": 40, "limit_window_seconds": 604800, "reset_at": 1779200469},
        "secondary_window": null
    }}"""

    _, _, usage = parse_codex_usage_response(raw)

    assert [(item.window, item.used_percent) for item in usage] == [("current_week", 40)]


def test_linked_claude_profile_does_not_refresh_expired_token(tmp_path):
    write_claude_dir(tmp_path, expires_at_ms=int((time.time() - 10) * 1000))

    try:
        claude_access_token(tmp_path, may_refresh=False)
    except ProbeFailure as exc:
        assert exc.code == "auth_expired"
    else:
        raise AssertionError("expected auth_expired")


def test_codex_rejects_expired_jwt_without_network(tmp_path):
    (tmp_path / "auth.json").write_text(json.dumps({"tokens": {"access_token": fake_jwt(int(time.time()) - 10)}}))

    try:
        fetch_codex_usage(tmp_path)
    except ProbeFailure as exc:
        assert exc.code == "auth_expired"
    else:
        raise AssertionError("expected auth_expired")


def test_claude_probe_reads_linked_config_dir(tmp_path, monkeypatch):
    write_claude_dir(tmp_path, expires_at_ms=int((time.time() + 3600) * 1000))
    calls = []

    def fake_get(url, headers, provider_name):
        calls.append(headers["Authorization"])
        return '{"five_hour":{"utilization":98.0,"resets_at":"2026-05-14T12:40:00+00:00"}}'

    monkeypatch.setattr("ai_usage.providers.http_get", fake_get)
    profile = Profile(id="claude-work", provider="claude", name="work", label="Claude Work", config_dir=str(tmp_path))

    entry = ClaudeAdapter().probe(profile, tmp_path, "2026-05-05T10:00:00Z")

    assert entry.state == "ok"
    assert entry.account == "user@example.com"
    assert entry.usage[0].used_percent == 98
    assert entry.last_ok_at == "2026-05-05T10:00:00Z"
    assert calls == ["Bearer at"]


def test_claude_probe_reports_http_failure_as_error(tmp_path, monkeypatch):
    write_claude_dir(tmp_path, expires_at_ms=int((time.time() + 3600) * 1000))

    def fail(url, headers, provider_name):
        raise ProbeFailure("rate_limited", "Claude usage endpoint returned HTTP 429")

    monkeypatch.setattr("ai_usage.providers.http_get", fail)
    profile = Profile(id="claude-work", provider="claude", name="work", label="Claude Work", config_dir=str(tmp_path))

    entry = ClaudeAdapter().probe(profile, tmp_path, "2026-05-05T10:00:00Z")

    assert entry.state == "error"
    assert entry.error.code == "rate_limited"
    assert entry.account == "user@example.com"


def test_codex_probe_uses_usage_endpoint(tmp_path, monkeypatch):
    (tmp_path / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": fake_jwt(int(time.time()) + 3600), "account_id": "acc"}})
    )
    seen = {}

    def fake_get(url, headers, provider_name):
        seen.update(headers)
        return (
            '{"email":"user@example.com","rate_limit":{'
            '"primary_window":{"used_percent":2,"reset_at":1778777094},'
            '"secondary_window":{"used_percent":13,"reset_at":1779200469}}}'
        )

    monkeypatch.setattr("ai_usage.providers.http_get", fake_get)
    profile = Profile(id="codex-main", provider="codex", name="main", label="Codex Main", config_dir=str(tmp_path))

    entry = CodexAdapter().probe(profile, tmp_path, "2026-05-05T10:00:00Z")

    assert entry.state == "ok"
    assert entry.account == "user@example.com"
    assert [item.window for item in entry.usage] == ["five_hour", "current_week"]
    assert seen["ChatGPT-Account-Id"] == "acc"

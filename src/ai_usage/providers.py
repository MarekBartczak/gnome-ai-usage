from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from ai_usage.models import ProbeError, Profile, StatusEntry, UsageWindow

ANTHROPIC_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_OAUTH_BETA = "oauth-2025-04-20"
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"
CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
FIVE_HOURS_SECONDS = 5 * 3600
SEVEN_DAYS_SECONDS = 7 * 86400
# Wake the CLI a bit before expiry so the panel never goes stale between two timer runs.
EXPIRY_MARGIN_SECONDS = 10 * 60
WAKE_CODES = {"auth_expired", "auth_invalid"}

Waker = Callable[[Profile, Path], bool]


class ProbeFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def clamp_percent(value: int | float) -> int:
    return max(0, min(100, round(value)))


def usage_percent_from_utilization(utilization: int | float) -> int:
    # The endpoint reports 0-100; older builds reported a 0-1 fraction.
    if 0 < utilization < 1:
        utilization *= 100
    return clamp_percent(utilization)


def format_reset_at(reset_at: object) -> str | None:
    if isinstance(reset_at, (int, float)):
        return datetime.fromtimestamp(reset_at).astimezone().isoformat(timespec="seconds")
    if isinstance(reset_at, str):
        try:
            parsed = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
        except ValueError:
            return reset_at
        return parsed.astimezone().isoformat(timespec="seconds")
    return None


def make_window(window: str, used: int | float, reset_at: object, label: str | None = None) -> UsageWindow:
    used_percent = clamp_percent(used)
    return UsageWindow(
        window=window,
        used_percent=used_percent,
        remaining_percent=100 - used_percent,
        reset_at=format_reset_at(reset_at),
        label=label,
    )


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def parse_claude_usage_response(raw: str) -> list[UsageWindow]:
    data = json.loads(raw)
    usage: list[UsageWindow] = []

    for window_name, key in (("current_session", "five_hour"), ("current_week", "seven_day")):
        window = data.get(key)
        if isinstance(window, dict) and isinstance(window.get("utilization"), (int, float)):
            usage.append(
                make_window(window_name, usage_percent_from_utilization(window["utilization"]), window.get("resets_at"))
            )

    # Per-model weekly caps (e.g. "Fable") are only reported in the newer `limits` list.
    for limit in data.get("limits") or []:
        if not isinstance(limit, dict) or limit.get("kind") != "weekly_scoped":
            continue
        model = ((limit.get("scope") or {}).get("model") or {}).get("display_name")
        if not isinstance(model, str) or not isinstance(limit.get("percent"), (int, float)):
            continue
        usage.append(make_window(f"week_{slugify(model)}", limit["percent"], limit.get("resets_at"), f"Week {model}"))

    extra = data.get("extra_usage")
    if isinstance(extra, dict) and extra.get("is_enabled") and isinstance(extra.get("utilization"), (int, float)):
        usage.append(make_window("extra_usage", extra["utilization"], None, "Extra usage"))

    return deduplicate_usage(usage)


def codex_window_name(window: dict, fallback: str) -> str:
    seconds = window.get("limit_window_seconds")
    if seconds == FIVE_HOURS_SECONDS:
        return "five_hour"
    if seconds == SEVEN_DAYS_SECONDS:
        return "current_week"
    return fallback


def parse_codex_usage_response(raw: str) -> tuple[str | None, str | None, list[UsageWindow]]:
    data = json.loads(raw)
    usage: list[UsageWindow] = []
    rate_limit = data.get("rate_limit") or {}
    for key, fallback in (("primary_window", "five_hour"), ("secondary_window", "current_week")):
        window = rate_limit.get(key)
        if isinstance(window, dict) and isinstance(window.get("used_percent"), (int, float)):
            usage.append(make_window(codex_window_name(window, fallback), window["used_percent"], window.get("reset_at")))
    return data.get("email"), data.get("plan_type"), deduplicate_usage(usage)


def deduplicate_usage(usage: Sequence[UsageWindow]) -> list[UsageWindow]:
    by_window: dict[str, UsageWindow] = {}
    for item in usage:
        by_window[item.window] = item
    return list(by_window.values())


def read_json(path: Path, missing_message: str) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeFailure("credentials_missing", missing_message) from exc


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2) + "\n")
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def http_get(url: str, headers: dict[str, str], provider_name: str) -> str:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode()
    except urllib.error.HTTPError as exc:
        code = "auth_invalid" if exc.code in (401, 403) else "rate_limited" if exc.code == 429 else "http_error"
        raise ProbeFailure(code, f"{provider_name} usage endpoint returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ProbeFailure("network_error", f"{provider_name} usage endpoint failed: {exc.reason}") from exc


def claude_account_email(config_dir: Path) -> str | None:
    # With CLAUDE_CONFIG_DIR the account file sits inside the dir, otherwise next to it in $HOME.
    for path in (config_dir / ".claude.json", config_dir.parent / ".claude.json"):
        try:
            email = (json.loads(path.read_text()).get("oauthAccount") or {}).get("emailAddress")
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        if isinstance(email, str):
            return email
    return None


def refresh_claude_tokens(credentials_path: Path, credentials: dict) -> str:
    oauth = credentials.get("claudeAiOauth")
    if not isinstance(oauth, dict) or not isinstance(oauth.get("refreshToken"), str):
        raise ProbeFailure("auth_expired", "Claude refresh token is missing")

    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": ANTHROPIC_OAUTH_CLIENT_ID,
            "refresh_token": oauth["refreshToken"],
        }
    ).encode()
    request = urllib.request.Request(
        CLAUDE_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "anthropic-beta": ANTHROPIC_OAUTH_BETA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            refreshed = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise ProbeFailure("auth_expired", f"Claude token refresh returned HTTP {exc.code}; log in again") from exc
    except urllib.error.URLError as exc:
        raise ProbeFailure("network_error", f"Claude token refresh failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ProbeFailure("auth_expired", "Claude token refresh returned invalid JSON") from exc

    access_token = refreshed.get("access_token")
    refresh_token = refreshed.get("refresh_token")
    expires_in = refreshed.get("expires_in")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str) or not isinstance(expires_in, int):
        raise ProbeFailure("auth_expired", "Claude token refresh response is missing required fields")

    oauth["accessToken"] = access_token
    oauth["refreshToken"] = refresh_token
    oauth["expiresAt"] = int(time.time() * 1000) + expires_in * 1000
    if isinstance(refreshed.get("scope"), str):
        oauth["scopes"] = refreshed["scope"].split()
    atomic_write_json(credentials_path, credentials)
    return access_token


def claude_access_token(config_dir: Path, may_refresh: bool) -> str:
    credentials_path = config_dir / ".credentials.json"
    credentials = read_json(credentials_path, f"Claude credentials not found in {config_dir}")
    oauth = credentials.get("claudeAiOauth")
    if not isinstance(oauth, dict) or not isinstance(oauth.get("accessToken"), str):
        raise ProbeFailure("credentials_missing", "Claude credentials have an unsupported format")

    expires_at = oauth.get("expiresAt")
    expired = isinstance(expires_at, (int, float)) and expires_at / 1000 <= time.time() + EXPIRY_MARGIN_SECONDS
    if not expired:
        return oauth["accessToken"]
    if not may_refresh:
        # Refresh tokens rotate; refreshing a linked CLI dir ourselves would log that CLI out.
        raise ProbeFailure("auth_expired", "Claude token expired and the CLI could not refresh it; run claude with this config dir")
    return refresh_claude_tokens(credentials_path, credentials)


def fetch_claude_usage(config_dir: Path, may_refresh: bool) -> str:
    access_token = claude_access_token(config_dir, may_refresh)
    return http_get(
        CLAUDE_USAGE_URL,
        {
            "Authorization": f"Bearer {access_token}",
            "anthropic-beta": ANTHROPIC_OAUTH_BETA,
            "User-Agent": "claude-code",
        },
        "Claude",
    )


def jwt_expiry(token: str) -> int | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
    except (IndexError, ValueError, AttributeError):
        return None
    return exp if isinstance(exp, int) else None


def fetch_codex_usage(config_dir: Path) -> str:
    auth = read_json(config_dir / "auth.json", f"Codex auth.json not found in {config_dir}")
    tokens = auth.get("tokens")
    if not isinstance(tokens, dict) or not isinstance(tokens.get("access_token"), str):
        raise ProbeFailure("credentials_missing", "Codex auth.json has no ChatGPT tokens (API key login?)")

    access_token = tokens["access_token"]
    exp = jwt_expiry(access_token)
    if exp is not None and exp <= time.time() + EXPIRY_MARGIN_SECONDS:
        raise ProbeFailure("auth_expired", "Codex token expired and the CLI could not refresh it; run codex with this config dir")

    headers = {"Authorization": f"Bearer {access_token}", "User-Agent": "codex-cli"}
    if isinstance(tokens.get("account_id"), str):
        headers["ChatGPT-Account-Id"] = tokens["account_id"]
    return http_get(CODEX_USAGE_URL, headers, "Codex")


def build_entry(
    profile: Profile,
    now_iso: str,
    account: str | None,
    usage: Sequence[UsageWindow],
    plan: str | None = None,
    error: ProbeError | None = None,
) -> StatusEntry:
    if error is None and not usage:
        error = ProbeError(code="usage_not_found", message="Usage response did not contain supported usage fields")
    return StatusEntry(
        id=profile.id,
        provider=profile.provider,
        label=profile.label,
        account=account,
        state="ok" if error is None else "error",
        last_probe_at=now_iso,
        usage=list(usage),
        error=error,
        plan=plan,
        last_ok_at=now_iso if error is None else None,
    )


def fetch_with_wake(fetch: Callable[[], str], profile: Profile, config_dir: Path, wake: Waker | None) -> str:
    try:
        return fetch()
    except ProbeFailure as exc:
        if exc.code not in WAKE_CODES or wake is None or not wake(profile, config_dir):
            raise
    return fetch()


class ProviderAdapter:
    provider: str
    login_command: list[str]

    def probe(self, profile: Profile, config_dir: Path, now_iso: str, wake: Waker | None = None) -> StatusEntry:
        raise NotImplementedError


class ClaudeAdapter(ProviderAdapter):
    provider = "claude"
    login_command = ["claude", "auth", "login"]

    def probe(self, profile: Profile, config_dir: Path, now_iso: str, wake: Waker | None = None) -> StatusEntry:
        account = claude_account_email(config_dir)
        try:
            raw = fetch_with_wake(
                lambda: fetch_claude_usage(config_dir, may_refresh=profile.config_dir is None), profile, config_dir, wake
            )
            usage = parse_claude_usage_response(raw)
        except ProbeFailure as exc:
            return build_entry(profile, now_iso, account, [], error=ProbeError(exc.code, exc.message))
        except (json.JSONDecodeError, AttributeError) as exc:
            return build_entry(profile, now_iso, account, [], error=ProbeError("parse_error", str(exc)))
        return build_entry(profile, now_iso, account, usage)


class CodexAdapter(ProviderAdapter):
    provider = "codex"
    login_command = ["codex", "login"]

    def probe(self, profile: Profile, config_dir: Path, now_iso: str, wake: Waker | None = None) -> StatusEntry:
        try:
            raw = fetch_with_wake(lambda: fetch_codex_usage(config_dir), profile, config_dir, wake)
            account, plan, usage = parse_codex_usage_response(raw)
        except ProbeFailure as exc:
            return build_entry(profile, now_iso, None, [], error=ProbeError(exc.code, exc.message))
        except (json.JSONDecodeError, AttributeError) as exc:
            return build_entry(profile, now_iso, None, [], error=ProbeError("parse_error", str(exc)))
        return build_entry(profile, now_iso, account, usage, plan=plan)


def get_adapter(provider: str) -> ProviderAdapter:
    if provider == "claude":
        return ClaudeAdapter()
    if provider == "codex":
        return CodexAdapter()
    raise ValueError(f"Unsupported provider: {provider}")

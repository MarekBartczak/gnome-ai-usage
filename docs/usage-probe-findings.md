# Usage Probe Findings

Updated: 2026-09-28 (Claude Code 2.1.283, codex-cli 0.158.0, GNOME Shell 46)

## Approach

Profiles are **linked** to the CLI config dirs used day to day (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`),
so tokens stay fresh through normal CLI use. The probe is HTTP only: no CLI subprocess, no TUI scraping.

    ai-usage profile link claude work ~/.claude-work --label "Claude Work"
    ai-usage profile link claude personal ~/.claude-personal --label "Claude Personal"
    ai-usage profile link codex main ~/.codex --label "Codex"
    ai-usage setup                        # or auto-detect all of the above + timer

Isolated profiles (`profile add` + `profile login`) still work, but their tokens rot when unused:
after ~4 months without use the Claude refresh token returned `invalid_grant`.

Linked profiles never refresh tokens themselves. Both providers rotate refresh tokens, so refreshing
from outside would log the real CLI out. An expired token yields `auth_expired`; the last good numbers
are kept with state `stale` until the CLI is used again.

## Claude

- Credentials: `<config_dir>/.credentials.json` → `claudeAiOauth.accessToken`, `expiresAt` (ms).
- Account email: `<config_dir>/.claude.json` → `oauthAccount.emailAddress` (or `~/.claude.json` for the default dir).
- Usage: `GET https://api.anthropic.com/api/oauth/usage`, header `anthropic-beta: oauth-2025-04-20` (unofficial).
  - `five_hour` / `seven_day`: `utilization` (0-100) + `resets_at`.
  - `limits[]`: `session`, `weekly_all`, `weekly_scoped` (per-model cap, e.g. `scope.model.display_name = "Fable"`).
  - `extra_usage`: `is_enabled`, `utilization` for pay-as-you-go credits.
  - Many other keys are codenames and are `null`; ignored.

## Codex

- Credentials: `<config_dir>/auth.json` → `tokens.access_token` (JWT, `exp` checked locally), `tokens.account_id`.
- Usage: `GET https://chatgpt.com/backend-api/wham/usage` with `ChatGPT-Account-Id`.
  - `rate_limit.primary_window` / `secondary_window`: `used_percent`, `limit_window_seconds`, `reset_at` (epoch).
  - Windows are classified by `limit_window_seconds` (18000 = 5h, 604800 = week), not by position.
  - `email`, `plan_type` at top level.

## GNOME extension

- Top bar: one group per profile (icon, 5h %, week %); defaults to the first profile of each provider,
  toggled per profile with "Show on top bar". Yellow ≥ 75 %, red ≥ 90 %, dimmed when stale.
- Reloads on `status.json` change (file monitor) plus a fallback timer; "Refresh now" runs
  `systemctl --user start ai-usage-probe.service`.
- Install: `./scripts/install-gnome-extension-local.sh && gnome-extensions enable ai-usage@marekbartczak.github.io`.
- After code changes on X11: Alt+F2 → `r`; on Wayland: log out and back in.

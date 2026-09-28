const WARN_PERCENT = 75;
const CRITICAL_PERCENT = 90;
const PROVIDER_ORDER = ['claude', 'codex'];

const WINDOW_LABELS = {
    current_session: 'Session (5h)',
    five_hour: 'Session (5h)',
    current_week: 'Week',
};

function byWindow(usageList) {
    return new Map((usageList ?? []).map(item => [item.window, item]));
}

function severityFor(usedPercent) {
    if (usedPercent === null)
        return 'unknown';
    if (usedPercent >= CRITICAL_PERCENT)
        return 'critical';
    if (usedPercent >= WARN_PERCENT)
        return 'warning';
    return 'normal';
}

function normalizeWindow(label, item) {
    const usedPercent = item?.used_percent ?? null;

    return {
        key: item?.window ?? null,
        label,
        usedPercent,
        resetAt: item?.reset_at ?? null,
        severity: severityFor(usedPercent),
    };
}

function shortWindowKeyForProvider(provider) {
    switch (provider) {
    case 'codex':
        return 'five_hour';
    case 'claude':
        return 'current_session';
    default:
        return null;
    }
}

function normalizeProfile(profile) {
    const usage = byWindow(profile.usage);
    const shortKey = shortWindowKeyForProvider(profile.provider);

    return {
        id: profile.id,
        provider: profile.provider,
        label: profile.label,
        account: profile.account ?? '',
        plan: profile.plan ?? null,
        state: profile.state,
        stale: profile.state !== 'ok',
        error: profile.error ?? null,
        lastOkAt: profile.last_ok_at ?? null,
        shortWindow: normalizeWindow('Session (5h)', shortKey ? usage.get(shortKey) : null),
        weekWindow: normalizeWindow('Week', usage.get('current_week')),
        windows: (profile.usage ?? []).map(item =>
            normalizeWindow(item.label ?? WINDOW_LABELS[item.window] ?? item.window, item)),
    };
}

export function normalizeProfiles(raw, primaryProfileId) {
    const profiles = (raw.profiles ?? []).map(normalizeProfile);
    const primary = profiles.find(profile => profile.id === primaryProfileId) ?? profiles[0] ?? null;

    return {
        primary,
        profiles,
        updatedAt: raw.updated_at ?? null,
    };
}

// Profiles shown on the top bar: the explicit selection, or the first profile of each provider.
export function panelProfiles(view, panelIds) {
    const selected = (panelIds ?? [])
        .map(id => view.profiles.find(profile => profile.id === id))
        .filter(Boolean);

    if (selected.length)
        return selected;

    return PROVIDER_ORDER
        .map(provider => view.profiles.find(profile => profile.provider === provider))
        .filter(Boolean);
}

export function togglePanelId(view, panelIds, profileId) {
    const current = panelProfiles(view, panelIds).map(profile => profile.id);
    const next = current.includes(profileId)
        ? current.filter(id => id !== profileId)
        : [...current, profileId];

    return next;
}

export function formatDuration(seconds) {
    if (seconds <= 0)
        return 'now';

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0)
        return `${days}d ${hours}h`;
    if (hours > 0)
        return `${hours}h ${minutes}m`;
    return `${Math.max(1, minutes)}m`;
}

export function formatResetIn(resetAt, nowMs = Date.now()) {
    if (!resetAt)
        return null;

    const resetMs = Date.parse(resetAt);

    if (Number.isNaN(resetMs))
        return resetAt;

    return `resets in ${formatDuration(Math.round((resetMs - nowMs) / 1000))}`;
}

export function formatAge(iso, nowMs = Date.now()) {
    if (!iso)
        return null;

    const thenMs = Date.parse(iso);

    if (Number.isNaN(thenMs))
        return null;

    const seconds = Math.round((nowMs - thenMs) / 1000);

    return seconds < 60 ? 'just now' : `${formatDuration(seconds)} ago`;
}

export {CRITICAL_PERCENT, WARN_PERCENT};

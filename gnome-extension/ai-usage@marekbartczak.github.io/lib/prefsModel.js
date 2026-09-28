const MIN_REFRESH_INTERVAL_SECONDS = 5;
const MAX_REFRESH_INTERVAL_SECONDS = 600;

export function normalizeStatusFilePath(value, fallback = '') {
    const candidate = String(value ?? '').trim();

    if (!candidate || !candidate.startsWith('/'))
        return fallback;

    return candidate;
}

export function normalizeRefreshInterval(value) {
    const numeric = Number(value);

    if (!Number.isFinite(numeric))
        return MIN_REFRESH_INTERVAL_SECONDS;

    return Math.min(
        MAX_REFRESH_INTERVAL_SECONDS,
        Math.max(MIN_REFRESH_INTERVAL_SECONDS, Math.round(numeric))
    );
}

export {
    MAX_REFRESH_INTERVAL_SECONDS,
    MIN_REFRESH_INTERVAL_SECONDS,
};

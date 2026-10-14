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

// Gdk.RGBA channels are 0..1 floats; group-colors stores #rrggbb.
export function rgbaToHex({red, green, blue}) {
    return `#${[red, green, blue]
        .map(channel => Math.round(channel * 255).toString(16).padStart(2, '0'))
        .join('')}`;
}

// A null color drops the override, so the group goes back to its automatic color.
export function withGroupColor(colors, groupKey, color) {
    const next = {...colors};

    if (color)
        next[groupKey] = color;
    else
        delete next[groupKey];

    return next;
}

export {
    MAX_REFRESH_INTERVAL_SECONDS,
    MIN_REFRESH_INTERVAL_SECONDS,
};

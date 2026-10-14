import {
    MAX_REFRESH_INTERVAL_SECONDS,
    MIN_REFRESH_INTERVAL_SECONDS,
    normalizeRefreshInterval,
    normalizeStatusFilePath,
    rgbaToHex,
    withGroupColor,
} from '../../gnome-extension/ai-usage@marekbartczak.github.io/lib/prefsModel.js';

function assertEqual(actual, expected, message) {
    if (actual !== expected)
        throw new Error(`${message}: expected ${expected}, got ${actual}`);
}

assertEqual(
    normalizeStatusFilePath('/home/user/.local/share/ai-usage-module/status.json'),
    '/home/user/.local/share/ai-usage-module/status.json',
    'absolute status path is preserved'
);

assertEqual(
    normalizeStatusFilePath('relative/status.json', '/fallback/status.json'),
    '/fallback/status.json',
    'relative status path falls back'
);

assertEqual(
    normalizeStatusFilePath('', '/fallback/status.json'),
    '/fallback/status.json',
    'empty status path falls back'
);

assertEqual(
    normalizeRefreshInterval(1),
    MIN_REFRESH_INTERVAL_SECONDS,
    'refresh interval is clamped to minimum'
);

assertEqual(
    normalizeRefreshInterval(9999),
    MAX_REFRESH_INTERVAL_SECONDS,
    'refresh interval is clamped to maximum'
);

assertEqual(
    normalizeRefreshInterval(29.6),
    30,
    'refresh interval is rounded to the nearest integer'
);

assertEqual(rgbaToHex({red: 0.8627, green: 0.5412, blue: 0.8667}), '#dc8add', 'color button rgba becomes #rrggbb');
assertEqual(rgbaToHex({red: 0, green: 1, blue: 0.0039}), '#00ff01', 'channels are zero-padded');

const colors = {work: '#99c1f1'};

assertEqual(JSON.stringify(withGroupColor(colors, 'home', '#dc8add')), '{"work":"#99c1f1","home":"#dc8add"}', 'sets a group color');
assertEqual(JSON.stringify(withGroupColor(colors, 'work', null)), '{}', 'null removes the override');
assertEqual(JSON.stringify(colors), '{"work":"#99c1f1"}', 'input map is not mutated');

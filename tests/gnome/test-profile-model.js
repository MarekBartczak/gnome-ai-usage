import {
    formatDuration,
    formatResetIn,
    groupProfiles,
    menuGroups,
    normalizeProfiles,
    panelProfiles,
    togglePanelId,
} from '../../gnome-extension/ai-usage@marekbartczak.github.io/lib/profileModel.js';

function assertEqual(actual, expected, message) {
    const a = JSON.stringify(actual);
    const e = JSON.stringify(expected);

    if (a !== e)
        throw new Error(`${message}: expected ${e}, got ${a}`);
}

const data = {
    updated_at: '2026-05-14T10:00:00Z',
    profiles: [
        {
            id: 'codex-main',
            provider: 'codex',
            label: 'Codex Main',
            state: 'ok',
            usage: [
                {window: 'five_hour', used_percent: 36, reset_at: '2026-05-14T12:00:00Z'},
                {window: 'current_week', used_percent: 21, reset_at: '2026-05-19T00:00:00Z'},
            ],
        },
        {
            id: 'claude-work',
            provider: 'claude',
            label: 'Claude Work',
            state: 'stale',
            error: {code: 'auth_expired', message: 'expired'},
            usage: [
                {window: 'current_session', used_percent: 92, reset_at: '2026-05-14T18:00:00Z'},
                {window: 'current_week', used_percent: 80, reset_at: '2026-05-19T00:00:00Z'},
                {window: 'week_fable', label: 'Week Fable', used_percent: 10, reset_at: null},
            ],
        },
        {
            id: 'claude-priv',
            provider: 'claude',
            label: 'Claude Priv',
            state: 'ok',
            usage: [],
        },
    ],
};

const view = normalizeProfiles(data, 'claude-work');

assertEqual(view.primary.id, 'claude-work', 'primary profile matches requested id');
assertEqual(view.profiles[0].shortWindow.usedPercent, 36, 'codex short window maps from five_hour');
assertEqual(view.profiles[1].shortWindow.severity, 'critical', 'short window >= 90 is critical');
assertEqual(view.profiles[1].weekWindow.severity, 'warning', 'week window >= 75 is warning');
assertEqual(view.profiles[1].stale, true, 'non-ok state is stale');
assertEqual(view.profiles[1].windows.map(w => w.label), ['Session (5h)', 'Week', 'Week Fable'], 'all windows get labels');

assertEqual(panelProfiles(view, []).map(p => p.id), ['claude-work', 'codex-main'], 'default panel shows first per provider');
assertEqual(panelProfiles(view, ['claude-priv', 'missing']).map(p => p.id), ['claude-priv'], 'explicit panel ids win');
assertEqual(togglePanelId(view, [], 'claude-priv'), ['claude-work', 'codex-main', 'claude-priv'], 'toggle adds to defaults');
assertEqual(togglePanelId(view, ['claude-priv', 'codex-main'], 'claude-priv'), ['codex-main'], 'toggle removes');

assertEqual(view.profiles.map(p => p.group), ['main', 'work', 'priv'], 'group is the profile name without the provider');

const accounts = normalizeProfiles({
    profiles: ['claude-work', 'claude-home', 'codex-work', 'codex-home', 'codex-solo', 'odd'].map(id => ({
        id,
        provider: id.startsWith('codex') ? 'codex' : 'claude',
        state: 'ok',
        usage: [],
    })),
}, '');
const groups = groupProfiles(accounts.profiles);

assertEqual(groups.map(g => g.key), ['work', 'home', 'solo', 'odd'], 'groups keep the order of first appearance');
assertEqual(groups.map(g => g.profiles.map(p => p.id)),
    [['claude-work', 'codex-work'], ['claude-home', 'codex-home'], ['codex-solo'], ['odd']],
    'claude-X and codex-X share a group');
assertEqual(groups.map(g => g.color), [null, '#dc8add', '#99c1f1', '#8ff0a4'], 'first group keeps the default color');
assertEqual(groups.map(g => g.custom), [false, false, false, false], 'auto colors are not custom');

const custom = groupProfiles(accounts.profiles, {work: '#62A0EA', home: 'red', ghost: '#000000'});

assertEqual(custom.map(g => g.color), ['#62a0ea', '#dc8add', '#99c1f1', '#8ff0a4'], 'valid custom colors win, invalid ones fall back');
assertEqual(custom.map(g => g.custom), [true, false, false, false], 'custom flag marks overrides');
assertEqual(custom[0].autoColor, null, 'auto color stays available for a reset');

assertEqual(formatDuration(3 * 86400 + 2 * 3600), '3d 2h', 'days format');
assertEqual(formatDuration(3700), '1h 1m', 'hours format');
assertEqual(formatResetIn('2026-05-14T12:30:00Z', Date.parse('2026-05-14T12:00:00Z')), 'resets in 30m', 'reset in');
assertEqual(formatResetIn(null), null, 'missing reset');

const degraded = normalizeProfiles({profiles: []}, 'missing');

assertEqual(degraded.primary, null, 'empty input has no primary');

const mixed = normalizeProfiles({
    profiles: ['claude-erli', 'claude-priv', 'codex-erli', 'codex-priv', 'codex-spare'].map(id => ({
        id,
        provider: id.split('-')[0],
        state: 'ok',
        usage: [],
    })),
}, '');
const menu = menuGroups(mixed, ['claude-erli', 'codex-erli', 'claude-priv'], {spare: '#62a0ea'});

assertEqual(menu.map(g => g.profiles.map(p => p.id)),
    [['claude-erli', 'codex-erli'], ['claude-priv', 'codex-priv'], ['codex-spare']],
    'menu lists top bar groups first, profiles off the bar join their group');
assertEqual(menu.map(g => g.color), [null, '#dc8add', '#62a0ea'], 'menu groups use the top bar colors');

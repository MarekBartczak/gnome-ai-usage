import GLib from 'gi://GLib';

import readStatusFile, {
    readStatusFile as namedReadStatusFile,
    readStatusFileAsync,
    sanitizeStatusData,
} from '../../gnome-extension/ai-usage@marekbartczak.github.io/lib/statusReader.js';

function assertEqual(actual, expected, message) {
    if (actual !== expected)
        throw new Error(`${message}: expected ${expected}, got ${actual}`);
}

const tempDir = GLib.dir_make_tmp('ai-usage-test-XXXXXX');
const statusPath = GLib.build_filenamev([tempDir, 'status.json']);
const statusData = {
    updated_at: '2026-05-14T10:00:00Z',
    profiles: [
        {
            id: 'codex-main',
            provider: 'codex',
            label: 'Codex Main',
            state: 'ok',
            usage: [],
        },
    ],
};

GLib.file_set_contents(statusPath, JSON.stringify(statusData));

const result = readStatusFile(statusPath);

assertEqual(readStatusFile, namedReadStatusFile, 'default and named exports point to the same function');
assertEqual(result.ok, true, 'status file read succeeds');
assertEqual(result.error, undefined, 'successful read does not include an error');
assertEqual(result.data.updated_at, '2026-05-14T10:00:00Z', 'status file preserves updated_at');
assertEqual(result.data.profiles[0].id, 'codex-main', 'status file preserves profile id');

const brokenPath = GLib.build_filenamev([tempDir, 'broken.json']);

GLib.file_set_contents(brokenPath, '{not-json');

const broken = readStatusFile(brokenPath);

assertEqual(broken.ok, false, 'invalid JSON returns an error result');
assertEqual(broken.data.profiles.length, 0, 'invalid JSON falls back to an empty profile list');
assertEqual(broken.data.updated_at, null, 'invalid JSON falls back to null updated_at');

const asyncResult = await readStatusFileAsync(statusPath);

assertEqual(asyncResult.ok, true, 'async status file read succeeds');
assertEqual(asyncResult.data.updated_at, '2026-05-14T10:00:00Z', 'async status file preserves updated_at');

const asyncBroken = await readStatusFileAsync(brokenPath);

assertEqual(asyncBroken.ok, false, 'async invalid JSON returns an error result');
assertEqual(asyncBroken.data.profiles.length, 0, 'async invalid JSON falls back to an empty profile list');

const sanitized = sanitizeStatusData({
    updated_at: '2026-05-14T12:00:00Z',
    profiles: [
        null,
        {
            id: 'claude-work',
            provider: 'claude',
            label: 'Claude Work',
            usage: [null, {window: 'current_session', used_percent: 77}],
        },
        'bad-profile',
    ],
});

assertEqual(sanitized.updated_at, '2026-05-14T12:00:00Z', 'sanitize preserves updated_at');
assertEqual(sanitized.profiles.length, 1, 'sanitize drops malformed profile entries');
assertEqual(sanitized.profiles[0].usage.length, 1, 'sanitize drops malformed usage entries');

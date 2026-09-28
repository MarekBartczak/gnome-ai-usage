import {replaceRefreshTimer} from '../../gnome-extension/ai-usage@marekbartczak.github.io/lib/refreshScheduler.js';

function assertEqual(actual, expected, message) {
    if (actual !== expected)
        throw new Error(`${message}: expected ${expected}, got ${actual}`);
}

const cancelled = [];
const scheduled = [];

const nextId = replaceRefreshTimer(
    17,
    30,
    sourceId => cancelled.push(sourceId),
    (seconds, callback) => {
        scheduled.push({seconds, callbackType: typeof callback});
        return 18;
    },
    () => true
);

assertEqual(cancelled.length, 1, 'existing timer is cancelled');
assertEqual(cancelled[0], 17, 'existing timer id is passed to cancel');
assertEqual(scheduled.length, 1, 'new timer is scheduled');
assertEqual(scheduled[0].seconds, 30, 'new timer uses requested interval');
assertEqual(scheduled[0].callbackType, 'function', 'new timer receives a callback');
assertEqual(nextId, 18, 'new timer id is returned');

const firstId = replaceRefreshTimer(
    null,
    15,
    sourceId => cancelled.push(sourceId),
    (seconds, callback) => {
        scheduled.push({seconds, callbackType: typeof callback});
        return 19;
    },
    () => true
);

assertEqual(cancelled.length, 1, 'null timer id does not trigger cancellation');
assertEqual(scheduled[1].seconds, 15, 'initial timer schedules requested interval');
assertEqual(firstId, 19, 'initial timer id is returned');

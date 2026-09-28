export function replaceRefreshTimer(currentId, seconds, cancel, schedule, onTick) {
    if (currentId)
        cancel(currentId);

    return schedule(seconds, onTick);
}

import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {providerGicon} from './iconRegistry.js';
import {formatAge, formatResetIn} from './profileModel.js';

function formatWindow(window) {
    if (window.usedPercent === null)
        return `${window.label}: --`;

    const resetIn = formatResetIn(window.resetAt);

    return resetIn
        ? `${window.label}: ${window.usedPercent}%  ·  ${resetIn}`
        : `${window.label}: ${window.usedPercent}%`;
}

function infoItem(text, styleClass = null) {
    const item = new PopupMenu.PopupMenuItem(text, {reactive: false});

    if (styleClass)
        item.label.add_style_class_name(styleClass);

    return item;
}

function profileTitle(profile) {
    const flag = profile.stale ? '  ⚠' : '';

    if (profile.shortWindow.usedPercent === null && profile.weekWindow.usedPercent === null)
        return `${profile.label}${flag}`;

    const short = profile.shortWindow.usedPercent ?? '--';
    const week = profile.weekWindow.usedPercent ?? '--';

    return `${profile.label}   ${short}% · ${week}%${flag}`;
}

// The provider icon in the group color ties each row to its group on the top bar.
function profileItem(profile, color, panelIds, extensionPath, callbacks) {
    const item = new PopupMenu.PopupSubMenuMenuItem(profileTitle(profile), true);
    const gicon = providerGicon(extensionPath, profile.provider);
    const account = [profile.account || 'No account', profile.plan].filter(Boolean).join('  ·  ');

    if (gicon)
        item.icon.gicon = gicon;
    if (color)
        item.icon.style = `color: ${color};`;

    item.menu.addMenuItem(infoItem(account, 'ai-usage-dim'));

    for (const window of profile.windows)
        item.menu.addMenuItem(infoItem(formatWindow(window), `ai-usage-${window.severity}`));

    if (profile.error) {
        const age = formatAge(profile.lastOkAt);
        const prefix = profile.state === 'stale' && age ? `Stale (last OK ${age}): ` : '';

        item.menu.addMenuItem(infoItem(`${prefix}${profile.error.message}`, 'ai-usage-warning'));
    }

    const onPanel = new PopupMenu.PopupSwitchMenuItem(
        'Show on top bar',
        panelIds.includes(profile.id)
    );
    onPanel.connect('toggled', () => callbacks.onTogglePanel(profile.id));
    item.menu.addMenuItem(onPanel);

    return item;
}

export function rebuildMenu(indicator, {view, panelIds, groups, extensionPath}, callbacks) {
    indicator.menu.removeAll();

    if (!view.profiles.length) {
        indicator.menu.addMenuItem(infoItem('No profiles — run: ai-usage setup'));
    }

    groups.forEach((group, index) => {
        if (index > 0)
            indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        for (const profile of group.profiles)
            indicator.menu.addMenuItem(profileItem(profile, group.color, panelIds, extensionPath, callbacks));
    });

    indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

    const age = formatAge(view.updatedAt);
    const refresh = new PopupMenu.PopupMenuItem(age ? `Refresh now  (updated ${age})` : 'Refresh now');
    refresh.connect('activate', () => callbacks.onRefresh());
    indicator.menu.addMenuItem(refresh);
}

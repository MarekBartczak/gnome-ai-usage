import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {providerGicon} from './lib/iconRegistry.js';
import {replaceRefreshTimer} from './lib/refreshScheduler.js';
import {rebuildMenu} from './lib/menuBuilder.js';
import {groupProfiles, menuGroups, normalizeProfiles, panelProfiles, togglePanelId} from './lib/profileModel.js';
import {readStatusFileAsync, statusFilePath} from './lib/statusReader.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const SEVERITY_CLASSES = ['ai-usage-normal', 'ai-usage-warning', 'ai-usage-critical', 'ai-usage-unknown'];

function metricLabel() {
    return new St.Label({
        text: '--',
        style_class: 'ai-usage-metric',
        y_align: Clutter.ActorAlign.CENTER,
    });
}

function setMetric(label, window) {
    label.text = window.usedPercent !== null ? String(window.usedPercent) : '--';

    for (const styleClass of SEVERITY_CLASSES)
        label.remove_style_class_name(styleClass);
    label.add_style_class_name(`ai-usage-${window.severity}`);
}

// A type name per module URL lets a fresh copy load from Looking Glass while the old class stays registered.
const AiUsageIndicator = GObject.registerClass({
    GTypeName: `AiUsageIndicator_${GLib.compute_checksum_for_string(GLib.ChecksumType.SHA256, import.meta.url, -1).slice(0, 12)}`,
}, class AiUsageIndicator extends PanelMenu.Button {
    _init(extensionPath) {
        super._init(0.0, 'AI Usage');
        this._extensionPath = extensionPath;

        this._box = new St.BoxLayout({
            style_class: 'ai-usage-pill',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(this._box);
        this.setGroups([]);
    }

    setGroups(groups) {
        this._box.destroy_all_children();

        if (!groups.length) {
            this._box.add_child(new St.Label({
                text: 'AI --',
                style_class: 'ai-usage-metric ai-usage-unknown',
                y_align: Clutter.ActorAlign.CENTER,
            }));
            return;
        }

        // A lone group is the whole indicator already; a frame only helps to tell several apart.
        const framed = groups.length > 1;

        for (const group of groups) {
            const account = new St.BoxLayout({
                style_class: framed ? 'ai-usage-account ai-usage-account-framed' : 'ai-usage-account',
                y_align: Clutter.ActorAlign.CENTER,
            });

            for (const profile of group.profiles)
                account.add_child(this._profileItem(profile, group.color));
            this._box.add_child(account);
        }
    }

    _profileItem(profile, color) {
        const item = new St.BoxLayout({
            style_class: profile.stale ? 'ai-usage-group ai-usage-stale' : 'ai-usage-group',
            y_align: Clutter.ActorAlign.CENTER,
        });
        const gicon = providerGicon(this._extensionPath, profile.provider);

        if (gicon) {
            const icon = new St.Icon({
                gicon,
                icon_size: 16,
                style_class: 'system-status-icon ai-usage-icon',
                y_align: Clutter.ActorAlign.CENTER,
            });

            if (color)
                icon.style = `color: ${color};`;
            item.add_child(icon);
        }

        const shortLabel = metricLabel();
        const weekLabel = metricLabel();

        setMetric(shortLabel, profile.shortWindow);
        setMetric(weekLabel, profile.weekWindow);
        weekLabel.add_style_class_name('ai-usage-week');
        item.add_child(shortLabel);
        item.add_child(weekLabel);
        return item;
    }
});

export default class AiUsageExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._indicator = new AiUsageIndicator(this.path);
        this._reloadGeneration = 0;
        this._view = normalizeProfiles({profiles: [], updated_at: null}, '');
        Main.panel.addToStatusArea(this.uuid, this._indicator, 0, 'right');
        this._indicator.menu.connect('open-state-changed', (_menu, isOpen) => {
            if (!isOpen && this._menuDirty)
                this._render();
        });

        this._settingsChangedIds = [
            this._settings.connect('changed::refresh-interval-seconds', () => this._restartRefreshTimer()),
            this._settings.connect('changed::status-file-path', () => this._restartMonitor()),
            this._settings.connect('changed::panel-profile-ids', () => this._render()),
            this._settings.connect('changed::group-colors', () => this._render()),
        ];
        this._restartMonitor();
        this._restartRefreshTimer();
    }

    disable() {
        for (const id of this._settingsChangedIds ?? [])
            this._settings.disconnect(id);
        this._settingsChangedIds = null;

        this._stopMonitor();

        if (this._refreshSourceId) {
            GLib.source_remove(this._refreshSourceId);
            this._refreshSourceId = null;
        }

        this._indicator?.destroy();
        this._indicator = null;
        this._reloadGeneration += 1;
        this._settings = null;
        this._view = null;
    }

    _stopMonitor() {
        if (this._monitorChangedId) {
            this._monitor.disconnect(this._monitorChangedId);
            this._monitorChangedId = null;
        }
        this._monitor?.cancel();
        this._monitor = null;
    }

    // The backend writes status.json atomically (rename), so watching the file reacts immediately.
    _restartMonitor() {
        this._stopMonitor();

        const file = Gio.File.new_for_path(statusFilePath(this._settings));

        try {
            this._monitor = file.monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, null);
            this._monitorChangedId = this._monitor.connect('changed', () => void this._reload());
        } catch (error) {
            console.warn(`ai-usage: cannot monitor status file: ${error.message}`);
        }

        void this._reload();
    }

    _restartRefreshTimer() {
        if (!this._settings)
            return;

        const seconds = Math.max(1, this._settings.get_uint('refresh-interval-seconds'));

        this._refreshSourceId = replaceRefreshTimer(
            this._refreshSourceId,
            seconds,
            sourceId => GLib.source_remove(sourceId),
            (intervalSeconds, onTick) => GLib.timeout_add_seconds(
                GLib.PRIORITY_DEFAULT,
                intervalSeconds,
                onTick
            ),
            () => {
                void this._reload();
                return GLib.SOURCE_CONTINUE;
            }
        );
    }

    _runRefreshCommand() {
        const command = this._settings?.get_string('refresh-command');

        if (!command)
            return;

        try {
            const [, argv] = GLib.shell_parse_argv(command);
            const proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);

            proc.wait_async(null, () => void this._reload());
        } catch (error) {
            console.warn(`ai-usage: refresh command failed: ${error.message}`);
        }
    }

    _render() {
        if (!this._settings || !this._indicator || !this._view)
            return;

        const panelIds = panelProfiles(this._view, this._settings.get_strv('panel-profile-ids'))
            .map(profile => profile.id);

        const groupColors = this._settings.get_value('group-colors').recursiveUnpack();

        this._indicator.setGroups(groupProfiles(panelProfiles(this._view, panelIds), groupColors));

        if (this._indicator.menu.isOpen) {
            this._menuDirty = true;
            return;
        }
        this._menuDirty = false;
        rebuildMenu(this._indicator, {
            view: this._view,
            panelIds,
            groups: menuGroups(this._view, panelIds, groupColors),
            extensionPath: this.path,
        }, {
            onTogglePanel: profileId => {
                this._settings.set_strv(
                    'panel-profile-ids',
                    togglePanelId(this._view, this._settings.get_strv('panel-profile-ids'), profileId)
                );
            },
            onRefresh: () => this._runRefreshCommand(),
        });
    }

    async _reload() {
        if (!this._settings || !this._indicator)
            return;

        const generation = ++this._reloadGeneration;
        const result = await readStatusFileAsync(statusFilePath(this._settings));

        if (!this._settings || !this._indicator || generation !== this._reloadGeneration)
            return;

        try {
            this._view = normalizeProfiles(result.data, '');
        } catch (_error) {
            this._view = normalizeProfiles({profiles: [], updated_at: null}, '');
        }

        this._render();
    }
}

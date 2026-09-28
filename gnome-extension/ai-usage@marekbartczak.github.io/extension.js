import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {iconPath} from './lib/iconRegistry.js';
import {replaceRefreshTimer} from './lib/refreshScheduler.js';
import {rebuildMenu} from './lib/menuBuilder.js';
import {normalizeProfiles, panelProfiles, togglePanelId} from './lib/profileModel.js';
import {readStatusFileAsync} from './lib/statusReader.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

function statusFilePath(settings) {
    return settings.get_string('status-file-path') ||
        GLib.build_filenamev([GLib.get_user_data_dir(), 'ai-usage-module', 'status.json']);
}

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

const AiUsageIndicator = GObject.registerClass(
class AiUsageIndicator extends PanelMenu.Button {
    _init(extensionPath) {
        super._init(0.0, 'AI Usage');
        this._extensionPath = extensionPath;

        this._box = new St.BoxLayout({
            style_class: 'ai-usage-pill',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(this._box);
        this.setProfiles([]);
    }

    setProfiles(profiles) {
        this._box.destroy_all_children();

        if (!profiles.length) {
            this._box.add_child(new St.Label({
                text: 'AI --',
                style_class: 'ai-usage-metric ai-usage-unknown',
                y_align: Clutter.ActorAlign.CENTER,
            }));
            return;
        }

        for (const profile of profiles) {
            const group = new St.BoxLayout({
                style_class: profile.stale ? 'ai-usage-group ai-usage-stale' : 'ai-usage-group',
                y_align: Clutter.ActorAlign.CENTER,
            });
            const providerIconPath = iconPath(this._extensionPath, profile.provider);

            if (providerIconPath) {
                group.add_child(new St.Icon({
                    gicon: Gio.FileIcon.new(Gio.File.new_for_path(providerIconPath)),
                    icon_size: 16,
                    style_class: 'system-status-icon ai-usage-icon',
                    y_align: Clutter.ActorAlign.CENTER,
                }));
            }

            const shortLabel = metricLabel();
            const weekLabel = metricLabel();

            setMetric(shortLabel, profile.shortWindow);
            setMetric(weekLabel, profile.weekWindow);
            weekLabel.add_style_class_name('ai-usage-week');
            group.add_child(shortLabel);
            group.add_child(weekLabel);
            this._box.add_child(group);
        }
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

        this._indicator.setProfiles(panelProfiles(this._view, panelIds));

        if (this._indicator.menu.isOpen) {
            this._menuDirty = true;
            return;
        }
        this._menuDirty = false;
        rebuildMenu(this._indicator, this._view, panelIds, {
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

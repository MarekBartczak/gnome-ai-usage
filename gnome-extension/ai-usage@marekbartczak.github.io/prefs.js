import Adw from 'gi://Adw';
import Gdk from 'gi://Gdk';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';
import {
    MAX_REFRESH_INTERVAL_SECONDS,
    MIN_REFRESH_INTERVAL_SECONDS,
    normalizeRefreshInterval,
    normalizeStatusFilePath,
    rgbaToHex,
    withGroupColor,
} from './lib/prefsModel.js';
import {groupProfiles, normalizeProfiles, panelProfiles} from './lib/profileModel.js';
import {readStatusFile, statusFilePath} from './lib/statusReader.js';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

// What an uncolored group looks like on the (dark) top bar.
const PANEL_COLOR = '#ffffff';

function hexToRgba(hex) {
    const rgba = new Gdk.RGBA();

    rgba.parse(hex);
    return rgba;
}

function readGroupColors(settings) {
    return settings.get_value('group-colors').recursiveUnpack();
}

function writeGroupColor(settings, groupKey, color) {
    settings.set_value('group-colors', new GLib.Variant('a{ss}', withGroupColor(readGroupColors(settings), groupKey, color)));
}

function groupColorRow(settings, group) {
    const row = new Adw.ActionRow({
        title: group.key,
        subtitle: group.profiles.map(profile => profile.label).join(', '),
    });
    const button = new Gtk.ColorDialogButton({
        dialog: new Gtk.ColorDialog({with_alpha: false}),
        rgba: hexToRgba(group.color ?? PANEL_COLOR),
        valign: Gtk.Align.CENTER,
    });
    const reset = new Gtk.Button({
        icon_name: 'edit-undo-symbolic',
        tooltip_text: 'Use the automatic color',
        valign: Gtk.Align.CENTER,
        css_classes: ['flat'],
        sensitive: group.custom,
    });
    let resetting = false;

    button.connect('notify::rgba', () => {
        if (resetting)
            return;
        writeGroupColor(settings, group.key, rgbaToHex(button.rgba));
        reset.sensitive = true;
    });
    reset.connect('clicked', () => {
        writeGroupColor(settings, group.key, null);
        resetting = true;
        button.rgba = hexToRgba(group.autoColor ?? PANEL_COLOR);
        resetting = false;
        reset.sensitive = false;
    });

    row.add_suffix(reset);
    row.add_suffix(button);
    return row;
}

function groupColorsGroup(settings) {
    const prefsGroup = new Adw.PreferencesGroup({
        title: 'Top bar colors',
        description: 'Profiles that share a name (claude-work, codex-work) form one group on the top bar. The group color tints its icons.',
    });
    const view = normalizeProfiles(readStatusFile(statusFilePath(settings)).data, '');
    const groups = groupProfiles(panelProfiles(view, settings.get_strv('panel-profile-ids')), readGroupColors(settings));

    if (!groups.length)
        prefsGroup.add(new Adw.ActionRow({title: 'No profiles on the top bar yet'}));

    for (const group of groups)
        prefsGroup.add(groupColorRow(settings, group));

    return prefsGroup;
}

export default class AiUsagePrefs extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();
        const page = new Adw.PreferencesPage();
        const group = new Adw.PreferencesGroup({title: 'AI Usage'});
        const initialPath = settings.get_string('status-file-path');

        const pathRow = new Adw.EntryRow({title: 'Status file path (empty = default)'});
        pathRow.text = initialPath;
        pathRow.connect('changed', row => {
            const text = row.text.trim();
            const normalized = text ? normalizeStatusFilePath(text, initialPath) : '';

            if (normalized === text) {
                settings.set_string('status-file-path', normalized);
                row.remove_css_class('error');
            } else {
                row.add_css_class('error');
            }
        });

        const intervalRow = new Adw.SpinRow({
            title: 'Reload interval (seconds)',
            adjustment: new Gtk.Adjustment({
                lower: MIN_REFRESH_INTERVAL_SECONDS,
                upper: MAX_REFRESH_INTERVAL_SECONDS,
                step_increment: 5,
                page_increment: 30,
                value: settings.get_uint('refresh-interval-seconds'),
            }),
        });
        intervalRow.connect('notify::value', row => {
            settings.set_uint('refresh-interval-seconds', normalizeRefreshInterval(row.value));
        });

        const refreshRow = new Adw.EntryRow({title: 'Refresh now command'});
        refreshRow.text = settings.get_string('refresh-command');
        refreshRow.connect('changed', row => settings.set_string('refresh-command', row.text.trim()));

        group.add(pathRow);
        group.add(intervalRow);
        group.add(refreshRow);
        page.add(group);
        page.add(groupColorsGroup(settings));
        window.add(page);
    }
}

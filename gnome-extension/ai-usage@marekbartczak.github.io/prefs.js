import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';
import {
    MAX_REFRESH_INTERVAL_SECONDS,
    MIN_REFRESH_INTERVAL_SECONDS,
    normalizeRefreshInterval,
    normalizeStatusFilePath,
} from './lib/prefsModel.js';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

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
        window.add(page);
    }
}

import Gio from 'gi://Gio';

export function iconPath(extensionPath, provider) {
    let basename = null;

    switch (provider) {
    case 'codex':
        basename = 'openai-symbolic.svg';
        break;
    case 'claude':
        basename = 'claude-symbolic.svg';
        break;
    default:
        return null;
    }

    return Gio.File.new_for_path(`${extensionPath}/icons/${basename}`).get_path();
}

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

export function providerGicon(extensionPath, provider) {
    const path = iconPath(extensionPath, provider);

    return path ? Gio.FileIcon.new(Gio.File.new_for_path(path)) : null;
}

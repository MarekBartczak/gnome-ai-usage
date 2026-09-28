import Gio from 'gi://Gio';

function decodeJson(bytes) {
    const text = new TextDecoder().decode(bytes);
    return JSON.parse(text);
}

function errorResult(error) {
    return {
        ok: false,
        error: error instanceof Error ? error.message : String(error),
        data: {profiles: [], updated_at: null},
    };
}

function sanitizeStatusData(raw) {
    const profiles = Array.isArray(raw?.profiles)
        ? raw.profiles
            .filter(profile => profile && typeof profile === 'object')
            .map(profile => ({
                ...profile,
                usage: Array.isArray(profile.usage)
                    ? profile.usage.filter(item => item && typeof item === 'object')
                    : [],
            }))
        : [];

    return {
        updated_at: raw?.updated_at ?? null,
        profiles,
    };
}

function readStatusFile(path) {
    try {
        const file = Gio.File.new_for_path(path);
        const [, bytes] = file.load_contents(null);
        const data = decodeJson(bytes);

        return {ok: true, data: sanitizeStatusData(data)};
    } catch (error) {
        return errorResult(error);
    }
}

async function readStatusFileAsync(path) {
    const file = Gio.File.new_for_path(path);

    try {
        const bytes = await new Promise((resolve, reject) => {
            file.load_contents_async(null, (source, result) => {
                try {
                    const [, contents] = source.load_contents_finish(result);
                    resolve(contents);
                } catch (error) {
                    reject(error);
                }
            });
        });

        return {ok: true, data: sanitizeStatusData(decodeJson(bytes))};
    } catch (error) {
        return errorResult(error);
    }
}

export {readStatusFile, readStatusFileAsync, sanitizeStatusData};
export default readStatusFile;

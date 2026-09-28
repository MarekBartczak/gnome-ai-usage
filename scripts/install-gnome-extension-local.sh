#!/usr/bin/env bash
set -euo pipefail

UUID="ai-usage@marekbartczak.github.io"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SRC_DIR="${REPO_ROOT}/gnome-extension/${UUID}"
DEST_DIR="${HOME}/.local/share/gnome-shell/extensions/${UUID}"

if [[ ! -d "${SRC_DIR}" ]]; then
    echo "Missing extension source directory: ${SRC_DIR}" >&2
    exit 1
fi

if [[ ! -d "${SRC_DIR}/schemas" ]]; then
    echo "Missing schema directory: ${SRC_DIR}/schemas" >&2
    exit 1
fi

if ! command -v glib-compile-schemas >/dev/null 2>&1; then
    echo "Missing required tool: glib-compile-schemas" >&2
    exit 1
fi

mkdir -p "$(dirname "${DEST_DIR}")"
rm -rf "${DEST_DIR}"
mkdir -p "${DEST_DIR}"
cp -a "${SRC_DIR}/." "${DEST_DIR}/"
glib-compile-schemas "${DEST_DIR}/schemas"

echo "Installed to ${DEST_DIR}"
echo "Enable with: gnome-extensions enable ${UUID}"
echo "Open prefs with: gnome-extensions prefs ${UUID}"

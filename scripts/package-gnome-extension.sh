#!/usr/bin/env bash
set -euo pipefail

UUID="ai-usage@marekbartczak.github.io"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
EXTENSION_DIR="${REPO_ROOT}/gnome-extension/${UUID}"
OUT_DIR="${REPO_ROOT}/dist"
EXTRA_SOURCES=()

mkdir -p "${OUT_DIR}"
glib-compile-schemas "${EXTENSION_DIR}/schemas"

if [[ -d "${EXTENSION_DIR}/lib" ]]; then
    EXTRA_SOURCES+=("--extra-source=lib")
fi

if [[ -d "${EXTENSION_DIR}/icons" ]]; then
    EXTRA_SOURCES+=("--extra-source=icons")
fi

(
    cd "${EXTENSION_DIR}"
    gnome-extensions pack . --out-dir "${OUT_DIR}" --force "${EXTRA_SOURCES[@]}"
)
echo "Created package in $OUT_DIR"

#!/usr/bin/env bash
# Builds dist/gnome-ai-usage_<version>_all.deb (plus a stable-name copy for /releases/latest/download).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UUID="ai-usage@marekbartczak.github.io"
VERSION="${VERSION:-$(sed -n 's/^version = "\(.*\)"/\1/p' "${REPO_ROOT}/pyproject.toml")}"
VERSION="${VERSION#v}"
OUT_DIR="${REPO_ROOT}/dist"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

PKG="${STAGE}/pkg"
mkdir -p "${PKG}/DEBIAN" "${PKG}/usr/bin" "${PKG}/usr/lib/ai-usage" \
    "${PKG}/usr/lib/systemd/user" "${PKG}/usr/share/gnome-shell/extensions" \
    "${PKG}/usr/share/doc/gnome-ai-usage"

cp -r "${REPO_ROOT}/src/ai_usage" "${PKG}/usr/lib/ai-usage/"
find "${PKG}/usr/lib/ai-usage" -name '__pycache__' -prune -exec rm -rf {} +

cat > "${PKG}/usr/bin/ai-usage" <<'SH'
#!/bin/sh
PYTHONPATH=/usr/lib/ai-usage${PYTHONPATH:+:$PYTHONPATH} exec python3 -m ai_usage "$@"
SH
chmod 755 "${PKG}/usr/bin/ai-usage"

EXT_DIR="${PKG}/usr/share/gnome-shell/extensions/${UUID}"
cp -r "${REPO_ROOT}/gnome-extension/${UUID}" "${EXT_DIR}"
glib-compile-schemas "${EXT_DIR}/schemas"

cat > "${PKG}/usr/lib/systemd/user/ai-usage-probe.service" <<'UNIT'
[Unit]
Description=Probe Claude and Codex usage limits
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/ai-usage probe
UNIT

cat > "${PKG}/usr/lib/systemd/user/ai-usage-probe.timer" <<'UNIT'
[Unit]
Description=Probe Claude and Codex usage limits periodically

[Timer]
OnStartupSec=30s
OnUnitActiveSec=5min
AccuracySec=30s

[Install]
WantedBy=timers.target
UNIT

cp "${REPO_ROOT}/LICENSE" "${PKG}/usr/share/doc/gnome-ai-usage/copyright"

cat > "${PKG}/DEBIAN/control" <<CONTROL
Package: gnome-ai-usage
Version: ${VERSION}
Section: gnome
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), gnome-shell (>= 45)
Maintainer: Marek Bartczak <noreply@github.com>
Homepage: https://github.com/MarekBartczak/gnome-ai-usage
Description: Claude Code and Codex CLI usage limits on the GNOME top bar
 Reads the OAuth tokens of already logged-in Claude Code and Codex CLIs and
 shows the 5-hour and weekly usage percentages in the GNOME Shell top bar.
 After installing, run "ai-usage setup" as your normal user.
CONTROL

cat > "${PKG}/DEBIAN/postinst" <<'SH'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    echo "gnome-ai-usage installed. As your normal user run:  ai-usage setup"
fi
SH
chmod 755 "${PKG}/DEBIAN/postinst"

chmod -R u=rwX,go=rX "${PKG}"
chmod 755 "${PKG}/usr/bin/ai-usage" "${PKG}/DEBIAN/postinst"
mkdir -p "${OUT_DIR}"
DEB="${OUT_DIR}/gnome-ai-usage_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "${PKG}" "${DEB}" >/dev/null
cp "${DEB}" "${OUT_DIR}/gnome-ai-usage.deb"
echo "${DEB}"

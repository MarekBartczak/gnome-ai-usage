#!/usr/bin/env bash
# Adds .deb files to a flat-pool APT repository and (re)signs it.
# Usage: build-apt-repo.sh <repo dir> <deb>...   (signing key must be in the default gpg keyring)
set -euo pipefail

REPO="$1"
shift
mkdir -p "${REPO}/pool/main"
cp "$@" "${REPO}/pool/main/"
rm -f "${REPO}/pool/main/gnome-ai-usage.deb"   # stable-name copy, not a separate version

cd "${REPO}"
rm -rf dists
for arch in all amd64 arm64; do
    mkdir -p "dists/stable/main/binary-${arch}"
    apt-ftparchive packages pool > "dists/stable/main/binary-${arch}/Packages"
    gzip -9kf "dists/stable/main/binary-${arch}/Packages"
done

apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=gnome-ai-usage \
    -o APT::FTPArchive::Release::Label=gnome-ai-usage \
    -o APT::FTPArchive::Release::Suite=stable \
    -o APT::FTPArchive::Release::Codename=stable \
    -o APT::FTPArchive::Release::Architectures="all amd64 arm64" \
    -o APT::FTPArchive::Release::Components=main \
    release dists/stable > dists/stable/Release

gpg --batch --yes --clearsign -o dists/stable/InRelease dists/stable/Release
gpg --batch --yes --armor --detach-sign -o dists/stable/Release.gpg dists/stable/Release
echo "APT repo updated in ${REPO}: $(ls pool/main | tr '\n' ' ')"

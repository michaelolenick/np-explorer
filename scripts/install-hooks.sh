#!/bin/sh
# Install the gitleaks pre-commit hook: a pinned, checksum-verified gitleaks in
# .venv/bin (if none is on PATH) and git's hooksPath pointed at .githooks/.
set -eu
VERSION=8.21.2
ROOT="$(git rev-parse --show-toplevel)"
BIN="$ROOT/.venv/bin"

if ! command -v gitleaks >/dev/null 2>&1 && [ ! -x "$BIN/gitleaks" ]; then
    case "$(uname -s)-$(uname -m)" in
        Linux-x86_64) PLATFORM=linux_x64 ;;
        Linux-aarch64) PLATFORM=linux_arm64 ;;
        Darwin-x86_64) PLATFORM=darwin_x64 ;;
        Darwin-arm64) PLATFORM=darwin_arm64 ;;
        *) echo "install gitleaks $VERSION yourself: https://github.com/gitleaks/gitleaks/releases" >&2; exit 1 ;;
    esac
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    BASE="https://github.com/gitleaks/gitleaks/releases/download/v$VERSION"
    TARBALL="gitleaks_${VERSION}_${PLATFORM}.tar.gz"
    curl -sSfL -o "$TMP/$TARBALL" "$BASE/$TARBALL"
    curl -sSfL -o "$TMP/checksums.txt" "$BASE/gitleaks_${VERSION}_checksums.txt"
    (cd "$TMP" && grep " $TARBALL\$" checksums.txt | sha256sum -c - >/dev/null 2>&1 \
        || grep " $TARBALL\$" checksums.txt | shasum -a 256 -c - >/dev/null)
    mkdir -p "$BIN"
    tar -xzf "$TMP/$TARBALL" -C "$BIN" gitleaks
    echo "installed gitleaks $VERSION to $BIN/gitleaks"
fi

git -C "$ROOT" config core.hooksPath .githooks
echo "pre-commit hook active: commits are scanned with gitleaks"

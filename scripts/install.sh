#!/usr/bin/env bash
# Install the latest monday-axi single-file build onto your PATH.
# Needs curl and a Python 3.10+ interpreter. No gh CLI, no token (public repo).
#
#   curl -fsSL https://raw.githubusercontent.com/craig-ai-tooling/monday-axi/main/scripts/install.sh | bash
#   BIN=/usr/local/bin/monday-axi ./scripts/install.sh   # custom target
set -euo pipefail

REPO="craig-ai-tooling/monday-axi"
BIN="${BIN:-$HOME/.local/bin/monday-axi}"
URL="https://github.com/${REPO}/releases/latest/download/monday-axi.pyz"

mkdir -p "$(dirname "$BIN")"
curl -fsSL "$URL" -o "$BIN"
chmod +x "$BIN"
"$BIN" --help >/dev/null
echo "installed $BIN"
echo "next: $BIN doctor"

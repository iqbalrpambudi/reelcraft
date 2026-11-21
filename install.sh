#!/bin/sh
# Reelcraft installer for macOS and Linux.
#   curl -LsSf https://raw.githubusercontent.com/iqbalrpambudi/reelcraft/main/install.sh | sh
#   ... | sh -s -- --service      also start it in the background at every login
# REELCRAFT_VERSION=v1.0.0 pins a release; REELCRAFT_WHEEL=<path or URL> installs that wheel.
set -eu

REPO="iqbalrpambudi/reelcraft"
SERVICE=0
for arg in "$@"; do
  case "$arg" in
    --service) SERVICE=1 ;;
    *) echo "Opsi tidak dikenal: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1m==>\033[0m %s\n' "$1"; }
fail() { printf '\033[31m%s\033[0m\n' "$1" >&2; exit 1; }

case "$(uname -s)" in
  Darwin | Linux) ;;
  *) fail "Installer ini untuk macOS dan Linux. Di Windows, pakai WSL." ;;
esac

# 1. uv: installs Python 3.12 and keeps reelcraft in its own environment
if ! command -v uv >/dev/null 2>&1; then
  say "Memasang uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || fail "uv terpasang tapi tidak ada di PATH. Buka terminal baru lalu ulangi."
fi

# 2. ffmpeg: every step from analysis to render uses it
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    say "Memasang ffmpeg (Homebrew)"
    brew install ffmpeg
  elif command -v apt-get >/dev/null 2>&1; then
    say "Memasang ffmpeg (apt, butuh sudo)"
    sudo apt-get update && sudo apt-get install -y ffmpeg
  elif command -v dnf >/dev/null 2>&1; then
    say "Memasang ffmpeg (dnf, butuh sudo)"
    sudo dnf install -y ffmpeg
  else
    fail "ffmpeg belum ada. Pasang dulu (https://ffmpeg.org/download.html), lalu ulangi."
  fi
fi

# 3. The wheel from a GitHub release: it carries the web dashboard, a git checkout does not
WHEEL="${REELCRAFT_WHEEL:-}"
if [ -z "$WHEEL" ]; then
  if [ -n "${REELCRAFT_VERSION:-}" ]; then
    API="https://api.github.com/repos/$REPO/releases/tags/$REELCRAFT_VERSION"
  else
    API="https://api.github.com/repos/$REPO/releases/latest"
  fi
  WHEEL=$(curl -fsSL "$API" | grep -o '"browser_download_url": *"[^"]*\.whl"' | head -n 1 | sed 's/.*"\(https[^"]*\)"/\1/') \
    || true
  [ -n "$WHEEL" ] || fail "Rilis Reelcraft tidak ditemukan di github.com/$REPO/releases."
fi
say "Memasang Reelcraft dari $WHEEL"
uv tool install --force --python 3.12 "$WHEEL"

BIN="$(uv tool dir --bin)"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) uv tool update-shell >/dev/null 2>&1 || true
     PATH="$BIN:$PATH"
     say "Folder $BIN ditambahkan ke PATH; berlaku di terminal baru." ;;
esac

# 4. Check, and optionally run in the background
reelcraft doctor || true
if [ "$SERVICE" = 1 ]; then
  reelcraft service install
  echo
  say "Selesai. Buka http://127.0.0.1:8765 lalu isi API key di Settings."
else
  echo
  say "Selesai. Jalankan: reelcraft serve"
  echo "    (atau 'reelcraft service install' agar menyala otomatis saat login)"
fi

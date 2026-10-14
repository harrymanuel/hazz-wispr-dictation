#!/bin/zsh
# Build "Hazz Wispr.app" in the project folder.
#
# Only needs re-running if you move the project folder: the app runs the Python
# code from here, so code changes just need an app restart. Rebuilding changes
# the app's signature, so macOS will ask for its permissions again.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/Hazz Wispr.app"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$ROOT/macos/Info.plist" "$APP/Contents/Info.plist"

# Try the default SDK first, then older ones (a newer SDK than the installed
# linker understands fails with "tapi error: unknown architecture").
compiled=0
for sdk in "" $(ls -d /Library/Developer/CommandLineTools/SDKs/MacOSX[0-9]*.sdk 2>/dev/null | sort -rV); do
  sysroot=()
  [[ -n $sdk ]] && sysroot=(-isysroot "$sdk")
  if clang -O2 -Wall "${sysroot[@]}" -DPROJECT_DIR="\"$ROOT\"" \
       -o "$APP/Contents/MacOS/HazzWispr" "$ROOT/macos/launcher.c" 2>/dev/null; then
    compiled=1
    break
  fi
done
if [[ $compiled != 1 ]]; then
  echo "Could not compile the launcher. Try: xcode-select --install" >&2
  exit 1
fi

# App icon: draw at 1024px, then scale into an .icns.
"$ROOT/.venv/bin/python" "$ROOT/macos/make_icon.py" "$TMP/icon.png"
ICONSET="$TMP/AppIcon.iconset"
mkdir "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$TMP/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$TMP/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"

# Ad-hoc signature so macOS can remember the app's permissions.
codesign --force --sign - "$APP"
echo "Built $APP"

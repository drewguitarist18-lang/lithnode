#!/bin/sh
# Builds Lithnode for Linux or Mac (Windows: installer/build.ps1). CI runs this; see .github/workflows/build.yml.
#   packaging/build.sh linux          -> packaging/linux/stage (what the Flatpak manifest packs)
#   packaging/build.sh mac arm64      -> dist/Lithnode-mac-arm64.dmg
# Needs Python 3 and Node.js. Run it from anywhere.
set -eu
cd "$(dirname "$0")/.."
ROOT=$(pwd)
TARGET=${1:?linux or mac}
ARCH=${2:-x64}

# 1. the engine (Python, bundled with PyInstaller) -> dist/Lithnode
python3 -m pip install -q pyinstaller
python3 installer/make_icon.py
python3 -m PyInstaller --noconfirm --clean --log-level WARN --distpath dist --workpath build installer/lithnode.spec

# 2. the window (Electron)
cp installer/lithnode.png installer/app/lithnode.png
cd installer/app
npm ci --no-fund --no-audit
if [ "$TARGET" = mac ]; then
  ICONSET=$ROOT/build/lithnode.iconset
  rm -rf "$ICONSET"; mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$ROOT/installer/lithnode.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    sips -z $((s * 2)) $((s * 2)) "$ROOT/installer/lithnode.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$ROOT/build/lithnode.icns"
  npx --no-install electron-packager . Lithnode --platform=darwin --arch="$ARCH" --out="$ROOT/dist" --overwrite --asar \
    --icon="$ROOT/build/lithnode.icns" --app-bundle-id=com.lithnode.Lithnode --app-category-type=public.app-category.developer-tools \
    "--ignore=^/node_modules" "--ignore=^/package-lock.json"
else
  npx --no-install electron-packager . Lithnode --platform=linux --arch="$ARCH" --out="$ROOT/dist" --overwrite --asar \
    "--ignore=^/node_modules" "--ignore=^/package-lock.json"
fi
rm -f lithnode.png
cd "$ROOT"

if [ "$TARGET" = mac ]; then
  # 3. the engine goes inside the app, then one ad-hoc signature over all of it, then the disk image
  APP="dist/Lithnode-darwin-$ARCH/Lithnode.app"
  rm -rf "$APP/Contents/Resources/server"
  cp -R dist/Lithnode "$APP/Contents/Resources/server"
  codesign --force --deep --sign - "$APP"
  codesign --verify --deep "$APP"
  rm -f "dist/Lithnode-mac-$ARCH.dmg"
  hdiutil create -volname Lithnode -srcfolder "$APP" -ov -format UDZO "dist/Lithnode-mac-$ARCH.dmg"
  ls -la "dist/Lithnode-mac-$ARCH.dmg"
else
  # 3. what the Flatpak packs: the window, the engine in server/ beside it, and the desktop files
  STAGE=packaging/linux/stage
  rm -rf "$STAGE"; mkdir -p "$STAGE"
  cp -a "dist/Lithnode-linux-$ARCH" "$STAGE/app"
  test -x "$STAGE/app/Lithnode"   # what lithnode.sh starts
  find "$STAGE/app/locales" -name '*.pak' ! -name 'en-US.pak' -delete
  cp -a dist/Lithnode "$STAGE/app/server"
  cp packaging/linux/lithnode.sh packaging/linux/com.lithnode.Lithnode.desktop packaging/linux/com.lithnode.Lithnode.metainfo.xml "$STAGE/"
  cp installer/lithnode.png "$STAGE/lithnode.png"
  du -sh "$STAGE"
fi

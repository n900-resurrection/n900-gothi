#!/bin/bash
# gothi is pure Python: check that the sources compile, and fetch the graphics of the Flipper firmware (GPL-3.0) at a pinned commit.
#   make -C apps/n900-gothi build
# Output: /project/build/out/n900-gothi-$VERSION/{lib/gothi, share/flipper, share/doc}
set -euo pipefail
VERSION="${VERSION:-0.9.0}"
PROJ=/project
HERE="$PROJ/apps/n900-gothi"
OUT="$PROJ/build/out/n900-gothi-$VERSION"
FW_COMMIT="$(cut -d' ' -f1 "$HERE/tools/firmware-commit")"   # the pin: the firmware commit of the graphics (change it to take newer graphics)
FW="$PROJ/build/downloads/flipperzero-firmware"

# sources compile (Python 3.12 of the Workshop is enough for a syntax check)
python3 -I -m py_compile "$HERE"/gothi/*.py
find "$HERE" -name __pycache__ -prune -exec rm -rf {} +

# the firmware graphics at the pinned commit (a shallow, sparse checkout; kept in build/downloads)
if [ ! -d "$FW/.git" ]; then
    git clone -q --depth 1 --filter=blob:none --sparse https://github.com/flipperdevices/flipperzero-firmware.git "$FW"
fi
git -C "$FW" sparse-checkout set assets/dolphin assets/icons
if [ "$(git -C "$FW" rev-parse HEAD)" != "$FW_COMMIT" ]; then
    git -C "$FW" fetch -q --depth 1 origin "$FW_COMMIT"
    git -C "$FW" checkout -q "$FW_COMMIT"
fi
echo "firmware $(git -C "$FW" rev-parse --short HEAD)"

rm -rf "$OUT"; mkdir -p "$OUT/lib" "$OUT/share/flipper/icons" "$OUT/share/flipper/dolphin" "$OUT/share/doc"
cp -r "$HERE/gothi" "$OUT/lib/gothi"
cp -r "$HERE/modules" "$OUT/modules"            # the bundled modules (Settings: volume, brightness, Bluetooth, Wi-Fi)
find "$OUT/lib" -name __pycache__ -prune -exec rm -rf {} +
cp -r "$FW/assets/dolphin/external" "$OUT/share/flipper/dolphin/external"
for d in MainMenu Power StatusBar Common; do cp -r "$FW/assets/icons/$d" "$OUT/share/flipper/icons/$d"; done
"$HERE/tools/derive-icons.sh" "$FW/assets/icons" "$OUT/share/flipper/icons"
git -C "$FW" rev-parse HEAD > "$OUT/share/flipper/COMMIT"
# the licence of the graphics: GPL-3.0 text of the firmware repository
for f in LICENSE LICENSE.md COPYING; do
    [ -s "$FW/$f" ] && cp "$FW/$f" "$OUT/share/doc/COPYING-flipper-graphics" && break
done
[ -s "$OUT/share/doc/COPYING-flipper-graphics" ] || curl -fsSL https://raw.githubusercontent.com/flipperdevices/flipperzero-firmware/"$FW_COMMIT"/LICENSE -o "$OUT/share/doc/COPYING-flipper-graphics"
echo "gothi $VERSION: $(find "$OUT/lib" -name '*.py' | wc -l) modules, $(find "$OUT/share/flipper" -name '*.png' | wc -l) graphics files, $(du -sh "$OUT" | cut -f1)"

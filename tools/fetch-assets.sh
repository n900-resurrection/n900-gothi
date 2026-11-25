#!/bin/sh
# Download the graphics of the Flipper Zero firmware (GPL-3.0) into assets/flipper/ (not committed): the animations of the dolphin and the icons,
# in the folder layout of the firmware (frame_N.png, meta.txt, manifest.txt). Run again to get new ones. Needs git.
set -e
cd "$(dirname "$0")/.."
T=$(mktemp -d)
git clone -q --depth 1 --filter=blob:none --sparse https://github.com/flipperdevices/flipperzero-firmware.git "$T/fw"
git -C "$T/fw" sparse-checkout set assets/dolphin assets/icons
rm -rf assets/flipper
mkdir -p assets/flipper
cp -r "$T/fw/assets/dolphin" "$T/fw/assets/icons" assets/flipper/
git -C "$T/fw" log -1 --format='%H %cs' > assets/flipper/COMMIT
rm -rf "$T"
echo "assets/flipper: $(find assets/flipper -name '*.png' | wc -l) PNG files, firmware $(cut -c1-10 assets/flipper/COMMIT)"

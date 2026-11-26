#!/bin/sh
# Icons that the firmware has only in another size are derived from its graphics (they are not committed: the firmware graphics are GPL-3.0).
#   tools/derive-icons.sh <firmware icons folder (assets/icons)> <target icons folder>
# Gothi/Smile_14.png: the smiley of the firmware (BadUsb/Smile_18x18.png) scaled to the 14 px of the menu icons, for the menu Dolphin (the mood).
set -e
SRC="$1"; DST="$2"
mkdir -p "$DST/Gothi"
convert "$SRC/BadUsb/Smile_18x18.png" -background white -alpha remove -filter Box -resize 14x14 -threshold 50% -depth 1 -define png:color-type=0 "$DST/Gothi/Smile_14.png"

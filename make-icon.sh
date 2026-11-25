#!/bin/bash
# Draw the menu icon of gothi -> icon.png next to this script: an orange screen with a black G on the dark square (see scripts/icon-lib.sh).
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
. "$D/../../scripts/icon-lib.sh"
icon_base -fill '#ff6400' -draw 'roundrectangle 32,52 223,162 16,16' -font "$FONT" -pointsize 120 -fill black -annotate +86+142 'G' \
    -fill '#ff6400' -draw 'circle 76,205 76,217' -draw 'circle 128,205 128,217' -draw 'circle 180,205 180,217' "$D/icon.png"

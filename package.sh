#!/bin/bash
# Package gothi as a .deb for Maemo 5: make -C apps/n900-gothi deb
# Output: /project/build/deb/gothi_<VERSION>-<REV>_armel.deb
set -euo pipefail
PROJ=/project
. "$PROJ/scripts/debpack.sh"

PKG=gothi
VERSION="${VERSION:-0.12.0}"
OUT="$PROJ/build/out/n900-gothi-$VERSION"
HERE="$PROJ/apps/n900-gothi"
STAGE="$PROJ/build/deb/stage-$PKG"
[ -d "$OUT/lib/gothi" ] || { echo "Missing build output in $OUT, run build.sh first (make build)"; exit 1; }

rm -rf "$STAGE"
mkdir -p "$STAGE/opt/gothi/share/doc/$PKG" "$STAGE/opt/gothi/modules" "$STAGE/usr/bin"   # modules: the packages of the modules put their folders here
cp -a "$OUT/lib" "$STAGE/opt/gothi/lib"
cp -a "$OUT/modules/." "$STAGE/opt/gothi/modules/"
cp -a "$OUT/share/flipper" "$STAGE/opt/gothi/share/flipper"
install -m 644 "$HERE/README.md" "$HERE/LICENSE" "$STAGE/opt/gothi/share/doc/$PKG/"
install -m 644 "$OUT/share/doc/COPYING-flipper-graphics" "$HERE/assets/fonts/OFL.txt" "$STAGE/opt/gothi/share/doc/$PKG/"
cat > "$STAGE/usr/bin/gothi" <<'EOT'
#!/bin/sh
# gothi: a Flipper Zero style interface (see /opt/gothi/share/doc/gothi/README.md). Options: --mode auto|keyboard|touch, --windowed
export PYTHONPATH=/opt/gothi/lib${PYTHONPATH:+:$PYTHONPATH}
export GOTHI_ASSETS="${GOTHI_ASSETS:-/opt/gothi/share/flipper}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${XDG_CACHE_HOME:-$HOME/.cache}/gothi/pyc}"   # /opt is not writable for the user
exec python3 -W ignore -m gothi "$@"
EOT
chmod 755 "$STAGE/usr/bin/gothi"
for sz in 48 64; do
    mkdir -p "$STAGE/usr/share/icons/hicolor/${sz}x${sz}/apps"
    convert "$HERE/icon.png" -resize "${sz}x${sz}" "$STAGE/usr/share/icons/hicolor/${sz}x${sz}/apps/$PKG.png"
done
mkdir -p "$STAGE/usr/share/applications/hildon"
cat > "$STAGE/usr/share/applications/hildon/$PKG.desktop" <<'EOT'
[Desktop Entry]
Encoding=UTF-8
Version=1.0
Type=Application
Name=gothi
Icon=gothi
Exec=/usr/bin/gothi
X-Osso-Type=application/x-executable
EOT
DEBPACK_ICON="$HERE/icon.png"

# Wi-Fi scan (modules/wifi-scan): a normal user only reads the results of the last scan (often one network), a fresh scan needs root. One narrow sudo rule,
# the way Maemo packages do it (a file in /etc/sudoers.d, then update-sudoers); the rule is made on the phone, so it is not a conffile.
mkdir -p "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/postinst" <<'EOT'
#!/bin/sh
echo "user ALL = NOPASSWD: /sbin/iwlist wlan0 scan" > /etc/sudoers.d/gothi.sudoers
chmod 644 /etc/sudoers.d/gothi.sudoers
update-sudoers >/dev/null 2>&1 || true
exit 0
EOT
cat > "$STAGE/DEBIAN/postrm" <<'EOT'
#!/bin/sh
if [ "$1" = remove ] || [ "$1" = purge ]; then
    rm -f /etc/sudoers.d/gothi.sudoers
    update-sudoers >/dev/null 2>&1 || true
fi
exit 0
EOT
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

SECTION=user/utilities
DEPENDS="python3.11, python3-pysdl2 (>= 0.9.17), libsdl2 (>= 2.30)"
RECOMMENDS="wifi-switcher"      # the Wi-Fi switch of the Settings runs its script; without it that entry is simply not shown
DISPLAY_NAME="gothi"
SHORT_DESC="A Flipper Zero style interface: menu, clock, battery, animations (keyboard and touch)"
LONG_DESC="gothi shows the 128x64 one-bit screen of the Flipper Zero with its original graphics and six keys: with the keyboard slid out the screen fills the display and the arrows, Enter and Backspace control it, with the keyboard closed there is a cross and a Back button for the touch screen. Applications: clock, battery, key test, a player of the firmware animations. Colour and screen size are set in Settings.
Written in Python 3 (SDL 2 through PySDL2). The graphics of the Flipper Zero firmware (GPL-3.0, Flipper Devices Inc.) are included; this package is not affiliated with Flipper Devices.
Upstream: https://github.com/n900-resurrection/n900-gothi"
debpack_build

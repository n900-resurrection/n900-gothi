TEST_NAME=gothi
need_pkg gothi
ok launcher test -x /usr/bin/gothi
ok menu-entry test -f /usr/share/applications/hildon/gothi.desktop
ok graphics-present test -d /opt/gothi/share/flipper/dolphin/external
ok licences test -s /opt/gothi/share/doc/gothi/COPYING-flipper-graphics
contains usage "--mode" sh -c '/usr/bin/gothi --help 2>&1'
# without a display (the dummy video driver) and with a throw-away HOME: starts, draws, feeds keys, ends after 8 frames
tmpdir
export HOME=$TESTDIR
ok headless-run sh -c 'SDL_VIDEODRIVER=dummy /usr/bin/gothi --mode keyboard --frames 8 --keys down,down,ok,back --screenshot '$TESTDIR'/shot.bmp'
ok screenshot-written test -s "$TESTDIR/shot.bmp"
# the firmware animations load from the package
contains animation-loads "frames" sh -c 'PYTHONPATH=/opt/gothi/lib GOTHI_ASSETS=/opt/gothi/share/flipper python3 -W ignore -c "
from gothi import flipper
a = flipper.load_icon(\"dolphin/external/L1_Boxing_128x64\")
print(len(a.frames), \"frames\")"'
contains settings-saved "color" sh -c 'SDL_VIDEODRIVER=dummy /usr/bin/gothi --frames 20 --keys down,down,down,down,down,down,ok,down,right,back,back >/dev/null 2>&1; cat '$TESTDIR'/.config/gothi/settings.json'
contains dolphin-state-saved "\"tools\": 1" sh -c 'rm -f '$TESTDIR'/.config/gothi/dolphin-state.json; SDL_VIDEODRIVER=dummy /usr/bin/gothi --frames 6 --keys ok,back >/dev/null 2>&1; cat '$TESTDIR'/.config/gothi/dolphin-state.json'
contains rules-shipped "rules.json" sh -c '/usr/bin/gothi --rules'
summary

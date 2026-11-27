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
contains settings-saved "color" sh -c 'SDL_VIDEODRIVER=dummy /usr/bin/gothi --frames 20 --keys down,down,down,down,down,down,down,ok,down,right,back,back >/dev/null 2>&1; cat '$TESTDIR'/.config/gothi/settings.json'
contains dolphin-state-saved "\"tools\": 1" sh -c 'rm -f '$TESTDIR'/.config/gothi/dolphin-state.json; SDL_VIDEODRIVER=dummy /usr/bin/gothi --frames 6 --keys ok,back >/dev/null 2>&1; cat '$TESTDIR'/.config/gothi/dolphin-state.json'
contains rules-shipped "rules.json" sh -c '/usr/bin/gothi --rules'
contains modules-listing "search folders" sh -c '/usr/bin/gothi --modules'
# the bundled modules (Settings): the commands of the manifests, as the user. State is restored at the end of each test.
M() { PYTHONPATH=/opt/gothi/lib python3 -W ignore -c "import json, sys; print(json.load(open('/opt/gothi/modules/$1/module.json'))[sys.argv[1]])" "$2"; }
U() { su user -c "$(M "$1" "$2" | sed "s/{value}/$3/")"; }
contains bundled-modules "Wi-Fi (switch)" sh -c '/usr/bin/gothi --modules'
contains bundled-volume "Volume (level)" sh -c '/usr/bin/gothi --modules'
contains bundled-brightness "Brightness (level)" sh -c '/usr/bin/gothi --modules'
contains bundled-bluetooth "Bluetooth (switch)" sh -c '/usr/bin/gothi --modules'
volume_roundtrip() {
    orig=$(U volume get); U volume set 55; got=$(U volume get); U volume set "$orig"
    [ "$got" = 55 ] && echo "volume-roundtrip-ok"
}
contains volume-roundtrip "volume-roundtrip-ok" volume_roundtrip
brightness_read() { v=$(U brightness get); [ "$v" -ge 1 ] && [ "$v" -le 5 ] && echo "brightness-$v-ok"; U brightness set "$v"; }
contains brightness-read "ok" brightness_read
bluetooth_cycle() {
    if U bluetooth status; then was=1; else was=0; fi
    U bluetooth start; sleep 2; U bluetooth status && up=1 || up=0
    U bluetooth stop; sleep 2; U bluetooth status && down=0 || down=1
    [ "$was" = 1 ] && U bluetooth start
    [ "$up$down" = 11 ] && echo "bluetooth-cycle-ok"
}
contains bluetooth-cycle "bluetooth-cycle-ok" bluetooth_cycle
# Wi-Fi: only the state is read (switching it off would cut the connection that runs this test)
contains wifi-status "on" sh -c 'su user -c "$(PYTHONPATH=/opt/gothi/lib python3 -W ignore -c "import json; print(json.load(open(\"/opt/gothi/modules/wifi/module.json\"))[\"status\"])")" && echo on || echo off'
# Flashlight: the flash LED lights for a moment (a start, the state, a stop), and no holder process is left behind
contains bundled-flashlight "Flashlight (switch)" sh -c '/usr/bin/gothi --modules'
flashlight_cycle() {
    T="python3 /opt/gothi/modules/flashlight/torch.py"
    su user -c "$T stop"; su user -c "$T status" && return
    su user -c "$T start" || return; su user -c "$T status" || return
    sleep 1; su user -c "$T stop"; su user -c "$T status" && return
    echo "flashlight-cycle-ok"
}
contains flashlight-cycle "flashlight-cycle-ok" flashlight_cycle
# Bluetooth scan: the module is offered; the adapter state and the known devices are only read (an inquiry is not made by the test)
contains bundled-bluetooth-scan "Bluetooth scan (python)" sh -c '/usr/bin/gothi --modules'
contains bluetooth-known-read "known" sh -c 'su user -c "PYTHONPATH=/opt/gothi/lib python3 -W ignore -c \"from gothi import bluetooth as b; b.adapter_up(); print(len(b.read_known()) >= 0 and \\\"known\\\")\""'
# touching the screen itself: off by default (a tap does nothing), on with the setting (a tap on the first row opens the Clock, which earns a deed)
rm -f "$HOME/.config/gothi/dolphin-state.json"
SDL_VIDEODRIVER=dummy /usr/bin/gothi --mode keyboard --frames 8 --keys tap:40:14 >/dev/null 2>&1
no_state_without_setting() { [ ! -e "$HOME/.config/gothi/dolphin-state.json" ] && echo untouched; }
contains tap-ignored-when-off "untouched" no_state_without_setting
echo '{"touch_screen": true}' > "$HOME/.config/gothi/settings.json"
contains tap-opens-the-clock "\"tools\": 1" sh -c 'SDL_VIDEODRIVER=dummy /usr/bin/gothi --mode keyboard --frames 8 --keys tap:40:14 >/dev/null 2>&1; cat "$HOME/.config/gothi/dolphin-state.json"'
rm -f "$HOME/.config/gothi/settings.json" "$HOME/.config/gothi/dolphin-state.json"
summary

#!/bin/sh
# Copy gothi to the N900 over ssh and add a menu entry (MVP: no package yet).   tools/deploy-n900.sh [ssh-host, default n900]
# Needs on the phone: Python 3.11 (package python3.11) and libsdl2 (package libsdl2) of the n900-resurrection repository.
set -e
H="${1:-n900}"
cd "$(dirname "$0")/.."
[ -d assets/flipper ] || ./tools/fetch-assets.sh
W=$(mktemp -d)
python3 -m pip download -q --no-deps pysdl2 -d "$W"
tar czf "$W/gothi.tgz" gothi assets/flipper/dolphin/external assets/flipper/icons
scp -q "$W"/gothi.tgz "$W"/*.whl "$H":/home/user/
ssh "$H" 'set -e
mkdir -p /home/user/gothi /home/user/tmp
cd /home/user/gothi && rm -rf gothi assets && tar xzf ../gothi.tgz && cd ..
chown -R user /home/user/gothi /home/user/tmp
su user -c "cd /home/user && TMPDIR=/home/user/tmp python3 -m pip install --user --no-deps -q --force-reinstall PySDL2-*.whl"
cat > /usr/bin/gothi <<EOS
#!/bin/sh
cd /home/user/gothi && exec python3 -W ignore -m gothi "\$@"
EOS
chmod +x /usr/bin/gothi
cat > /usr/share/applications/hildon/gothi.desktop <<EOS
[Desktop Entry]
Name=gothi
Exec=/usr/bin/gothi
Icon=general_tools_unsorted
Type=Application
Categories=Utilities;
X-Osso-Type=application/x-executable
EOS
rm -f /home/user/gothi.tgz /home/user/PySDL2-*.whl'
rm -rf "$W"
echo "installed: menu entry gothi, or  ssh $H su user -c 'DISPLAY=:0 gothi'"

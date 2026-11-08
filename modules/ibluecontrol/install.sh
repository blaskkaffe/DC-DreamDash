# iBlueControlMod module - sourced by install.sh while this module is in the folder. Installs the Python package bleak (the Pi talks
# Bluetooth LE to the adapter through BlueZ) and adds the module's own service, dreampi-netswitch-iblue. The module itself is off until
# it is switched on in Settings > Modules. Nothing of DreamPi is touched.
if ! python3 -c "import bleak" >/dev/null 2>&1; then
    echo "Installing bleak (Bluetooth LE for the iBlueControlMod module)..."
    # bleak 0.21 and newer need Python 3.8; the old DreamPi image (Raspbian Buster) has 3.7, which takes bleak 0.20
    BLEAK="bleak"
    [ "$(python3 -c 'import sys; print(sys.version_info[1])' 2>/dev/null || echo 9)" -lt 8 ] && BLEAK="bleak<0.21"
    # the Debian / Raspberry Pi OS package first (newer systems), then pip (installed first when it is missing)
    { apt-get update -qq >/dev/null 2>&1; apt-get install -y python3-bleak >/dev/null 2>&1; } \
        || { python3 -m pip --version >/dev/null 2>&1 || apt-get install -y python3-pip >/dev/null 2>&1
             # Raspbian Buster can have a held python-pip-whl that blocks python3-pip: then pip's own installer (it goes to /usr/local)
             python3 -m pip --version >/dev/null 2>&1 || {
                 GP=https://bootstrap.pypa.io/get-pip.py; [ "$BLEAK" != "bleak" ] && GP=https://bootstrap.pypa.io/pip/3.7/get-pip.py
                 curl -fsSL "$GP" -o /tmp/get-pip.py >/dev/null 2>&1 && python3 /tmp/get-pip.py >/dev/null 2>&1; rm -f /tmp/get-pip.py; }
             python3 -m pip install --break-system-packages "$BLEAK" >/dev/null 2>&1 || python3 -m pip install "$BLEAK" >/dev/null 2>&1; }
    python3 -c "import bleak" >/dev/null 2>&1 \
        || echo "WARNING: could not install bleak for the iBlueControlMod module. Run: curl -fsSL https://bootstrap.pypa.io/pip/3.7/get-pip.py | sudo python3 && sudo python3 -m pip install 'bleak<0.21'"
fi
cat > /etc/systemd/system/dreampi-netswitch-iblue.service <<UNIT
[Unit]
Description=DreamPi Netswitch iBlueControlMod link
After=bluetooth.target network.target
StartLimitIntervalSec=0
ConditionPathExists=$DEST/modules/ibluecontrol/netswitch_iblue_service.py

[Service]
ExecStart=$(command -v python3) $DEST/modules/ibluecontrol/netswitch_iblue_service.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
NS_SERVICES="$NS_SERVICES dreampi-netswitch-iblue.service"

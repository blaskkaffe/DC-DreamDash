# iBlueControlMod module - sourced by install.sh while this module is in the folder. Installs the Python package bleak (the Pi talks
# Bluetooth LE to the adapter through BlueZ) and adds the module's own service, dreampi-netswitch-iblue. The module itself is off until
# it is switched on in Settings > Modules. Nothing of DreamPi is touched.
if ! python3 -c "import bleak" >/dev/null 2>&1; then
    echo "Installing bleak (Bluetooth LE for the iBlueControlMod module)..."
    # the Debian / Raspberry Pi OS package first (no pip needed, works with the system Python), pip as the fallback
    { apt-get update -qq >/dev/null 2>&1; apt-get install -y python3-bleak >/dev/null 2>&1; } \
        || python3 -m pip install --break-system-packages bleak >/dev/null 2>&1 \
        || python3 -m pip install bleak >/dev/null 2>&1
    python3 -c "import bleak" >/dev/null 2>&1 \
        || echo "WARNING: could not install bleak for the iBlueControlMod module. Run: sudo apt install python3-bleak"
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

# iBlueControlMod module - sourced when the module is gone from the folder, and by uninstall.sh: removes its service and files.
systemctl disable --now dreampi-netswitch-iblue.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/dreampi-netswitch-iblue.service
rm -f "$DEST/iblue_device" "$DEST/iblue_demo"

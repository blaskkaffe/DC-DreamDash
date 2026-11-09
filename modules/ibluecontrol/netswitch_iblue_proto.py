# DreamPi Netswitch add-on - iBlueControlMod module: the Bluetooth protocol of the adapter, pure functions (no Bluetooth, no files).
# The adapter is a BlueRetro (fork) with a GATT config service; commands go to the command characteristic and the answer is read back
# from it (the firmware's main/bluetooth/att_cfg.c, the web config's web/utils/iblueCmd.js). Works on Python 3 and 2.7.
import struct

SERVICE = "56830f56-5180-fab0-314b-2fa176799a00"


def uuid(n):
    return "56830f56-5180-fab0-314b-2fa176799a%02x" % n


CHRC_GLOBAL, CHRC_OUT_CTRL, CHRC_OUT_DATA, CHRC_IN_CTRL, CHRC_IN_DATA, CHRC_CMD = [uuid(n) for n in (1, 2, 3, 4, 5, 7)]

CMD_GET_IBLUE_INFO = 0x40
CMD_GET_PORT_STATUS = 0x50      # the iBlueControlMod firmware (`unified`, docs/ble-commands.md there): read only; was 0x4B in a first draft,
                                # but 0x4B-0x4F are the firmware's Joy-Con motion commands
# Info feature bits (byte 5 of the 0x40 answer, the firmware's one table in docs/ble-commands.md); a client ignores bits it does not know
FEAT_GESTURES, FEAT_GAMEID, FEAT_MOTION, FEAT_PORT_STATUS, FEAT_DCAPI = 0x01, 0x04, 0x10, 0x20, 0x40

PORTS = 4
PORT_NAMES = ("A", "B", "C", "D")
STATE_EMPTY, STATE_BT, STATE_WIRED = 0, 1, 2
STATUS_TEXT = {STATE_EMPTY: "Empty", STATE_BT: "BT-connected", STATE_WIRED: "Wired-connected"}
STATUS_KIND = {STATE_EMPTY: "empty", STATE_BT: "bt", STATE_WIRED: "wired"}

# the Dreamcast output modes (BlueRetro: GamePad, GamePadAlt, Keyboard, Mouse; the iBlueControlMod firmware adds Racing and Maracas, the
# Racing Controller and Samba de Amigo's maracas) and accessories, as the web config numbers them
TYPES = [(0, "Normal"), (1, "Dual stick"), (2, "Keyboard"), (3, "Mouse"), (4, "Racing"), (5, "Maracas")]
# what the adapter tells the Dreamcast in its Maple device info (main/wired/maple.c: "Dreamcast Controller", "Dreamcast Mouse", "Keyboard"),
# without "Dreamcast " so that the longest, "Controller", fits a small tile. Normal and Dual stick both say "Controller".
CONSOLE_NAMES = {0: "Controller", 1: "Controller", 2: "Keyboard", 3: "Mouse", 4: "Racing", 5: "Maracas"}     # "Racing Controller", "Maracas Controller"
SHORT_STATUS = {STATE_EMPTY: "Empty", STATE_BT: "BT", STATE_WIRED: "Wired"}
ACCS = [(0, "None"), (1, "VMU"), (2, "Rumble"), (3, "Both")]


def label(table, value):
    for v, name in table:
        if v == value:
            return name
    return "Unknown (%s)" % value


def parse_info(raw):
    """The answer to 0x40: None when it is not an iBlueControlMod build."""
    raw = bytearray(raw)
    if len(raw) < 9 or bytes(raw[0:4]) != b"iBLU":
        return None
    f = raw[5]
    return {"version": raw[4], "gestures": bool(f & FEAT_GESTURES), "gameid": bool(f & FEAT_GAMEID), "motion": bool(f & FEAT_MOTION),
            "port_status": bool(f & FEAT_PORT_STATUS), "dcapi": bool(f & FEAT_DCAPI), "gesture_count": raw[6], "action_count": raw[8]}


def parse_ports(raw):
    """The answer to 0x50: [count, then per port: state, dev_mode, acc_mode, bt type, bt subtype]."""
    raw = bytearray(raw)
    if not raw:
        return []
    out = []
    for i in range(min(raw[0], PORTS)):
        o = 1 + i * 5
        if o + 5 > len(raw):
            break
        out.append({"port": i, "state": raw[o], "dev_mode": raw[o + 1], "acc_mode": raw[o + 2], "bt_type": raw[o + 3], "bt_subtype": raw[o + 4]})
    return out


def out_ctrl(port):
    return struct.pack("<H", port)


def out_data(dev_mode, acc_mode):
    return bytearray([dev_mode, acc_mode])


def valid_choice(table, value):
    return any(v == value for v, _ in table)


def port_view(p):
    """One port as the page shows it."""
    return {"name": PORT_NAMES[p["port"]] if p["port"] < len(PORT_NAMES) else str(p["port"] + 1),
            "port": p["port"], "kind": STATUS_KIND.get(p["state"], "empty"), "status": STATUS_TEXT.get(p["state"], "Empty"),
            "short": SHORT_STATUS.get(p["state"], "Empty"),
            "console_name": CONSOLE_NAMES.get(p["dev_mode"], "") if p["state"] == STATE_BT else "",      # a wired controller's type is not known to the adapter
            "type": p["dev_mode"], "type_text": label(TYPES, p["dev_mode"]), "acc": p["acc_mode"], "acc_text": label(ACCS, p["acc_mode"])}

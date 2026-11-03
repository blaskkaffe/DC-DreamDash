# DreamPi Netswitch add-on - iBlueControlMod module: the Bluetooth protocol of the adapter, pure functions (no Bluetooth, no files).
# The adapter is a BlueRetro (fork) with a GATT config service; commands go to the command characteristic and the answer is read back
# from it (the firmware's main/bluetooth/att_cfg.c, the web config's web/utils/iblueCmd.js). Works on Python 3 and 2.7.
import struct

SERVICE = "56830f56-5180-fab0-314b-2fa176799a00"


def uuid(n):
    return "56830f56-5180-fab0-314b-2fa176799a%02x" % n


CHRC_GLOBAL, CHRC_OUT_CTRL, CHRC_OUT_DATA, CHRC_IN_CTRL, CHRC_IN_DATA, CHRC_CMD = [uuid(n) for n in (1, 2, 3, 4, 5, 7)]

CMD_GET_IBLUE_INFO = 0x40
CMD_GET_PROFILE = 0x43
CMD_PROFILE_LOAD = 0x45
CMD_GET_PORT_STATUS = 0x4B      # added by the iBlueControlMod firmware branch claude/port-status

PORTS = 4
PORT_NAMES = ("A", "B", "C", "D")
STATE_EMPTY, STATE_BT, STATE_WIRED = 0, 1, 2
STATUS_TEXT = {STATE_EMPTY: "Empty", STATE_BT: "BT-connected", STATE_WIRED: "Wired-connected"}
STATUS_KIND = {STATE_EMPTY: "empty", STATE_BT: "bt", STATE_WIRED: "wired"}

# the Dreamcast output modes (BlueRetro: GamePad, GamePadAlt, Keyboard, Mouse) and accessories, as the web config numbers them
TYPES = [(0, "Normal"), (1, "Dual stick"), (2, "Keyboard"), (3, "Mouse")]
ACCS = [(0, "None"), (1, "Memory"), (2, "Rumble"), (3, "Both")]
PROFILE_RESULT = {0: "OK", 1: "That profile slot is empty", 2: "Bad request", 3: "Could not write it in the adapter"}


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
    return {"version": raw[4], "gestures": bool(f & 1), "profiles": bool(f & 2), "gameid": bool(f & 4), "port_status": bool(f & 8),
            "gesture_count": raw[6], "profile_count": raw[7], "action_count": raw[8]}


def parse_ports(raw):
    """The answer to 0x4B: [count, then per port: state, dev_mode, acc_mode, bt type, bt subtype]."""
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


def parse_profile(raw):
    """The answer to 0x43: [used, slot, name...]."""
    raw = bytearray(raw)
    if len(raw) < 2:
        return {"used": False, "slot": 0, "name": ""}
    name = bytes(raw[2:]).split(b"\0", 1)[0].decode("ascii", "replace")
    return {"used": raw[0] == 1, "slot": raw[1], "name": name}


def cmd_get_profile(slot):
    return bytearray([CMD_GET_PROFILE, slot])


def cmd_profile_load(slot):
    return bytearray([CMD_PROFILE_LOAD, slot])


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
            "type": p["dev_mode"], "type_text": label(TYPES, p["dev_mode"]), "acc": p["acc_mode"], "acc_text": label(ACCS, p["acc_mode"])}

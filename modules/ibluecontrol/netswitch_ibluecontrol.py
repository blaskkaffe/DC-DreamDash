# DreamPi Netswitch add-on - iBlueControlMod module, web side. The page's box (four port buttons, a pop-up per port) reads GET /iblue/view; its
# actions are POSTs that are written as a request file for the module's own service (netswitch_iblue_service.py, the only code that talks
# Bluetooth), which does them and writes the result in the state file. No sockets between the two (docs/ibluecontrol.md). Python 3.
import json
import os
import time

import base_core as core
import netswitch_iblue_proto as proto

STATE = core.TMP_PREFIX + ".iblue"             # the service -> web: {"time", "found", "info", "ports", "result", "error"}
REQUEST = core.TMP_PREFIX + ".iblue_request"   # web -> the service: {"id", "action", ...}
SEEN = core.TMP_PREFIX + ".iblue_seen"         # touched by every GET /iblue/view: the service only polls while a page is looking
DEVICE = os.path.join(core.BASE_DIR, "iblue_device")   # the Bluetooth address of the adapter once found ("rescan" removes it)
STALE = 60                                     # seconds after which the service's last answer is too old to show
MAX_BODY = 1000


def _read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (IOError, OSError, ValueError):
        return {}


def device_text():
    try:
        with open(DEVICE) as f:
            return "Paired with the adapter at %s" % f.read().strip()
    except (IOError, OSError):
        return "No adapter chosen yet: it is searched for when the box is on the page"


def view():
    """What the page's box shows, ready to display."""
    try:
        open(SEEN, "w").close()
    except (IOError, OSError):
        pass
    st = _read(STATE)
    fresh = st.get("time") and time.time() - st["time"] < STALE
    ports = []
    if fresh and st.get("ports"):
        ports = [proto.port_view(p) for p in st["ports"]]
    else:
        ports = [{"name": n, "port": i, "kind": "none", "status": "No adapter", "short": "No adapter", "console_name": "", "type": 0, "type_text": "", "acc": 0, "acc_text": ""}
                 for i, n in enumerate(proto.PORT_NAMES)]
    pending = os.path.exists(REQUEST)
    if not fresh:
        note = st.get("error") or "Looking for the adapter (tap its button to open pairing if it is not found)"
    else:
        note = st.get("error") or ""
    res = st.get("result") or {}
    return {"title": "iBluecontrolmod/blueretro", "note": note, "online": bool(fresh and st.get("found")), "busy": pending,
            "ports": ports, "types": [{"value": v, "label": n} for v, n in proto.TYPES], "accs": [{"value": v, "label": n} for v, n in proto.ACCS],
            "message": res.get("message", "") if not pending else "Working..."}


def _queue(req):
    if os.path.exists(REQUEST):
        return {"ok": False, "message": "The adapter is busy, try again in a moment"}
    req["id"] = int(time.time() * 1000)
    tmp = REQUEST + ".tmp"
    with open(tmp, "w") as f:
        json.dump(req, f)
    os.rename(tmp, REQUEST)
    core.poke("iblue")
    return {"ok": True, "message": "Working..."}


def _body(h):
    try:
        d = json.loads(h._body(MAX_BODY).decode("utf-8", "replace"))
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def _int(d, key, lo, hi):
    try:
        v = int(d.get(key))
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def _answer(h, r):
    h.send(json.dumps(r), "application/json", status=200 if r["ok"] else 409)
    return True


def _post_port(h):
    d = _body(h)
    port, typ, acc = _int(d, "port", 0, proto.PORTS - 1), _int(d, "type", 0, 255), _int(d, "acc", 0, 255)
    if port is None or typ is None or acc is None or not proto.valid_choice(proto.TYPES, typ) or not proto.valid_choice(proto.ACCS, acc):
        return _answer(h, {"ok": False, "message": "Bad request"})
    return _answer(h, _queue({"action": "port", "port": port, "type": typ, "acc": acc}))


def _post_rescan(h):
    try:
        os.remove(DEVICE)
    except OSError:
        pass
    return _answer(h, {"ok": True, "message": "Searching again"})


def _get_view(h):
    h.send(json.dumps(view()), "application/json")


def api(d, warnings):
    d["iblue_device"] = device_text()      # not "iblue": that name is the data source of the box (S.iblue)


GET = {"/iblue/view": _get_view}
POST = {"/iblue/port": _post_port, "/iblue/rescan": _post_rescan}
OPEN = ("/iblue/port",)      # dashboard buttons, like the network buttons; "rescan" is a setting (PIN)

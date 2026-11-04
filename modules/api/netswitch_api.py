# DreamPi Netswitch add-on - DC API module, web side: the Pi's end of the Dreamcast ecosystem's control language "dc1"
# (the shared design is docs/unified/04-control-channel.md in the Project; docs/dcapi.md here). Plain text over HTTP:
#   POST /dcapi    the request in the body, the answer in the body (text/plain). GET /dcapi answers "get hello" for a quick look.
#
#   dc1                        first line: the language level
#   id 17                      optional: echoed in the answer
#   to dreampi                 optional: who the request is for. Only this Pi answers for now (no relay to other devices yet)
#   get hello                  one operation per line: get <key> | get <prefix>* | set <key> <value> | call <action> [arguments]
#   get net.selected
#   call net.select dcnet
#
# The answer is "dc1", the echoed "id", then one line per answered key: "ok <key> <value>" or "err <key> <code> [why]". Codes: unknown,
# readonly, range, locked, busy, unavailable, denied, bad. Unknown keys never fail the rest of the message. This first slice offers the
# capabilities `api` and `net` (hello.*, net.*, events); link.*, online.* and the relay to adapters come later.
# The values come from the network switcher through its services ("net:state", "net:select"): this module imports no other module.
# `events` are polled: `get events since=N` answers "ok events.next M" and "ev <n> <key> <value>" for every change since N (the last 32 kept).
# Works on Python 3 and 2.7.
import os
import threading
import time

import base_core as core

LEVEL = "dc1"
CAPS = "api,net"                 # section 5 of the design: the capabilities this module keeps its promise for
RING = 32                        # changes kept for `get events`
MAX_BODY = 4000
OBSERVE_EVERY = 2                # seconds: how often the background thread looks for changes
VERSION_FILE = os.path.join(core.BASE_DIR, "version")

_lock = threading.Lock()
_ring = []                       # [(n, key, value)], oldest first
_next = [1]                      # the number the next change gets
_dropped = [0]                   # the highest change number that fell out of the ring
_last = [None]                   # the values at the last look; None = not looked yet (the first look starts the baseline, it is no change)


# ------------------------------------------------------------------ the values
def _clean(text):
    return " ".join(str(text).split())


def hello():
    """[(key, value)]: who this is and what it can do."""
    return [("hello.kind", "gateway"), ("hello.name", "DC-DreamDash"),
            ("hello.version", _clean(core.read_file(VERSION_FILE) or "unknown")),
            ("hello.api", "1"), ("hello.caps", CAPS)]


def values():
    """{key: value} of everything this Pi can read (keys it has no value for are left out)."""
    d = {}
    net = core.service("net:state")
    if isinstance(net, dict):
        d["net.selected"] = net.get("selected", "dcnow")
        if net.get("call"):
            d["net.call"] = net["call"]
        code = net.get("dcnet") or "inactive"
        d["net.dcnet"] = "ok" if code == "ok" else "off:" + code
    return d


def observe():
    """Look for changes since the last look and keep them for `get events`."""
    now = values()
    with _lock:
        if _last[0] is None and not now:
            return now                  # the network switcher is not there yet: no baseline, or its first values would look like changes
        if _last[0] is not None:
            for key in sorted(set(now) | set(_last[0])):
                if now.get(key) != _last[0].get(key):
                    _ring.append((_next[0], key, now.get(key, "none")))
                    _next[0] += 1
            while len(_ring) > RING:
                _dropped[0] = _ring.pop(0)[0]
        _last[0] = now
    return now


def start():
    """Called once by the web service: keep looking for changes, so `get events` also knows what happened between two requests."""
    def loop():
        while True:
            try:
                observe()
            except Exception:
                pass
            time.sleep(OBSERVE_EVERY)
    t = threading.Thread(target=loop)
    t.daemon = True
    t.start()


# ------------------------------------------------------------------ the language
def parse(text):
    """(request id or None, `to` or None, [(verb, key, rest)]) of a request; ValueError says what is wrong with it."""
    lines = [l.strip() for l in text.replace("\r", "").split("\n")]
    lines = [l for l in lines if l]
    if not lines or lines[0] != LEVEL:
        raise ValueError("first line must be " + LEVEL)
    rid, to, ops = None, None, []
    for line in lines[1:]:
        word, _, rest = line.partition(" ")
        rest = rest.strip()
        if word == "id":
            rid = rest.split(" ")[0][:10]
        elif word == "to":
            to = rest
        elif word in ("get", "set", "call"):
            key, _, arg = rest.partition(" ")
            ops.append((word, key, arg.strip()))
        else:
            ops.append((word, rest, ""))          # unknown verb: answered with err ... unknown
    return rid, to, ops


def _events(arg):
    """The answer lines of `get events since=N`."""
    since = 0
    for part in arg.replace("since=", "since ").split():
        if part.isdigit():
            since = int(part)
    observe()
    with _lock:
        out = []
        if since < _dropped[0]:
            out.append("ok events.lost 1")
        out.append("ok events.next %d" % _next[0])
        out += ["ev %d %s %s" % (n, k, v) for (n, k, v) in _ring if n > since]
    return out


def _get(key, arg):
    if key == "hello":
        return ["ok %s %s" % kv for kv in hello()]
    if key == "events":
        return _events(arg)
    known = values()
    known.update(dict(hello()))
    if key.endswith("*"):
        prefix = key[:-1]
        rows = ["ok %s %s" % (k, known[k]) for k in sorted(known) if k.startswith(prefix)]
        return rows or ["err %s unknown" % key]
    if key in known:
        return ["ok %s %s" % (key, known[key])]
    if key in ("net.call",):
        return ["err net.call unavailable no call"]
    return ["err %s unknown" % key]


def _set(key):
    known = dict(hello())
    known.update(values())
    if key in known or key.startswith("hello.") or key in ("net.call",):
        return ["err %s readonly" % key]
    return ["err %s unknown" % key]


def _call(action, arg):
    if action == "net.select":
        net = arg.split(" ")[0].lower()
        answer = core.service("net:select", net, "DC API")
        if answer == "ok":
            observe()
            return ["ok net.select " + net]
        if answer == "bad":
            return ["err net.select range dcnow or dcnet"]
        return ["err net.select unavailable"]
    return ["err %s unknown" % action]


def handle(text):
    """The answer (text) to a request (text)."""
    try:
        rid, to, ops = parse(text)
    except ValueError as e:
        return "%s\nerr request bad %s\n" % (LEVEL, e)
    out = [LEVEL] + (["id " + rid] if rid else [])
    if to and to.lower() not in ("dreampi", "gateway", "dc-dreamdash"):
        out.append("err to unavailable no relay to other devices yet")
        return "\n".join(out) + "\n"
    observe()
    for verb, key, arg in ops:
        if verb == "get":
            out += _get(key, arg)
        elif verb == "set":
            out += _set(key)
        elif verb == "call":
            out += _call(key, arg)
        else:
            out.append("err %s unknown" % (verb,))
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ HTTP
def _post(h):
    body = h._body(MAX_BODY).decode("utf-8", "replace")
    h.send(handle(body), "text/plain; charset=utf-8")
    return True


def _get_hello(h):
    h.send(handle(LEVEL + "\nget hello\nget net.*\n"), "text/plain; charset=utf-8")


GET = {"/dcapi": _get_hello}
OPEN = ("/dcapi",)             # the Dreamcast asks, also while Settings is locked with the PIN (the PIN is for the web page only)
POST = {"/dcapi": _post}

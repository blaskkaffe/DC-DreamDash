# -*- coding: utf-8 -*-
"""
DreamPi Netswitch add-on - the network switcher module's integration with DreamPi (routing hook).

Loaded automatically by Python (through a .pth file written by modules/switcher/install.sh) but does nothing unless
the running program imports DreamPi's netlink.py from /home/pi/dreampi.
It then wraps Netlink.check_number() with one rule:

  A call DreamPi would send to its normal PPP goes to DCNET when DCNET is selected (and enabled in netlink_config.ini).
  Netlink/XBAND codes, DreamPi's own *69/*70 prefixes and idle results are untouched.

The network is never chosen by the number that was dialed: it is selected over the data channel (the page's buttons, the
GPIO buttons, openMenu's POST /dcnow and /dcnet). The selection is the file dcnet_mode (DCNow! is selected again after
every reboot).
It also reports DreamPi's state (starting / ready / in a call) to
/tmp/dreampi-netswitch.state for the web page. Modules (modules/ in
the add-on folder) hook in here through the "hook" file in their module.json: "debuglog" provides the code
that, while the file debug_dtmf exists, logs every modem event while DreamPi
listens for the call to /tmp/dreampi-netswitch-dtmf.log (modules/debuglog/netswitch_hookdebug.py;
without the module nothing is logged).
No DreamPi file is modified. Written for both Python 2.7 and 3.
"""
import json
import logging
import os
import re
import sys
import time

BASE_DIR = "/opt/dreampi-netswitch"
FLAG = os.path.join(BASE_DIR, "dcnet_mode")
STATUS = "/tmp/dreampi-netswitch.active"
STATE = "/tmp/dreampi-netswitch.state"
DEBUG_DTMF = os.path.join(BASE_DIR, "debug_dtmf")  # exists = log modem events (see modules/debuglog)
MODULES_DIR = os.path.join(BASE_DIR, "modules")
MODULES_STATE = os.path.join(BASE_DIR, "modules.json")   # {"debuglog": true, ...} from the Modules menu
MODEM = "/tmp/dreampi-netswitch.modem"
MODEM_PORT = "/tmp/dreampi-netswitch.port"   # the serial device DreamPi opened, e.g. /dev/ttyUSB0
NETLINK_DIR = "/home/pi/dreampi"

# __builtin__ first: on Python 2 the "future" package can provide a fake
# "builtins" module, and patching that would do nothing.
try:
    import __builtin__ as _builtins  # Python 2
except ImportError:
    import builtins as _builtins  # Python 3

_original_import = _builtins.__import__
_done = [False]


def _log(obj, text):
    try:
        obj.logger.info("netswitch: " + text)
    except Exception:
        pass


def _write_file(path, text):
    """Replace a small state file in one step (write a temporary file, rename it over): the web page and the LED
    service read these files many times a second and must never see one half-written or empty."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write(text)
        os.rename(tmp, path)
    except Exception:
        pass


def _write_status(text):
    _write_file(STATUS, text + "\n")


def _write_state(state):
    """DreamPi's current state for the web page: starting, ready,
    call <network> or unknown, with a unix timestamp."""
    _write_file(STATE, "%s %d\n" % (state, int(time.time())))


def _module_active(name):
    """The module is installed (its folder with a module.json) and not switched off in the Modules menu.
    A module without an entry in modules.json counts as on (debuglog is on by default)."""
    if not os.path.exists(os.path.join(MODULES_DIR, name, "module.json")):
        return False
    try:
        with open(MODULES_STATE) as f:
            return json.load(f).get(name) is not False
    except Exception:
        return True


_parts = {}


def _module_part(name):
    """The module's "hook" file (module.json "hook": the file name without .py) once it has been imported, else None (module absent,
    off or without one). It runs inside DreamPi, so it is Python 2.7 and 3 compatible like this file."""
    if not _module_active(name):
        return None
    if name not in _parts:
        folder = os.path.join(MODULES_DIR, name)
        part = False
        try:
            with open(os.path.join(folder, "module.json")) as f:
                wanted = json.load(f).get("hook")
            if wanted:
                sys.path.insert(0, folder)
                try:
                    part = __import__(str(wanted))
                finally:
                    try:
                        sys.path.remove(folder)
                    except ValueError:
                        pass
        except Exception:
            part = False
        _parts[name] = part
    return _parts[name] or None


def _debug_part():
    """The debug log module's hook file (netswitch_hookdebug), or None."""
    return _module_part("debuglog")


def _dtmf_log(text):
    """Add a line to the debug log. The debug log module does the writing (and only while recording is on),
    so without the module nothing is logged."""
    if not os.path.exists(DEBUG_DTMF):
        return
    part = _debug_part()
    if part is not None:
        part.log(text)


def _watch_serial(modem):
    """Log what the modem reports while DreamPi listens for digits (debug log module)."""
    part = _debug_part()
    if part is not None:
        part.watch(modem)


def _patch(module):
    cls = getattr(module, "Netlink", None)
    original = getattr(cls, "check_number", None) if cls is not None else None
    if original is None:
        _write_status("error: Netlink.check_number not found, add-on inactive")
        return
    if getattr(original, "_netswitch", False):
        return

    def check_number(self, raw_string):
        result = original(self, raw_string)

        try:
            if isinstance(result, dict) and result.get("client") == "PPP" and os.path.exists(FLAG):
                if getattr(self, "dcnet", False):
                    self.mode = "dcnet"
                    self.dial_string = raw_string
                    _log(self, "routing %s to DCNET" % raw_string)
                    result = {"client": "dcnet", "dial_string": raw_string}
                else:
                    _log(self, "DCNET selected but not enabled in netlink_config.ini, using DCNow!")
            # Netlink, XBAND, *69 and idle results pass through unchanged
            client = result.get("client") if isinstance(result, dict) else None
            if client and client != "idle":
                _write_state("call " + {"PPP": "dcnow", "dcnet": "dcnet"}.get(client, client))
        except Exception:
            pass
        return result

    check_number._netswitch = True
    cls.check_number = check_number
    _write_status("active pid=%d" % os.getpid())
    _write_state("starting")
    _patch_ready_signals(cls)
    _install_modem_status()


# DreamPi's own log messages -> modem status shown on the web page.
# The first pattern that matches wins; "%s" is filled from the match and
# "{speed}" with the last carrier speed seen.
_MODEM_EVENTS = [
    (r"^Detecting connection and modem", "Looking for the modem", None),
    (r"^Unable to find a modem device", "No modem found, retrying", None),
    (r"^Unable to detect an internet connection", "Waiting for internet", None),
    (r"^Opening serial interface to (\S+)", "Opening modem on %s", "port"),
    (r"^<LISTENING>", "Dial tone on, waiting for a call", "clear"),
    (r"^(?:Response: )?CONNECT (\d+)", "Carrier up at %s bps", "speed"),
    (r"^DCNet Call answered", "Online via DCNET{speed}", None),
    (r"Call answered", "Answered, starting PPP{speed}", None),
    (r"^Connected$", "Online via DCNow!{speed}", None),
    (r"^Couldn't answer call", "Could not answer the call", "clear"),
    (r"^Detected modem hang up", "Call ended", "clear"),
    (r"^Connection terminated", "Call ended", "clear"),
    (r"^Xband disconnected|^Listener stopped", "Call ended", "clear"),
]
_speed = [""]


POKE_INTERNET = "/tmp/dreampi-netswitch.poke.internet"     # core.poke("internet"): the checker (netswitch_switcher_probes.py) measures the internet again now
_poked = [0.0]


def _poke_internet():
    """DreamPi has just said it sees no internet: ask the web service to look now instead of at its next check (at most every 5 s)."""
    if time.time() - _poked[0] >= 5:
        _poked[0] = time.time()
        _write_file(POKE_INTERNET, "%f\n" % time.time())


def _write_modem(text):
    _write_file(MODEM, "%d %s\n" % (int(time.time()), text))


def _write_port(port):
    _write_file(MODEM_PORT, port + "\n")


class _ModemStatusHandler(logging.Handler):
    """Turns DreamPi's own log lines into a short modem status."""
    def emit(self, record):
        try:
            msg = record.getMessage().strip()
            if msg and not msg.startswith("Rule "):
                _dtmf_log("dreampi: " + msg)
            if msg.startswith("Unable to detect an internet connection"):
                _poke_internet()
            for pattern, text, action in _MODEM_EVENTS:
                m = re.search(pattern, msg)
                if m:
                    if action == "speed":
                        _speed[0] = m.group(1)
                    elif action == "clear":
                        _speed[0] = ""
                    elif action == "port":
                        _write_port(m.group(1))
                    text = text % m.groups() if m.groups() else text
                    _write_modem(text.replace("{speed}", " at %s bps" % _speed[0] if _speed[0] else ""))
                    return
        except Exception:
            pass


def _install_modem_status():
    try:
        logger = logging.getLogger("dreampi")
        if not any(isinstance(h, _ModemStatusHandler) for h in logger.handlers):
            handler = _ModemStatusHandler()
            handler.setLevel(logging.INFO)
            logger.addHandler(handler)
        _write_modem("DreamPi starting")
    except Exception:
        pass


def _wrap_ready(cls, name):
    """Mark DreamPi ready when cls.name has run (the dial tone starting is
    exactly when DreamPi logs <LISTENING>)."""
    original = getattr(cls, name, None)
    if original is None or getattr(original, "_netswitch", False):
        return False

    def wrapper(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        _write_state("ready")
        # A new serial object is opened after every call, so watch it again
        _watch_serial(getattr(self, "modem", self))
        return value

    wrapper._netswitch = True
    setattr(cls, name, wrapper)
    return True


def _patch_ready_signals(netlink_cls):
    # dreampi.py runs as the __main__ module and defines Modem there. It
    # imports netlink inside process(), so Modem already exists at this point.
    try:
        main = sys.modules.get("__main__")
        modem = getattr(main, "Modem", None)
        if modem is None or not _wrap_ready(modem, "start_dial_tone"):
            _write_state("unknown")
        elif "--disable-dial-tone" in sys.argv:
            # DreamPi never calls start_dial_tone() then (its own rule: dial_tone_enabled = "--disable-dial-tone" not in sys.argv), so
            # "ready" would never come, at the start or after a call: it listens as soon as the modem is opened again
            _wrap_ready(modem, "connect")
        # The USB serial path goes back to idle without a dial tone
        _wrap_ready(netlink_cls, "reset_serial")
    except Exception:
        pass


def _import_hook(name, *args, **kwargs):
    module = _original_import(name, *args, **kwargs)
    if not _done[0] and name == "netlink":
        try:
            mod = sys.modules.get("netlink")
            path = os.path.realpath(getattr(mod, "__file__", "") or "")
            if mod is not None and path.startswith(os.path.realpath(NETLINK_DIR)):
                _done[0] = True
                _patch(mod)
                _builtins.__import__ = _original_import
        except Exception as e:
            _write_status("error: %s" % e)
    return module


def _is_dreampi_process():
    # sys.argv does not exist yet when Python 2 processes .pth files, so the
    # command line is read from /proc instead. If that fails, hook anyway:
    # the hook only reacts to netlink.py from /home/pi/dreampi.
    try:
        with open("/proc/self/cmdline", "rb") as f:
            return b"dreampi" in f.read()
    except Exception:
        return True


try:
    if _is_dreampi_process():
        _builtins.__import__ = _import_hook
except Exception:
    pass

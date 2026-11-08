#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# DreamPi Netswitch add-on - the iBlueControlMod module's own service (dreampi-netswitch-iblue). The only code that talks Bluetooth.
#
# Runs as root. While the module is on and a page is looking (GET /iblue/view touches the "seen" file) it connects to the adapter every
# POLL seconds, reads the ports and the profile names, and disconnects again, so the adapter's Bluetooth slot is held for a moment only.
# A request from the page (netswitch_ibluecontrol.REQUEST) is done at once in its own connection. Needs the Python package bleak.
# With the file iblue_demo in the add-on's folder it talks to a simulated adapter instead (for the demo server and tests).
import asyncio
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))     # the base folder, for base_core
import base_core as core  # noqa: E402
import netswitch_ibluecontrol as web  # noqa: E402
import netswitch_iblue_proto as proto  # noqa: E402

POLL = 15           # seconds between status reads while a page is looking
LOOK = 40           # a page counts as looking this long after its last /iblue/view
SCAN = 10           # seconds of scanning
DEMO = os.path.join(core.BASE_DIR, "iblue_demo")


def write_state(st):
    st["time"] = time.time()
    tmp = web.STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.rename(tmp, web.STATE)


class Demo(object):
    """A simulated adapter with the same calls as the real client below."""
    def __init__(self):
        self.modes = [[0, 3], [1, 2], [0, 0], [0, 0]]
        self.states = [1, 2, 0, 1]
        self.profiles = {0: "Standard", 1: "Twin stick"}
        self.loaded = None

    async def info(self):
        return {"version": 1, "port_status": True, "profile_count": 4}

    async def ports(self):
        return [{"port": i, "state": self.states[i], "dev_mode": self.modes[i][0], "acc_mode": self.modes[i][1], "bt_type": 0, "bt_subtype": 0}
                for i in range(proto.PORTS)]

    async def profile_list(self, count):
        return [{"slot": s, "used": s in self.profiles, "name": self.profiles.get(s, "")} for s in range(count)]

    async def set_port(self, port, typ, acc):
        self.modes[port] = [typ, acc]
        return 0

    async def load_profile(self, slot):
        if slot not in self.profiles:
            return 1
        self.loaded = slot
        return 0


class Adapter(object):
    """The real adapter through bleak."""
    def __init__(self, client):
        self.c = client

    async def _cmd(self, data, read=True):
        await self.c.write_gatt_char(proto.CHRC_CMD, bytes(data), response=True)
        return await self.c.read_gatt_char(proto.CHRC_CMD) if read else None

    async def info(self):
        return proto.parse_info(await self._cmd([proto.CMD_GET_IBLUE_INFO]))

    async def ports(self):
        return proto.parse_ports(await self._cmd([proto.CMD_GET_PORT_STATUS]))

    async def profile_list(self, count):
        out = []
        for s in range(count):
            out.append(proto.parse_profile(await self._cmd(proto.cmd_get_profile(s))))
        return out

    async def set_port(self, port, typ, acc):
        await self.c.write_gatt_char(proto.CHRC_OUT_CTRL, bytes(proto.out_ctrl(port)), response=True)
        await self.c.write_gatt_char(proto.CHRC_OUT_DATA, bytes(proto.out_data(typ, acc)), response=True)
        return 0

    async def load_profile(self, slot):
        return bytearray(await self._cmd(proto.cmd_profile_load(slot)))[0]


async def find_address():
    from bleak import BleakScanner
    saved = None
    try:
        with open(web.DEVICE) as f:
            saved = f.read().strip()
    except (IOError, OSError):
        pass
    if saved:
        return saved
    try:
        found = await BleakScanner.discover(timeout=SCAN, return_adv=True)      # {address: (device, advertisement)}
        seen = [(addr, dev.name or adv.local_name or "", adv.service_uuids or []) for addr, (dev, adv) in found.items()]
    except TypeError:       # older bleak (the Python 3.7 of the old DreamPi image): a list of devices
        seen = [(d.address, d.name or "", (getattr(d, "metadata", None) or {}).get("uuids", [])) for d in await BleakScanner.discover(timeout=SCAN)]
    for address, name, uuids in seen:
        if proto.SERVICE in [u.lower() for u in uuids] or "blueretro" in name.lower():
            with open(web.DEVICE, "w") as f:
                f.write(address)
            return address
    return None


async def session(demo, adapter_for):
    """One connection: do the request if there is one, then read everything."""
    req = None
    try:
        with open(web.REQUEST) as f:
            req = json.load(f)
    except (IOError, OSError, ValueError):
        req = None
    async with adapter_for() as ad:
        info = await ad.info()
        if info is None or not info.get("port_status"):
            return {"found": True, "error": "This adapter's firmware has no port status yet (needs the claude/port-status firmware)"}
        result = None
        if req:
            try:
                if req.get("action") == "port":
                    code = await ad.set_port(int(req["port"]), int(req["type"]), int(req["acc"]))
                    result = {"id": req.get("id"), "ok": code == 0, "message": "Port %s changed" % proto.PORT_NAMES[int(req["port"])]}
                elif req.get("action") == "profile":
                    code = await ad.load_profile(int(req["slot"]))
                    result = {"id": req.get("id"), "ok": code == 0, "message": "Profile loaded" if code == 0 else proto.PROFILE_RESULT.get(code, "Failed")}
            except Exception as e:      # noqa: B902 - any Bluetooth error is reported to the page
                result = {"id": req.get("id"), "ok": False, "message": "Could not do it: %s" % e}
            try:
                os.remove(web.REQUEST)
            except OSError:
                pass
        ports = await ad.ports()
        profs = await ad.profile_list(info.get("profile_count", 0))
        st = {"found": True, "info": info, "ports": ports, "error": "",
              "profiles": [{"slot": p["slot"], "used": p["used"], "name": p["name"] or ("Profile %d" % (p["slot"] + 1))} for p in profs]}
        if result:
            st["result"] = result
        return st


class _DemoCtx(object):
    def __init__(self, d):
        self.d = d

    async def __aenter__(self):
        return self.d

    async def __aexit__(self, *a):
        return False


class _RealCtx(object):
    def __init__(self, address):
        from bleak import BleakClient
        self.client = BleakClient(address, timeout=15)

    async def __aenter__(self):
        await self.client.connect()
        return Adapter(self.client)

    async def __aexit__(self, *a):
        try:
            await self.client.disconnect()
        except Exception:       # noqa: B902
            pass
        return False


def looking():
    try:
        return time.time() - os.path.getmtime(web.SEEN) < LOOK
    except OSError:
        return False


async def main():
    demo = Demo() if os.path.exists(DEMO) else None
    last = 0
    last_state = {}
    while True:
        await asyncio.sleep(0.5)
        if not core.module_enabled("ibluecontrol"):
            continue
        due = os.path.exists(web.REQUEST) or (looking() and time.time() - last >= POLL)
        if not due:
            continue
        last = time.time()
        try:
            if demo:
                st = await session(True, lambda: _DemoCtx(demo))
            else:
                address = await find_address()
                if not address:
                    st = {"found": False, "error": "Adapter not found. Tap its button to open pairing, then wait a moment"}
                else:
                    st = await session(False, lambda: _RealCtx(address))
        except ImportError as e:        # bleak itself, or one of its own requirements (dbus_fast, typing_extensions ...)
            core.debug_log("iblue: import failed: %s" % e)
            fix = "sudo apt install -y python3-distutils && curl -fsSL https://bootstrap.pypa.io/pip/3.7/get-pip.py | sudo python3 && sudo python3 -m pip install 'bleak<0.21'" if sys.version_info < (3, 8) else "sudo apt install python3-bleak"
            st = {"found": False, "error": "Bluetooth library problem on python %d.%d (%s): %s. Try: %s"
                  % (sys.version_info[0], sys.version_info[1], sys.executable, e, fix)}
        except Exception as e:      # noqa: B902 - a failed connection is a state, not a crash
            core.debug_log("iblue: %s" % e)
            st = {"found": False, "error": "Could not reach the adapter (%s)" % (str(e) or e.__class__.__name__)}
            try:
                os.remove(web.REQUEST)
            except OSError:
                pass
            st["result"] = {"ok": False, "message": st["error"]}
        if "result" not in st and last_state.get("result") and time.time() - last_state.get("time", 0) < 20:
            st["result"] = last_state["result"]
        write_state(st)
        last_state = dict(st, time=time.time())


if __name__ == "__main__":
    asyncio.run(main())

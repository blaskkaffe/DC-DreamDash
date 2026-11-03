# The iBlueControlMod module: the Bluetooth protocol (pure functions), the web side's view and requests, and the service against its
# simulated adapter (no Bluetooth needed).
import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import ROOT, core, sandbox, cleanup  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "modules", "ibluecontrol"))
import netswitch_iblue_proto as proto  # noqa: E402
import netswitch_ibluecontrol as web  # noqa: E402
import netswitch_iblue_service as service  # noqa: E402


class Proto(unittest.TestCase):
    def test_info_needs_the_marker(self):
        self.assertIsNone(proto.parse_info(b"\x02"))
        info = proto.parse_info(b"iBLU\x01\x0b\x03\x04\x07")
        self.assertTrue(info["port_status"] and info["profiles"] and info["gestures"])
        self.assertFalse(proto.parse_info(b"iBLU\x01\x03\x03\x04\x07")["port_status"])      # an older firmware without the status command
        self.assertEqual(info["profile_count"], 4)

    def test_ports(self):
        raw = bytes(bytearray([4, 1, 0, 3, 5, 6,  2, 1, 2, 0, 0,  0, 0, 0, 0, 0,  1, 3, 0, 5, 6]))
        ports = proto.parse_ports(raw)
        self.assertEqual([p["state"] for p in ports], [1, 2, 0, 1])
        v = [proto.port_view(p) for p in ports]
        self.assertEqual([x["status"] for x in v], ["BT-connected", "Wired-connected", "Empty", "BT-connected"])
        self.assertEqual([x["name"] for x in v], ["A", "B", "C", "D"])
        self.assertEqual((v[0]["type_text"], v[1]["type_text"], v[3]["type_text"]), ("Normal", "Dual stick", "Mouse"))
        self.assertEqual(v[0]["acc_text"], "Both")

    def test_a_short_answer_gives_fewer_ports_not_an_error(self):
        self.assertEqual(proto.parse_ports(b""), [])
        self.assertEqual(len(proto.parse_ports(bytes(bytearray([4, 1, 0, 0, 0, 0, 1, 0])))), 1)

    def test_profile_and_commands(self):
        self.assertEqual(proto.parse_profile(b"\x01\x02Twin\x00junk")["name"], "Twin")
        self.assertFalse(proto.parse_profile(b"\x00\x01\x00")["used"])
        self.assertEqual(list(proto.cmd_profile_load(3)), [0x45, 3])
        self.assertEqual(list(proto.out_ctrl(2)), [2, 0])
        self.assertEqual(proto.CHRC_CMD, "56830f56-5180-fab0-314b-2fa176799a07")


class Web(unittest.TestCase):
    def setUp(self):
        self.tmp = sandbox()

    def tearDown(self):
        cleanup(self.tmp)

    def test_the_view_without_an_adapter_has_four_disabled_ports(self):
        v = web.view()
        self.assertEqual(v["title"], "iBluecontrolmod/blueretro")
        self.assertEqual([p["name"] for p in v["ports"]], ["A", "B", "C", "D"])
        self.assertFalse(v["online"])
        self.assertEqual(v["ports"][0]["status"], "No adapter")

    def test_the_view_shows_a_fresh_state_and_ignores_a_stale_one(self):
        import time
        ports = [{"port": i, "state": s, "dev_mode": 0, "acc_mode": 0, "bt_type": 0, "bt_subtype": 0} for i, s in enumerate((1, 2, 0, 0))]
        st = {"found": True, "ports": ports, "profiles": [{"slot": 0, "used": True, "name": "Std"}], "time": time.time()}
        json.dump(st, open(web.STATE, "w"))
        v = web.view()
        self.assertTrue(v["online"])
        self.assertEqual([p["kind"] for p in v["ports"]], ["bt", "wired", "empty", "empty"])
        st["time"] = time.time() - 600
        json.dump(st, open(web.STATE, "w"))
        self.assertFalse(web.view()["online"])

    def test_requests_are_checked_and_queued_once(self):
        class H(object):
            def __init__(self, body):
                self.body, self.sent = body, None
            def _body(self, n):
                return json.dumps(self.body).encode()
            def send(self, body, ctype, status=200):
                self.sent = (json.loads(body), status)
        h = H({"port": 9, "type": 0, "acc": 0})
        web._post_port(h)
        self.assertEqual(h.sent[1], 409)                                   # no such port
        h = H({"port": 1, "type": 7, "acc": 0})
        web._post_port(h)
        self.assertEqual(h.sent[1], 409)                                   # no such controller type
        self.assertFalse(os.path.exists(web.REQUEST))
        h = H({"port": 1, "type": 1, "acc": 2})
        web._post_port(h)
        self.assertEqual(h.sent[1], 200)
        req = json.load(open(web.REQUEST))
        self.assertEqual((req["action"], req["port"], req["type"], req["acc"]), ("port", 1, 1, 2))
        h = H({"slot": 0})
        web._post_profile(h)
        self.assertEqual(h.sent[1], 409)                                   # the adapter is still busy with the first one

    def test_the_port_buttons_are_open_while_settings_are_locked(self):
        self.assertIn("/iblue/port", web.OPEN)
        self.assertIn("/iblue/profile", web.OPEN)
        self.assertNotIn("/iblue/rescan", web.OPEN)


class Service(unittest.TestCase):
    def setUp(self):
        self.tmp = sandbox()

    def tearDown(self):
        cleanup(self.tmp)

    def run_session(self, demo):
        return asyncio.run(service.session(True, lambda: service._DemoCtx(demo)))

    def test_demo_session_reads_ports_and_profiles(self):
        st = self.run_session(service.Demo())
        self.assertEqual([p["state"] for p in st["ports"]], [1, 2, 0, 1])
        self.assertEqual([p["name"] for p in st["profiles"] if p["used"]], ["Standard", "Twin stick"])

    def test_a_port_request_changes_the_adapter_and_clears_the_request(self):
        demo = service.Demo()
        json.dump({"id": 1, "action": "port", "port": 2, "type": 1, "acc": 2}, open(web.REQUEST, "w"))
        st = self.run_session(demo)
        self.assertTrue(st["result"]["ok"])
        self.assertEqual(demo.modes[2], [1, 2])
        self.assertEqual(st["ports"][2]["dev_mode"], 1)
        self.assertFalse(os.path.exists(web.REQUEST))

    def test_loading_an_empty_profile_slot_says_so(self):
        json.dump({"id": 2, "action": "profile", "slot": 3}, open(web.REQUEST, "w"))
        st = self.run_session(service.Demo())
        self.assertFalse(st["result"]["ok"])
        self.assertIn("empty", st["result"]["message"])

    def test_old_firmware_is_explained(self):
        class Old(service.Demo):
            async def info(self):
                return {"port_status": False}
        st = self.run_session(Old())
        self.assertIn("port status", st["error"])


if __name__ == "__main__":
    unittest.main()

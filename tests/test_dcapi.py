"""The DC API module: the dc1 language (hello, get, set, call, events) over POST /dcapi, answered from the network switcher's services."""
import os
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from support import web, core, sandbox, cleanup

import netswitch_api as api
import netswitch_switcher_state as sstate

PAGE = {"X-Requested-With": "openMenu"}


def lines(text):
    return text.strip().split("\n")


class Lang(unittest.TestCase):
    """handle() directly: no server."""

    def setUp(self):
        self.tmp = sandbox()
        self.saved = (sstate.dcnet_code, list(api._ring), api._next[0], api._dropped[0], api._last[0])
        sstate.dcnet_code = lambda: "ok"
        del api._ring[:]
        api._next[0], api._dropped[0], api._last[0] = 1, 0, None

    def tearDown(self):
        sstate.dcnet_code = self.saved[0]
        api._ring[:] = self.saved[1]
        api._next[0], api._dropped[0], api._last[0] = self.saved[2:]
        cleanup(self.tmp)

    def ask(self, *ops, **kw):
        head = [api.LEVEL] + (["id " + kw["id"]] if "id" in kw else [])
        return lines(api.handle("\n".join(head + list(ops)) + "\n"))

    def test_hello(self):
        out = self.ask("get hello")
        self.assertEqual(out[0], "dc1")
        self.assertIn("ok hello.kind gateway", out)
        self.assertIn("ok hello.name DC-DreamDash", out)
        self.assertIn("ok hello.api 1", out)
        self.assertIn("ok hello.caps api,net", out)

    def test_id_is_echoed(self):
        self.assertEqual(self.ask("get net.selected", id="17")[:2], ["dc1", "id 17"])

    def test_network_keys(self):
        out = self.ask("get net.selected", "get net.dcnet", "get net.call")
        self.assertEqual(out, ["dc1", "ok net.selected dcnow", "ok net.dcnet ok", "err net.call unavailable no call"])

    def test_selected_and_call_follow_the_files(self):
        open(sstate.FLAG, "w").close()
        with open(sstate.STATE, "w") as f:
            f.write("call dcnet %d" % int(time.time()))
        out = self.ask("get net.*")
        self.assertEqual(out, ["dc1", "ok net.call dcnet", "ok net.dcnet ok", "ok net.selected dcnet"])

    def test_dcnet_off_reason(self):
        sstate.dcnet_code = lambda: "noupdates"
        self.assertEqual(self.ask("get net.dcnet")[1], "ok net.dcnet off:noupdates")

    def test_select_network(self):
        self.assertEqual(self.ask("call net.select dcnet")[1], "ok net.select dcnet")
        self.assertTrue(os.path.exists(sstate.FLAG))
        self.assertEqual(self.ask("get net.selected")[1], "ok net.selected dcnet")
        self.assertEqual(self.ask("call net.select dcnow")[1], "ok net.select dcnow")
        self.assertFalse(os.path.exists(sstate.FLAG))

    def test_select_network_bad_value(self):
        self.assertEqual(self.ask("call net.select pizza")[1], "err net.select range dcnow or dcnet")
        self.assertFalse(os.path.exists(sstate.FLAG))

    def test_set_is_refused_for_what_is_read_only(self):
        self.assertEqual(self.ask("set net.selected dcnet")[1], "err net.selected readonly")
        self.assertFalse(os.path.exists(sstate.FLAG))
        self.assertEqual(self.ask("set hello.name x")[1], "err hello.name readonly")
        self.assertEqual(self.ask("set port.A.mode dual")[1], "err port.A.mode unknown")

    def test_unknown_things_do_not_spoil_the_rest(self):
        out = self.ask("get port.A.mode", "get net.selected", "frobnicate x", "call sys.reset")
        self.assertEqual(out, ["dc1", "err port.A.mode unknown", "ok net.selected dcnow", "err frobnicate unknown", "err sys.reset unknown"])

    def test_bad_requests(self):
        self.assertEqual(lines(api.handle("get hello\n")), ["dc1", "err request bad first line must be dc1"])
        self.assertEqual(lines(api.handle("")), ["dc1", "err request bad first line must be dc1"])
        self.assertEqual(self.ask(), ["dc1"])

    def test_request_for_another_device_is_not_answered_as_ours(self):
        self.assertEqual(self.ask("to A4CF12B3", "get hello"), ["dc1", "err to unavailable no relay to other devices yet"])
        self.assertIn("ok hello.kind gateway", self.ask("to dreampi", "get hello"))

    def test_prefix_without_match(self):
        self.assertEqual(self.ask("get zzz.*")[1], "err zzz.* unknown")

    def test_blank_lines_and_crlf(self):
        out = lines(api.handle("dc1\r\n\r\nget net.selected\r\n\r\n"))
        self.assertEqual(out, ["dc1", "ok net.selected dcnow"])

    # ---- events
    def test_events_report_changes_since_a_number(self):
        self.assertEqual(self.ask("get events since=0"), ["dc1", "ok events.next 1"])
        self.ask("call net.select dcnet")
        out = self.ask("get events since=0")
        self.assertEqual(out, ["dc1", "ok events.next 2", "ev 1 net.selected dcnet"])
        self.assertEqual(self.ask("get events since=1"), ["dc1", "ok events.next 2"])

    def test_events_see_a_call_start_and_end(self):
        self.ask("get hello")                                  # the baseline
        with open(sstate.STATE, "w") as f:
            f.write("call dcnow %d" % int(time.time()))
        self.assertEqual(self.ask("get events since=0")[2:], ["ev 1 net.call dcnow"])
        with open(sstate.STATE, "w") as f:
            f.write("ready %d" % int(time.time()))
        self.assertEqual(self.ask("get events since=1")[2:], ["ev 2 net.call none"])

    def test_events_lost_when_the_ring_overflowed(self):
        self.ask("get hello")
        for i in range(api.RING + 5):
            if i % 2 == 0:
                open(sstate.FLAG, "w").close()
            elif os.path.exists(sstate.FLAG):
                os.remove(sstate.FLAG)
            api.observe()
        out = self.ask("get events since=0")
        self.assertEqual(out[1], "ok events.lost 1")
        self.assertEqual(len([l for l in out if l.startswith("ev ")]), api.RING)
        self.assertNotIn("ok events.lost 1", self.ask("get events since=%d" % (api._dropped[0] + 1)))

    def test_no_baseline_while_the_switcher_is_missing(self):
        orig = core.service
        core.service = lambda *a: None
        try:
            api.observe()
            self.assertIsNone(api._last[0])
        finally:
            core.service = orig
        api.observe()                                         # now it is there: this is the baseline, no events
        self.assertEqual(self.ask("get events since=0"), ["dc1", "ok events.next 1"])

    def test_without_the_switcher_there_are_no_net_keys(self):
        orig = core.service
        core.service = lambda *a: None
        try:
            self.assertEqual(self.ask("get net.selected")[1], "err net.selected unknown")
            self.assertEqual(self.ask("call net.select dcnet")[1], "err net.select unavailable")
            self.assertIn("ok hello.caps api,net", self.ask("get hello"))
        finally:
            core.service = orig


class Http(unittest.TestCase):
    def setUp(self):
        self.tmp = sandbox()
        self.srv = web.Server(("127.0.0.1", 0), web.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        web.refresh_page(force=True)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        cleanup(self.tmp)

    def call(self, method, path, body=None, headers=None):
        req = Request(self.base + path, data=body, method=method, headers=headers or {})
        try:
            r = urlopen(req, timeout=10)
            return r.status, r.read().decode()
        except HTTPError as e:
            return e.code, e.read().decode()

    def test_post_and_get(self):
        status, text = self.call("POST", "/dcapi", b"dc1\nid 3\nget hello\n", PAGE)
        self.assertEqual(status, 200)
        self.assertEqual(lines(text)[:2], ["dc1", "id 3"])
        self.assertIn("ok hello.caps api,net", lines(text))
        status, text = self.call("GET", "/dcapi")
        self.assertEqual(status, 200)
        self.assertIn("ok hello.kind gateway", lines(text))

    def test_select_over_http_works_while_settings_are_locked(self):
        with open(os.path.join(core.BASE_DIR, "settings_pin"), "w") as f:
            f.write("x")
        status, text = self.call("POST", "/dcapi", b"dc1\ncall net.select dcnet\n", PAGE)
        self.assertEqual(status, 200)
        self.assertIn("ok net.select dcnet", lines(text))

    def test_a_request_from_another_site_is_refused(self):
        status, _ = self.call("POST", "/dcapi", b"dc1\ncall net.select dcnet\n", {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)

    def test_a_big_body_is_cut(self):
        status, text = self.call("POST", "/dcapi", b"dc1\n" + b"get hello\n" * 2000, PAGE)
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()

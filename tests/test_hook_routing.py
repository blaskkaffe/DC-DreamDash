"""The check_number() wrapper in the DreamPi hook (against a fake Netlink class): the dialed digits decide nothing, only the
selection (the file dcnet_mode, set over the data channel) does."""
import builtins
import os
import types
import unittest

from support import sandbox, cleanup
import netswitch_dreampi as hook

builtins.__import__ = hook._original_import     # importing the hook may arm its import hook; undo that here


class FakeModule(object):
    def __init__(self, dcnet_enabled=True):
        calls = self.calls = []

        class Netlink(object):
            dcnet = dcnet_enabled
            mode = None

            def check_number(self, raw):
                calls.append(raw)
                if raw.startswith("*70"):
                    return {"client": "idle", "dial_string": raw}
                if raw.startswith("*69"):
                    return {"client": "Netlink", "dial_string": raw}
                return {"client": "PPP", "dial_string": raw}
        self.module = types.ModuleType("netlink")
        self.module.Netlink = Netlink
        self.cls = Netlink


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = sandbox(hook)
        self.fake = FakeModule()
        hook._patch(self.fake.module)
        self.nl = self.fake.cls()
        self.nl.logger = types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)

    def tearDown(self):
        cleanup(self.tmp)

    def state(self):
        with open(hook.STATE) as f:
            return f.read().rsplit(" ", 1)[0]

    def test_every_number_goes_to_dcnow_when_dcnow_is_selected(self):
        for number in ("1111111", "5550002", "5551234", "*21#"):
            self.assertEqual(self.nl.check_number(number)["client"], "PPP", number)
        self.assertFalse(os.path.exists(hook.FLAG))                       # no number ever selects anything

    def test_every_number_goes_to_dcnet_when_dcnet_is_selected(self):
        open(hook.FLAG, "w").close()
        for number in ("1111111", "5550001", "5551234"):
            r = self.nl.check_number(number)
            self.assertEqual((r["client"], r["dial_string"]), ("dcnet", number), number)
        self.assertTrue(os.path.exists(hook.FLAG))                        # and no number ever deselects it

    def test_the_call_state_follows_the_network_used(self):
        self.nl.check_number("1111111")
        self.assertEqual(self.state(), "call dcnow")
        open(hook.FLAG, "w").close()
        self.nl.check_number("1111111")
        self.assertEqual(self.state(), "call dcnet")

    def test_dcnet_not_enabled_falls_back_to_dcnow(self):
        fake = FakeModule(dcnet_enabled=False)
        hook._patch(fake.module)
        nl = fake.cls()
        nl.logger = self.nl.logger
        open(hook.FLAG, "w").close()
        self.assertEqual(nl.check_number("1111111")["client"], "PPP")

    def test_dreampis_own_codes_pass_through(self):
        open(hook.FLAG, "w").close()
        self.assertEqual(self.nl.check_number("*70")["client"], "idle")
        self.assertEqual(self.nl.check_number("*69")["client"], "Netlink")
        self.assertEqual(self.fake.calls, ["*70", "*69"])

    def test_patching_twice_wraps_once(self):
        before = self.fake.cls.check_number
        hook._patch(self.fake.module)
        self.assertIs(self.fake.cls.check_number, before)

    def test_the_hook_has_no_phone_number_machinery_left(self):
        for gone in ("_matches", "_action", "_Call", "_play_busy", "DEFAULT_ROW", "BUSY_SECONDS"):
            self.assertFalse(hasattr(hook, gone), gone)


if __name__ == "__main__":
    unittest.main()

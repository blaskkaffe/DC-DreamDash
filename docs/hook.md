# The hook, call routing and the debug log

Read before touching `modules/switcher/netswitch_dreampi.py`, the call routing or the debug timeline. Back to [CLAUDE.md](../CLAUDE.md).

## How the hook loads

- The `.pth` file (written by `modules/switcher/install.sh`, it names `/opt/dreampi-netswitch/modules/switcher`; the base installer knows nothing about it) imports `netswitch_dreampi`, the network switcher module's DreamPi integration. It only acts when `/proc/self/cmdline` contains `dreampi` (`sys.argv` doesn't exist yet during `.pth` processing on Python 2). It then temporarily wraps `__import__`, using `__builtin__` before `builtins` because python-future can provide a fake `builtins` on Python 2. When a module named `netlink` is imported from `/home/pi/dreampi`, it wraps `Netlink.check_number()` and restores the original `__import__`.
- State lives in files: `/opt/dreampi-netswitch/dcnet_mode` (exists means DCNet is selected), DCNow! is selected again after every reboot (`netswitch_switcher_state.reset_network_after_boot()`, run by the switcher module's `start()` (web service) and its buttons service when they start: it compares the kernel's boot id with `boot_id` in the add-on folder and removes `dcnet_mode` when it differs; the first run after an install only records the id; the hook itself doesn't do this, it only reads the file). The hook writes `/tmp/dreampi-netswitch.active` (`active pid=N` or an error). The hook also writes `/tmp/dreampi-netswitch.state` (`starting`, `ready`, `call <network>` or `unknown`, plus a unix time): `starting` when netlink is imported, `call ...` from `check_number()`, and `ready` after `__main__.Modem.start_dial_tone()` (the moment DreamPi logs `<LISTENING>`) or `Netlink.reset_serial()`. The web page checks that pid under `/proc`, and also reads `netlink_config.ini` and `/boot/noautoupdates.txt` to warn when DCNet is off.
- DreamPi's state (`/tmp/dreampi-netswitch.state`): `starting` when the hook is loaded, `ready` when DreamPi has started the dial tone (the hook wraps `Modem.start_dial_tone` and the Netlink `reset_serial`), `call <network>` when a call is routed. With DreamPi's `--disable-dial-tone` it never calls `start_dial_tone` (its rule: `dial_tone_enabled = "--disable-dial-tone" not in sys.argv`), so the hook then wraps `Modem.connect` instead: DreamPi listens as soon as the modem is opened, at the start and after every call (a few seconds before DreamPi has finished resetting the modem). Without that the page and the LED stayed on "Starting up" for ever. Read from DreamPi's `dreampi.py` (master); tested with fake classes, not on a Pi.
- Modem status: the hook adds a `logging.Handler` to DreamPi's `dreampi` logger and maps DreamPi's own messages (`<LISTENING>`, `Heard:`, `CONNECT 33600`, `Call answered`, `Connected`, `Detected modem hang up`, ...) to a short text in `/tmp/dreampi-netswitch.modem` (`<unix time> <text>`). Table `_MODEM_EVENTS`; keep it in sync if upstream log texts change. The same table's `Opening serial interface to (\S+)` row also writes the raw port (e.g. `/dev/ttyUSB0`) to `/tmp/dreampi-netswitch.port`, which is how the web service finds the modem without guessing or parsing `netlink_config.ini`.

## Debug log

The **debug log module** (`modules/debuglog/`) owns this: its `netswitch_hookdebug.py` is loaded by the hook (`_debug_part()`, only while the module is installed and on; Python 2 compatible) and does the writing, so without the module the hook logs nothing. If `/opt/dreampi-netswitch/debug_dtmf` exists (the page's Recording switch, `POST /debug`), the hook writes one timeline to `/tmp/dreampi-netswitch-dtmf.log` (`HH:MM:SS.mmm  +Nms  text`):
- modem bytes read while `modem._sending_tone` is true, decoded by `_serial_feed()`: `<DLE><digit>` -> `modem: DTMF x`, other `<DLE>` codes via `_DLE_CODES` (V.253), text lines -> `modem says: ...`. The hook replaces `read` on the pyserial object again after every `start_dial_tone()`, since DreamPi opens a new serial object after each call;
- every message on DreamPi's `dreampi` logger (`dreampi: ...`), via the same handler as the modem status;
- the hook's own routing lines.
The web service trims the log to its newest 500 KB whenever it passes 1 MB (`trim_log()` in the checker loop; safe because the hook opens the file per line). `GET /dtmf` serves the newest 256 KB (`?all` for everything). Responses over 2 KB are gzip-compressed when the browser accepts it. The web page appends its own actions (`web page: ...`), serves new text incrementally at `GET /log?from=<byte offset>` (JSON; `reset` when the file was cleared), shows it live in a panel polled every 0.7 s, and has `POST /debug` (toggle) and `POST /clearlog`. The page's status poll runs every 1 s.

## Upstream facts the hook depends on (netlink.py, dpi2 branch)

- `check_number(self, raw_string)` returns `{'client': mode, 'dial_string': ...}`. `dreampi.py` answers with its own pppd only when `client == 'PPP'`. Any other non-idle mode is handled by `Netlink.poll()` -> `mode_handler()`.
- Mode `"dcnet"` makes `mode_handler()` call `dcnet_connect()`, which answers and runs `dcnet.rpi`. This is the same route the built-in `*69` prefix uses: it stores `self.dial_modifier` in memory, valid for 10 seconds.
- `self.dcnet` is True only when `netlink_config.ini` has `[DCNet] enabled = yes` and `dcnet.rpi` exists.
- The serial-port path (`serial_poll`) also calls `check_number()` and handles `"dcnet"`.
- openMenu 1.7.0 always dials `1111111` with login `openMenu`/`openMenu` (see `dcnow_net.h` in the openMenu repository). DCNet expects the password `password`. **Since the phone numbers were removed** nothing in the dialed number selects DCNow! for openMenu. Decision (see `docs/unified/03-decisions.md`, D-5): openMenu has to work equally well on both networks. It tries DCNET's login as well (a login that fails on one network is retried with the other's), and once connected it learns from the poll reply which network it is on (`CALL`) and which one is selected (`NET`), so it can tell the player or switch with `POST /dcnow` / `POST /dcnet`. The openMenu side is not written yet.
- If upstream renames `check_number`, the hook writes an error to the status file and does nothing, and DreamPi keeps working.

## Routing rules

The dialed number decides nothing. `check_number()` in the hook calls the original, then:

- A `PPP` result goes to DCNET when `dcnet_mode` exists and `self.dcnet` is true (`self.mode = "dcnet"`, result `{"client": "dcnet", ...}`); if DCNET is selected but not enabled in `netlink_config.ini`, the call stays on DCNow! and the log says so.
- Netlink/XBAND results, DreamPi's own `*69` / `*70` prefixes and idle results pass through unchanged.
- The call state (`call dcnow` / `call dcnet`) is written for every non-idle result.

The selection (`dcnet_mode`) is written over the data channel or by hand: the page's buttons, the GPIO buttons, `POST /dcnow` and `POST /dcnet` (openMenu). There is no hang-up number, no busy tone and no number matching; `tests/test_hook_routing.py` checks that no number ever changes the selection.

## Testing the routing without a Pi

Download the current `netlink.py`, place it at `/home/pi/dreampi/netlink.py`, stub the `serial`, `stun` and `sh` modules, load the `.pth` with `site.addsitedir()`, create the object with `Netlink.__new__(Netlink)`, set `logger`, `servers`, `dcnet`, `dial_modifier` and `mode`, then call `check_number()` for each rule. Also check that `netlink.py`'s hash is unchanged afterwards.

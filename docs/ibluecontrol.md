# iBlueControlMod / BlueRetro module

Back to [CLAUDE.md](../CLAUDE.md). Module folder: `modules/ibluecontrol/`. Default: **off** (switch it on in Settings > Modules).

## What it does

A dashboard box headed **iBluecontrolmod/blueretro** with four port tiles (A to D). Each is coloured in the port's palette colour (full colour for Bluetooth, paler for wired, only the border for an empty port) (A orange, B green, C blue, D bright pink as the nearest to the Dreamcast's magenta; change them in Settings > Appearance) and has the port letter, then **BT**,
**Wired** or **Empty**, and at the bottom the name the adapter tells the Dreamcast for that port (Controller, Keyboard or Mouse; the
"Dreamcast " of the Maple name is left out so it fits; nothing for an empty port). Normal and Dual stick both say Controller; the popup shows which.
**A wired port** shows no name and has no settings: the adapter only sees that something is plugged in, not what it is, so its popup just says so. Tapping a button opens a
pop-up under the row, **also for a port that has a controller**, with:

- **Controller type**: the Dreamcast output mode of that port (BlueRetro `GamePad`, `GamePadAlt`, `Keyboard`, `Mouse`; shown as Normal,
  Dual stick, Keyboard, Mouse. "Dual stick" is the label for `GamePadAlt`; check it against your adapter).
- **Accessory**: None, VMU, Rumble, Both (the port's accessory mode), four in a row.
- **Profile**: loads one of the adapter's saved profiles. A profile is a copy of the whole BlueRetro configuration, mapping included, so
  loading one changes the button mapping of all ports. Editing single buttons of the mapping is not in this module (use blueretro.io).

The pop-up buttons are dashboard buttons: they stay usable while Settings is locked with the PIN. **Search again** (Settings >
iBlueControlMod) forgets the adapter's address.

## Pieces

| File | What |
|---|---|
| `netswitch_iblue_proto.py` | The adapter's Bluetooth protocol as pure functions (UUIDs, command bytes, parsing, labels). Python 2 and 3. |
| `netswitch_ibluecontrol.py` | Web entry: `GET /iblue/view` (what the box shows), `POST /iblue/port {port, type, acc}`, `POST /iblue/profile {slot}`, `POST /iblue/rescan`. Writes requests as a file, never talks Bluetooth. |
| `netswitch_iblue_service.py` | The module's own service `dreampi-netswitch-iblue` (root; the only code using Bluetooth, through the Python package `bleak` and BlueZ). |
| `page.js` | The custom widget `iblue-ports`. |
| `install.sh` / `remove.sh` | Install `bleak` (apt `python3-bleak`, pip as fallback; `bleak<0.21` on Python 3.7, the old DreamPi image) and the service; remove them. DreamPi's own files are never touched. |

State files (no sockets between the web service and the service): `/tmp/dreampi-netswitch.iblue` (service to web: ports, profiles,
last result, error), `.iblue_request` (web to service, one request at a time), `.iblue_seen` (touched by every `GET /iblue/view`),
and `/opt/dreampi-netswitch/iblue_device` (the adapter's address once found). `iblue_demo` in the add-on folder makes the service use a
simulated adapter (`IBLUE=1 python3 tests/ui/demo_server.py`).

## How it talks to the adapter

The service connects over Bluetooth LE to the adapter's BlueRetro config service
(`56830f56-5180-fab0-314b-2fa176799a00`), **only while a page is looking** (every 15 s, one short connection: read, then disconnect), and
at once when the page asks for a change.

- Port type and accessory: write the port number (uint16 LE) to the output-config control characteristic (`...9a02`), then
  `[dev_mode, acc_mode]` to the output-config data characteristic (`...9a03`), as blueretro.io does.
- Profiles: commands `0x43` (get), `0x45` (load) on the command characteristic (`...9a07`), already in the firmware (`main`).
- **Port status: command `0x4B`**, a read-only command added to the firmware for this module (branch `claude/port-status` of
  iBlueControlMod; patch in the pull request). The answer is `[count, then per port: state (0 empty, 1 Bluetooth, 2 wired), dev_mode,
  acc_mode, BT type, BT subtype]`. A port is wired when its sense line is pulled to ground (the same test the firmware uses to skip
  that port when it hands out Bluetooth slots), Bluetooth when a controller with finished HID setup is mapped to it, otherwise empty.
  The info command `0x40` sets feature bit 3 when the command exists; with an older firmware the box says so and nothing else works.

## Not verified on hardware (see [hardware-status.md](hardware-status.md))

Everything here is tested with the simulated adapter only. Open questions for a first run on a real adapter:

1. **Can the Pi connect at all outside the pairing window?** The firmware only runs inquiry/advertising for 60 s after power-on or a
   tap on the button (`CONFIG_BLUERETRO_IBLUE_PAIR_WINDOW_S`). If it does not accept a Bluetooth LE connection outside that window, the
   box says "Adapter not found. Tap its button..." and the firmware needs a small change (always connectable for config).
2. **Does a short config connection move the controllers?** A connected config client takes one of the adapter's Bluetooth device slots,
   and the firmware numbers ports by slot. The module keeps the connection short for that reason; whether ports shift during it is
   unknown.
3. The scan finds the adapter by its advertised service UUID or a name containing "BlueRetro".
4. The firmware command `0x4B` has not been compiled or flashed (no ESP-IDF build here).

## Later

- Read what is plugged into a wired port (and its settings) from openMenu on the Dreamcast, over the modem or the serial link the openMenu module already uses. Not started; the adapter itself cannot see it.

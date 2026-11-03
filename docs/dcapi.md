# DC API (`dc1`): the control language, Pi side

The Dreamcast ecosystem (openMenu, the adapters, this Pi, DC-PicoLink) is meant to speak one small text language, `dc1`. The shared design is `04-control-channel.md` in the Unified Dreamcast Ecosystem Project (snapshot: `docs/unified/`). This page is what **this repository** has built of it: the `api` module (`modules/api/netswitch_api.py`).

**Status: written and host-tested (`tests/test_dcapi.py`). Not tried with openMenu or on a Dreamcast** (openMenu has no client for it yet). It offers the capabilities `api` and `net` only; `link`, `online`, the relay to adapters and the Maple/BLE bindings are later steps of the plan.

## Using it

```
curl -s -X POST --data-binary $'dc1\nid 1\nget hello\nget net.*\n' -H 'X-Requested-With: openMenu' http://localhost/dcapi
```

`POST /dcapi` takes the request as text and answers text; `GET /dcapi` answers `get hello` and `get net.*`, to look with a browser. The path works while Settings are locked with the PIN (the PIN is for the web page only, decision D-12), and like the other POSTs it refuses requests that carry another site's `Origin`.

| Request line | Meaning |
|---|---|
| `dc1` | first line, required: the language level |
| `id N` | optional, echoed |
| `to X` | optional: who the request is for. Only this Pi (`dreampi`, `gateway`) answers; any other target gets `err to unavailable ...` (no relay yet) |
| `get <key>`, `get <prefix>*` | read; `get hello` lists the hello keys |
| `get events since=N` | changes since number N (below) |
| `set <key> <value>` | nothing here is writable yet: known keys answer `readonly`, others `unknown` |
| `call net.select dcnow\|dcnet` | selects the network (the same as the page's buttons and `POST /dcnow` / `/dcnet`) |

The answer is `dc1`, the echoed `id`, then `ok <key> <value>` or `err <key> <code> [why]` lines, in order. An unknown key or verb only gives its own `err ... unknown` line.

## Keys

| Key | Value |
|---|---|
| `hello.kind` `hello.name` `hello.version` `hello.api` `hello.caps` | `gateway`, `DC-DreamDash`, the installed version, `1`, `api,net` |
| `net.selected` | `dcnow` or `dcnet`: the network the user selected |
| `net.call` | the network of the call DreamPi is in; `err ... unavailable no call` when none |
| `net.dcnet` | `ok`, or `off:<why>` (`config`, `disabled`, `noupdates`, `inactive`) |

These are the same facts the openMenu poll carries as `NET`, `CALL` and `DCNET`; the poll keeps working unchanged.

## Events

`get events since=N` answers `ok events.next M` (the number the next change will get) and `ev <n> <key> <value>` for each change with n above N. The last 32 changes are kept in memory; if N is older, the answer starts with `ok events.lost 1` and the client reads the keys it cares about again. A key that disappears (the call ended) is reported with the value `none`. The web service looks for changes every 2 seconds and at every request. The first look after a start is a baseline, not a change. The numbers start again when the web service restarts.

## How it fits the module rules

The module reads nothing from other modules' code: it asks the network switcher through two services it offers, `net:state` and `net:select` (`core.service()`), so with the switcher absent the `net.*` keys are simply unknown. The switcher's buttons and this module share `select_network()`.

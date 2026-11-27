# Wardriving module: preparation (issue #16)

Status: **preparation**, the module itself is not written. This page says what already exists and what is still to build, now that the parts are there.

## What we have

| part | where | state |
|---|---|---|
| Wi-Fi scan as a normal user (`iwlist wlan0 scan` through a narrow sudo rule), parser, `merge` of what was seen | `gothi/wifi.py`, bundled module Wi-Fi scan | done (0.12.0) |
| a GPS position with a fix, in the background | `gothi-gps`: `gps-stream.py --raw` and the track recorder (`gps-track`), which keeps its latest fix in `~/.cache/gothi/gps-track.json` | done (gothi-gps 0.3.0), **not tested under the open sky yet** (#18) |
| a track in GPX of the whole route | the same recorder | done |
| a background process with a pid file, a state file and `start` / `stop` / `status` | `gothi-gps/module-track/recorder.py`, the torch of the Flashlight module | pattern to copy |
| screens: menus, statistics pages, graphs | `gothi/ui.py`, `gothi/sensors.py` (`Series`, `trace`) | done |
| modem and cell info (cell ID, signal) | issue #21 | not yet |

So the two hard unknowns of the old plan (how to scan as a normal user, how to get a position) are solved. What is left is the glue, the store and the screens.

## Design

**One session = one recorder + one scanner.** `wardrive.py start` (a background process like the track recorder) does this every few seconds:

1. read the latest fix from `gps-track.json` (the file has a time; a fix older than ~5 s counts as no fix);
2. run the Wi-Fi scan (`gothi.wifi.scan`, about a second);
3. write what was heard together with the position.

If the track recorder is not running, `start` **starts it** (so a wardriving session also makes a GPX of the route, and the GPS has one owner). `stop` stops the scanner, and stops the recorder only if the wardriving started it.

**Where a network is.** The position of a network is where its signal was the strongest in the session (an access point is nearest to where you hear it loudest). A sample is kept per scan only when there is a fix; without a fix the scan goes on (it still counts networks) but nothing is written to the map, and the screen says "no position".

**Store.** SQLite (in the standard library) in `~/MyDocs/gothi/wardrive/wardrive.db`:

- `networks(bssid PRIMARY KEY, ssid, security, channel, best_signal, lat, lon, alt, first_seen, last_seen, seen)`: one row per BSSID, updated when a stronger sample arrives;
- `samples(id, bssid, time, signal, lat, lon, accuracy)`: raw samples, off by default (a setting), because they grow fast.

Writes are committed in batches of a few seconds, so a dead battery loses a few seconds, not the session. Everything stays on the phone.

**Export** (only when asked, nothing is uploaded):

- **WiGLE CSV**: the first line `WigleWifi-1.4,appRelease=...,model=N900,release=...,device=RX-51,display=,board=,brand=Nokia`, then the header `MAC,SSID,AuthMode,FirstSeen,Channel,RSSI,CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,Type` and one row per network (`Type` is `WIFI`, `AuthMode` like `[WPA2-PSK-CCMP][ESS]`). The format is written from memory: **check it against the documentation of WiGLE before the first upload**.
- **GPX** of the route (already made by the recorder) and a **KML** of the networks as points, for a map on the computer.

**Screens** (a `python` module, menu Modules): *Session* (start / stop, live counters: networks, new in this session, with a position, distance, time), *Statistics* (open vs. encrypted, by security type, by channel, strongest, the rate of new networks over the session as a graph), *Networks* (the list with a detail), *Export*.

**Dolphin.** Deeds for a new network (a daily group with a limit, so that XP does not run away) and for the end of a session.

## Rules

- **Passive only.** No connecting, no deauthentication, no injection, no password guessing. The module records what the networks announce, as the Wi-Fi scan already does.
- **Personal data.** A list of SSIDs with places is personal data: it stays on the phone, the README says so, the export is an explicit action. A home network's name and place can identify a person, so the README warns before uploading anywhere public.
- **Battery.** GPS plus a scan every few seconds drains the N900. The screen may be off while it logs. A setting stops the session below a battery percentage (the battery is read like in `gothi/sysinfo.py`).
- **A scan may disturb a connected Wi-Fi.** The N900 scan is short, but the module warns and the period is a setting (5 to 10 s).

## Testing without the sky

- the scanner and the position are injected: a fake scan (the parser tests already have made-up `iwlist` text) and a fake position feed that replays a made-up route, so the whole session runs in unit tests;
- the store, the "strongest sample wins" rule, the statistics and both exports are pure functions over rows;
- the background process is tested the way the recorder is: a real fork with fake helpers;
- the real test is outdoors (a walk with the module in a pocket), together with #18.

## Steps

- [ ] 1. `gothi/wardrive.py`: store, the strongest-sample rule, statistics, WiGLE CSV and KML, with tests.
- [ ] 2. The session process (scan + latest fix + store), start / stop / status, tests with fakes.
- [ ] 3. Screens: Session, Statistics, Networks, Export.
- [ ] 4. Deeds, README with screenshots made from made-up data.
- [ ] 5. A real test outdoors (needs a GPS fix, #18), then tune the period and the filters.
- [ ] 6. Later: Bluetooth devices in the same store (`bluedriving`), cell IDs from #21.

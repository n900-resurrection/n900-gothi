# Sensors module: design (issue #20)

Status: **implemented in gothi 0.15.0** (steps 1 and 2; the open questions below are not answered yet). Everything below that says "read on the test phone" was read there with `cat`, without writing anything.

## What the N900 has

| sensor | driver / interface | what it gives | read on the test phone |
|---|---|---|---|
| accelerometer | `lis302dl`, `/sys/bus/i2c/drivers/lis302dl/3-001d/coord` | `x y z` in mg (1000 = 1 g), 100 Hz by default (`rate`), `scale` normal | `18 -450 -918`, readable as the normal user; `enable` says `off` and the values still come |
| ambient light | `tsl2563`, `/sys/class/i2c-adapter/i2c-2/2-0029/lux` (+ `adc0`, `adc1`, `calib0`, `calib1`) | lux, calibrated by the driver | `1492` indoors |
| proximity | `/sys/devices/platform/gpio-switch/proximity/state` | one bit: `open` / `closed` (not a distance) | `open` |
| keyboard slide | `.../gpio-switch/slide/state` | `open` / `closed` | `open` |
| keyboard lock | `.../gpio-switch/kb_lock/state` | the lock slider on the top edge | `open` |
| camera lens cover | `.../gpio-switch/cam_shutter/state` | cover `open` / `closed` | `open` |
| camera buttons | `.../cam_focus/state`, `.../cam_launch/state` | half press, launch key | `inactive` |
| headphone jack | `.../gpio-switch/headphone/state` | `connected` / `disconnected` | `disconnected` |
| battery | HAL (`gothi/sysinfo.py` already reads it) | percent, voltage, charging; temperature to check | already in the Battery page |

The N900 has **no gyroscope, compass or barometer**, so there is no heading and no height. The proximity sensor is on/off only.

## Screens

A bundled `python` module (`modules/sensors`, menu Modules) like Wi-Fi scan, one menu:

1. **Overview**: all values on one page, refreshed ~5x a second:
   ```
   Sensors
   acc   18 -450 -918
   light 1492 lx
   prox  open     slide open
   lens  open     jack  out
   ```
2. **Level**: a bubble level. The bubble moves with the tilt (x, y of the gravity vector), the title shows the tilt in degrees; OK sets the **zero** here (for a table that is not flat), saved in `~/.config/gothi/sensors.json`.
3. **Accelerometer**: a scrolling trace of the last ~10 seconds (three lines, or the magnitude on the small screen), the strength in g, and a **shake counter** (the magnitude over 1.8 g counts as a shake, with a pause between two).
4. **Light**: the lux number, a logarithmic bar (the range is 0 to 50000), a word (dark / dim / indoor / bright / sun), and a 60-second trace. Useful to choose the brightness, later it could drive an auto-brightness switch.
5. **Switches**: a live list of the switches above with a **log of changes** (time, name, new state): slide the keyboard, cover the lens, plug the headphones, and a line appears. This is also how to find out which hardware keys exist.

A screen that cannot read its sensor says so instead of failing, so the module is harmless on a phone where one is missing.

## Code

- `gothi/sensors.py`, pure functions over text, testable without a phone (like `wifi.py` and `bluetooth.py`): `parse_coord`, `tilt(x, y, z)` (pitch and roll in degrees), `magnitude`, `bubble(x, y, w, h)` (the pixel of the bubble), `lux_word`, `lux_bar`, a `Series` ring buffer for the traces, `read_switches(root)`, `Shake` detector, and a `Sampler` that reads the few small sysfs files from `tick()` (a read takes well under a millisecond, so no thread is needed), only while a sensor screen is on top.
- The sysfs root is a parameter (`root="/"`), so the tests build a fake tree in a temporary folder.
- `modules/sensors/module.py` has the screens (`Menu`, `Scene`, `ScrollView` of `gothi/ui.py`) and `create(module)`.
- Deeds for the dolphin: `sensors_view` (opening the module), `level_used`, `shake` (first shake).
- The `enable` file of the accelerometer is **not touched**: other programs may use it. If the values stop changing when it is `off` on some phones, the module will say "no data" and the setting can be revisited.

## Tests

- Unit tests: parsing (good, empty, garbage), tilt angles for the six positions of the phone, the bubble stays inside its circle, the shake detector (one shake, a noisy table, two shakes a second apart), lux words at the limits, `Series` wrap, the switch log with a fake tree, each screen draws on 64 and 80 rows, a missing sensor.
- Phone tests (`test.sh`): only reads: the module is offered, the files exist and parse, the magnitude of a phone at rest is between 0.8 and 1.3 g, lux is a number.
- Screenshots in the README are made on the PC with made-up values.

## Open questions (need the phone in hand)

1. ~~The **axis signs**~~: answered by the author: the top left corner of the screen is x and y with a minus, so x is to the right and y is down (the screen's own axes) and z into the display (face up reads about -920). The sensor gives the reaction to gravity, so a positive value means that side is higher and the bubble goes to the high side. Still to confirm: landscape use reads y near -1000.
2. ~~How often does the light sensor refresh?~~ Answered: about twice a second (the module reads five times a second, which is enough).
3. ~~Does `enable = off` mean stale values?~~ Answered: no, the data are fresh and the shakes are counted well.
4. ~~`proximity`~~: answered, `closed` means something covers the sensor (confirmed on the phone in a case).

## Steps

1. `gothi/sensors.py` + unit tests + the Overview and Switches screens (the safest ones).
2. Level, Accelerometer and Light with their tests and screenshots.
3. Tuning on the phone (signs, thresholds, rates), README, a release as gothi 0.15.0.
4. Later, not now: tilt to scroll a list, shake as a gesture, auto-brightness from the light sensor.

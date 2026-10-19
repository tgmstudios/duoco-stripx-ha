# DuoCo StripX (MELK-OA21) for Home Assistant

Local Bluetooth Low Energy control of DuoCo StripX LED strip controllers that advertise as `MELK-OA21`. No cloud, account, or API key.

**Status: 0.1.0, pre-release.** Verified on one controller; protocol is derived from the vendor app's published command layout, and not every mode has been confirmed on hardware.

## Compatibility and testing
- HACS/Home Assistant minimum is declared as 2025.1.0; that minimum is **untested**.
- Automated tests ran against Home Assistant 2026.2.3, and module import was checked on 2026.8.2. This does not mean the integration is fully functional on all versions.
- Hardware verification covers one controller only. The 213 app-derived effect IDs are available; 210 are enabled by default and the 3 strobe IDs (196-198) are hidden unless enabled. No hardware claim is made for every effect.
- No LICENSE file is included; no license has been chosen, so reuse rights are not granted by this repository's visibility alone.

## Features
- Light: on/off, RGB colour, brightness (0-100 % on the wire), effects.
- Number: effect speed (0-100 %).
- Effects: the app's "Basic, Curtain, Trans, Water, Flow, Tail, Run, RunBack" groups (213 IDs). Labels are the app's; "Back" variants keep the app's names (no directions are invented). Strobe effects (3) are hidden unless enabled in the integration options (photosensitivity).
- Built-in "Scenes" (an OC/OT feature) are not exposed.

## Honest limitations
- **State is assumed.** The controller reports nothing back (its readable characteristic only returns a firmware string and it sends no notifications). Entities have `assumed_state: true`; a successful BLE write means the frame was sent, **not** that the light changed. State starts `unknown` and stays unknown until the first command; values from before a restart are shown only as `last_known_*` attributes (never as current state) and nothing is written to the device. State is also cleared when the controller stops advertising (likely power cycle) and when a command is cancelled or fails mid-write. Disconnects are bounded to 5 s.
- Nothing is written at startup, load or restore. Setup only connects to read the firmware string.
- Not supported: Wi-Fi, white/CCT, LED count/geometry/pairing/init commands, music/microphone, timers. (The app's pixel-count frame is implemented in `protocol.py` but is never sent automatically since it is persistent device configuration.)
- Each command connects, writes (write-without-response, GATT `fff3`), and disconnects, so the phone app can still be used between commands. Availability comes from passive Bluetooth advertisements. A failed command raises an error, marks the entity unavailable until the device is seen again, and forgets the assumed values.
- Requires a Home Assistant Bluetooth adapter or proxy in range.

## Install (HACS custom repository or manual)
Copy `custom_components/duoco_stripx` to your config directory, restart, then add the integration. Enter the controller's Bluetooth address and confirm you own it. Discovery of nearby `MELK-OA21` devices only *prompts*; nothing is added or controlled without confirmation.

## Protocol (9-byte frames, characteristic `0000fff3-0000-1000-8000-00805f9b34fb`)
| Action | Frame |
|---|---|
| Power on / off | `7e0404010001ff00ef` / `7e0404000000ff00ef` |
| RGB | `7e070503RRGGBB10ef` |
| Brightness 0-100 | `7e0401VVffffff00ef` |
| Speed 0-100 | `7e0402VVffffff00ef` |
| Effect | `7e0503ID06ffff00ef` |

Inputs are strictly validated (no clamping; booleans, floats, NaN rejected).

## Development
`pytest` with `pytest-homeassistant-custom-component`. No license has been selected yet.

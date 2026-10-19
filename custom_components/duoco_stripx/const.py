"""Constants for the DuoCo StripX integration."""

DOMAIN = "duoco_stripx"

CONF_ADDRESS = "address"
CONF_NAME = "name"
CONF_OWNED = "confirm_owned"
CONF_FIRMWARE = "firmware"
OPT_ALLOW_FLASHING = "allow_flashing_effects"

SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"

NAME_PATTERN = r"^MELK-OA21"
CONNECT_ATTEMPTS = 3
OPERATION_TIMEOUT = 25.0
DISCONNECT_TIMEOUT = 5.0  # hard cap on client.disconnect(); a hung disconnect must not hold the device lock

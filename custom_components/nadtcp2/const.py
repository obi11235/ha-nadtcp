"""Constants for the NAD C338 integration."""

DOMAIN = "nadtcp2"

PLATFORMS = ["media_player"]

CONF_HOST = "host"
CONF_MIN_VOLUME = "min_volume"
CONF_MAX_VOLUME = "max_volume"
CONF_VOLUME_STEP = "volume_step"
CONF_RECONNECT_INTERVAL = "reconnect_interval"

DEFAULT_NAME = "NAD amplifier"
DEFAULT_MIN_VOLUME = -80
DEFAULT_MAX_VOLUME = -10
DEFAULT_VOLUME_STEP = 4
DEFAULT_RECONNECT_INTERVAL = 10

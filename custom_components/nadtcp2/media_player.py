"""Support for NAD digital amplifiers which can be remote controlled via tcp/ip."""
from __future__ import annotations

import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    PLATFORM_SCHEMA,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_HOST,
    CONF_MAX_VOLUME,
    CONF_MIN_VOLUME,
    CONF_RECONNECT_INTERVAL,
    CONF_VOLUME_STEP,
    DEFAULT_MAX_VOLUME,
    DEFAULT_MIN_VOLUME,
    DEFAULT_NAME,
    DEFAULT_RECONNECT_INTERVAL,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
)
from .nad_client import (
    CMD_MUTE,
    CMD_POWER,
    CMD_SOURCE,
    CMD_VOLUME,
    NADReceiverTCPC338,
)

_LOGGER = logging.getLogger(__name__)

SIGNAL_NAD_STATE_RECEIVED = "nad_state_received"

SUPPORT_NAD = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.SELECT_SOURCE
)

# Kept for backwards compatibility with existing YAML configurations; new
# configurations should use the UI (config flow).
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_RECONNECT_INTERVAL,
                 default=DEFAULT_RECONNECT_INTERVAL): int,
    vol.Optional(CONF_MIN_VOLUME, default=DEFAULT_MIN_VOLUME): int,
    vol.Optional(CONF_MAX_VOLUME, default=DEFAULT_MAX_VOLUME): int,
    vol.Optional(CONF_VOLUME_STEP, default=DEFAULT_VOLUME_STEP): int,
})


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
) -> None:
    """Import a YAML `media_player` platform config into a config entry."""
    _LOGGER.warning(
        "Configuring the NAD C338 integration via YAML is deprecated and "
        "will be imported into the UI. Remove the `media_player` platform "
        "block from your configuration once the import has completed"
    )
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=dict(config)
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the NAD amplifier from a config entry."""
    options = entry.options
    async_add_entities([NADEntity(
        entry.entry_id,
        entry.data.get(CONF_NAME, DEFAULT_NAME),
        entry.data[CONF_HOST],
        options.get(CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL),
        options.get(CONF_MIN_VOLUME, DEFAULT_MIN_VOLUME),
        options.get(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME),
        options.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP),
    )])


class NADEntity(MediaPlayerEntity):
    """Entity handler for the NAD protocol."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_icon = "mdi:speaker-multiple"
    _attr_supported_features = SUPPORT_NAD

    def __init__(self, unique_id, name, host, reconnect_interval,
                 min_volume, max_volume, volume_step):
        """Initialize the entity properties."""
        self._client = None
        self._host = host
        self._reconnect_interval = reconnect_interval
        self._min_vol = min_volume
        self._max_vol = max_volume
        self._volume_step = volume_step

        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=name,
            manufacturer="NAD",
            model="C338",
        )

        self._state = STATE_UNKNOWN
        self._muted = None
        self._volume = None
        self._source = None

    def nad_vol_to_internal_vol(self, nad_vol):
        """Convert the device volume range to the internal 0..1 range.

        Takes into account configured min and max volume.
        """
        if nad_vol is None or nad_vol < self._min_vol:
            return 0.0
        if nad_vol > self._max_vol:
            return 1.0
        return (nad_vol - self._min_vol) / (self._max_vol - self._min_vol)

    def internal_vol_to_nad_vol(self, internal_vol):
        """Convert the internal 0..1 range back to the device volume range."""
        return int(round(
            internal_vol * (self._max_vol - self._min_vol) + self._min_vol))

    @property
    def state(self):
        """Return the state of the entity."""
        return self._state

    @property
    def source(self):
        """Name of the current input source."""
        return self._source

    @property
    def source_list(self):
        """List of available input sources."""
        return self._client.available_sources()

    @property
    def available(self):
        """Return if device is available."""
        return self._state != STATE_UNKNOWN

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._volume

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._muted

    async def async_turn_off(self):
        """Turn the media player off."""
        await self._client.power_off()

    async def async_turn_on(self):
        """Turn the media player on."""
        await self._client.power_on()

    async def async_volume_up(self):
        """Step volume up in the configured increments."""
        if self.volume_level is None:
            return
        await self._client.set_volume(
            self.internal_vol_to_nad_vol(self.volume_level)
            + self._volume_step * 0.5)

    async def async_volume_down(self):
        """Step volume down in the configured increments."""
        if self.volume_level is None:
            return
        await self._client.set_volume(
            self.internal_vol_to_nad_vol(self.volume_level)
            - self._volume_step * 0.5)

    async def async_set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        await self._client.set_volume(self.internal_vol_to_nad_vol(volume))

    async def async_mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        if mute:
            await self._client.mute()
        else:
            await self._client.unmute()

    async def async_select_source(self, source):
        """Select input source."""
        await self._client.select_source(source)

    async def async_added_to_hass(self):
        """Set up the client and start connecting when Home Assistant is up."""
        @callback
        def state_changed_cb(state):
            async_dispatcher_send(
                self.hass, SIGNAL_NAD_STATE_RECEIVED, state)

        @callback
        def handle_state_changed(state):
            if CMD_POWER in state:
                self._state = STATE_ON if state[CMD_POWER] else STATE_OFF
            else:
                self._state = STATE_UNKNOWN

            if CMD_VOLUME in state:
                self._volume = self.nad_vol_to_internal_vol(state[CMD_VOLUME])
            if CMD_MUTE in state:
                self._muted = state[CMD_MUTE]
            if CMD_SOURCE in state:
                self._source = state[CMD_SOURCE]

            self.async_write_ha_state()

        async def connect(event=None):
            await self._client.connect()

        self._client = NADReceiverTCPC338(
            self._host, self.hass.loop,
            reconnect_interval=self._reconnect_interval,
            state_changed_cb=state_changed_cb)

        self.async_on_remove(async_dispatcher_connect(
            self.hass, SIGNAL_NAD_STATE_RECEIVED, handle_state_changed))

        if self.hass.is_running:
            await connect()
        else:
            self.async_on_remove(self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_START, connect))

    async def async_will_remove_from_hass(self):
        """Disconnect from the amplifier when the entity is removed."""
        if self._client is not None:
            await self._client.disconnect()

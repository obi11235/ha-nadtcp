"""Support for NAD digital amplifiers which can be remote controlled via tcp/ip."""
import logging
import asyncio
import socket
import time

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.media_player import (
    MediaPlayerEntity, PLATFORM_SCHEMA, DEVICE_CLASS_RECEIVER)
from homeassistant.components.media_player.const import (
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_MUTE, SUPPORT_TURN_ON, SUPPORT_TURN_OFF,
    SUPPORT_VOLUME_STEP, SUPPORT_SELECT_SOURCE)
from homeassistant.const import (
    CONF_NAME, STATE_OFF, STATE_ON, STATE_UNKNOWN, STATE_UNAVAILABLE,
    EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP)

from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect, dispatcher_send)

_LOGGER = logging.getLogger(__name__)


CMD_MAIN = "Main"
CMD_BRIGHTNESS = "Main.Brightness"
CMD_BASS_EQ = "Main.Bass"
CMD_CONTROL_STANDBY = "Main.ControlStandby"
CMD_AUTO_STANDBY = "Main.AutoStandby"
CMD_VERSION = "Main.Version"
CMD_MUTE = "Main.Mute"
CMD_POWER = "Main.Power"
CMD_AUTO_SENSE = "Main.AutoSense"
CMD_SOURCE = "Main.Source"
CMD_VOLUME = "Main.Volume"

MSG_ON = 'On'
MSG_OFF = 'Off'

C338_CMDS = {
    'Main':
        {'supported_operators': ['?']
         },
    'Main.AnalogGain':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': range(0, 0),
         'type': int
         },
    'Main.Brightness':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': range(0, 4),
         'type': int
         },
    'Main.Mute':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': [MSG_OFF, MSG_ON],
         'type': bool
         },
    'Main.Power':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': [MSG_OFF, MSG_ON],
         'type': bool
         },
    'Main.Volume':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': range(-80, 0),
         'type': float
         },
    'Main.Bass':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': [MSG_OFF, MSG_ON],
         'type': bool
         },
    'Main.ControlStandby':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': [MSG_OFF, MSG_ON],
         'type': bool
         },
    'Main.AutoStandby':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': [MSG_OFF, MSG_ON],
         'type': bool
         },
    'Main.AutoSense':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': [MSG_OFF, MSG_ON],
         'type': bool
         },
    'Main.Source':
        {'supported_operators': ['+', '-', '=', '?'],
         'values': ["Stream", "Wireless", "TV", "Phono", "Coax1", "Coax2",
                    "Opt1", "Opt2"]
         },
    'Main.Version':
        {'supported_operators': ['?'],
         'type': float
         },
    'Main.Model':
        {'supported_operators': ['?'],
         'values': ['NADC338']
         }
}


class NADReceiverTCPC338(asyncio.Protocol):
    PORT = 30001

    CMD_MIN_INTERVAL = 0.15

    def __init__(self, host, loop, state_changed_cb=None,
                 reconnect_interval=15, connect_timeout=10):
        self._loop = loop
        self._host = host
        self._state_changed_cb = state_changed_cb
        self._reconnect_interval = reconnect_interval
        self._connect_timeout = connect_timeout

        self._transport = None
        self._buffer = ''
        self._last_cmd_time = 0

        self._closing = False
        self._state = {}

    @staticmethod
    def make_command(command, operator, value=None):
        cmd_desc = C338_CMDS[command]
        # validate operator
        if operator in cmd_desc['supported_operators']:
            if operator is '=' and value is None:
                raise ValueError("No value provided")
            elif operator in ['?', '-', '+'] and value is not None:
                raise ValueError(
                    "Operator \'%s\' cannot be called with a value" % operator)

            if value is None:
                cmd = command + operator
            else:
                # validate value
                if 'values' in cmd_desc:
                    if 'type' in cmd_desc and cmd_desc['type'] == bool:
                        value = cmd_desc['values'][int(value)]
                    elif value not in cmd_desc['values']:
                        raise ValueError("Given value \'%s\' is not one of %s"
                                         % (value, cmd_desc['values']))

                cmd = command + operator + str(value)
        else:
            raise ValueError("Invalid operator provided %s" % operator)

        return cmd

    @staticmethod
    def parse_part(response):
        key, value = response.split('=')

        cmd_desc = C338_CMDS[key]

        # convert the data to the correct type
        if 'type' in cmd_desc:
            if cmd_desc['type'] == bool:
                value = bool(cmd_desc['values'].index(value))
            else:
                value = cmd_desc['type'](value)

        return key, value

    def connection_made(self, transport):
        self._transport = transport

        sock = self._transport.get_extra_info('socket')
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 1)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 10)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 3)

        _LOGGER.debug("Connected to %s", self._host)
        self._loop.create_task(self.exec_command('Main', '?'))

    def data_received(self, data):
        data = data.decode('utf-8').replace('\x00', '')

        self._buffer += data

        new_state = {}
        while '\r\n' in self._buffer:
            line, self._buffer = self._buffer.split('\r\n', 1)
            key, value = self.parse_part(line)
            new_state[key] = value

            # volume changes implicitly disables mute,
            if key == 'Main.Volume' and self._state.get('Main.Mute') is True:
                new_state['Main.Mute'] = False

        if new_state:
            _LOGGER.debug("state changed %s", new_state)
            self._state.update(new_state)
            if self._state_changed_cb:
                self._state_changed_cb(self._state)

    def connection_lost(self, exc):
        if exc:
            _LOGGER.error("Disconnected from %s because of %s",
                          self._host, exc)
        else:
            _LOGGER.debug("Disconnected from %s because of close/abort.",
                          self._host)
        self._transport = None

        self._state.clear()
        if self._state_changed_cb:
            self._state_changed_cb(self._state)

        if not self._closing:
            self._loop.create_task(self.connect())

    async def connect(self):
        self._closing = False

        while not self._closing and not self._transport:
            try:
                _LOGGER.debug("Connecting to %s", self._host)
                connection = self._loop.create_connection(
                    lambda: self, self._host, NADReceiverTCPC338.PORT)
                await asyncio.wait_for(
                    connection, timeout=self._connect_timeout)
                return
            except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
                _LOGGER.exception("Error connecting to %s, reconnecting in %ss",
                                  self._host, self._reconnect_interval,
                                  exc_info=True)
                await asyncio.sleep(self._reconnect_interval)

    async def disconnect(self):
        self._closing = True
        if self._transport:
            self._transport.close()

    async def exec_command(self, command, operator, value=None):
        if self._transport:
            # throttle commands to CMD_MIN_INTERVAL
            cmd_wait_time = (self._last_cmd_time
                             + NADReceiverTCPC338.CMD_MIN_INTERVAL) - time.time()
            if cmd_wait_time > 0:
                await asyncio.sleep(cmd_wait_time)
            cmd = self.make_command(command, operator, value)
            self._transport.write(cmd.encode('utf-8'))

            self._last_cmd_time = time.time()

    async def status(self):
        """Return the state of the device."""
        return self._state

    async def power_off(self):
        """Power the device off."""
        await self.exec_command(CMD_POWER, '=', False)

    async def power_on(self):
        """Power the device on."""
        await self.exec_command(CMD_POWER, '=', True)

    async def set_volume(self, volume):
        """Set volume level of the device. Accepts integer values -80-0."""
        await self.exec_command(CMD_VOLUME, '=', float(volume))

    async def volume_down(self):
        await self.exec_command(CMD_VOLUME, '-')

    async def volume_up(self):
        await self.exec_command(CMD_VOLUME, '+')

    async def mute(self):
        """Mute the device."""
        await self.exec_command(CMD_MUTE, '=', True)

    async def unmute(self):
        """Unmute the device."""
        await self.exec_command(CMD_MUTE, '=', False)

    async def select_source(self, source):
        """Select a source from the list of sources."""
        await self.exec_command(CMD_SOURCE, '=', source)

    def available_sources(self):
        """Return a list of available sources."""
        return list(C338_CMDS[CMD_SOURCE]['values'])


SIGNAL_NAD_STATE_RECEIVED = 'nad_state_received'

DEFAULT_RECONNECT_INTERVAL = 10
DEFAULT_NAME = 'NAD amplifier'
DEFAULT_MIN_VOLUME = -80
DEFAULT_MAX_VOLUME = -10
DEFAULT_VOLUME_STEP = 4

SUPPORT_NAD = (
    SUPPORT_VOLUME_SET
    | SUPPORT_VOLUME_MUTE
    | SUPPORT_TURN_ON
    | SUPPORT_TURN_OFF
    | SUPPORT_VOLUME_STEP
    | SUPPORT_SELECT_SOURCE
)

CONF_MIN_VOLUME = 'min_volume'
CONF_MAX_VOLUME = 'max_volume'
CONF_VOLUME_STEP = 'volume_step'
CONF_RECONNECT_INTERVAL = 'reconnect_interval'
CONF_HOST = 'host'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_RECONNECT_INTERVAL, default=DEFAULT_RECONNECT_INTERVAL): int,
    vol.Optional(CONF_MIN_VOLUME, default=DEFAULT_MIN_VOLUME): int,
    vol.Optional(CONF_MAX_VOLUME, default=DEFAULT_MAX_VOLUME): int,
    vol.Optional(CONF_VOLUME_STEP, default=DEFAULT_VOLUME_STEP): int,
})


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the NAD platform."""
    async_add_entities([NADEntity(
        config.get(CONF_NAME),
        config.get(CONF_HOST),
        config.get(CONF_RECONNECT_INTERVAL),
        config.get(CONF_MIN_VOLUME),
        config.get(CONF_MAX_VOLUME),
        config.get(CONF_VOLUME_STEP),
    )])

    return True


class NADEntity(MediaPlayerEntity):
    """Entity handler for the NAD protocol"""

    def __init__(self, name, host, reconnect_interval, min_volume, max_volume, volume_step):
        """Initialize the entity properties"""
        self._client = None
        self._name = name
        self._host = host
        self._reconnect_interval = reconnect_interval
        self._min_vol = min_volume
        self._max_vol = max_volume
        self._volume_step = volume_step

        self._state = STATE_UNKNOWN
        self._muted = None
        self._volume = None
        self._source = None

    def nad_vol_to_internal_vol(self, nad_vol):
        """Convert the configured volume range to internal volume range.
        Takes into account configured min and max volume.
        """
        if nad_vol is None:
            volume_internal = 0.0
        elif nad_vol < self._min_vol:
            volume_internal = 0.0
        elif nad_vol > self._max_vol:
            volume_internal = 1.0
        else:
            volume_internal = (nad_vol - self._min_vol) / \
                              (self._max_vol - self._min_vol)
        return volume_internal

    def internal_vol_to_nad_vol(self, internal_vol):
        return int(round(internal_vol * (self._max_vol - self._min_vol) + self._min_vol))

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def name(self):
        """Return the name of the entity."""
        return self._name

    @property
    def device_class(self):
        """Return the class of this device."""
        return DEVICE_CLASS_RECEIVER

    @property
    def state(self):
        """Return the state of the entity."""
        return self._state

    @property
    def icon(self):
        """Return the icon for the device."""
        return "mdi:speaker-multiple"

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
        return self._state is not STATE_UNKNOWN

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._volume

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._muted

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_NAD

    async def async_turn_off(self):
        """Turn the media player off."""
        await self._client.power_off()

    async def async_turn_on(self):
        """Turn the media player on."""
        await self._client.power_on()

    async def async_volume_up(self):
        """Step volume up in the configured increments."""
        await self._client.set_volume(self.internal_vol_to_nad_vol(self.volume_level) + self._volume_step * 0.5)

    async def async_volume_down(self):
        """Step volume down in the configured increments."""
        await self._client.set_volume(self.internal_vol_to_nad_vol(self.volume_level) - self._volume_step * 0.5)

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
        def state_changed_cb(state):
            dispatcher_send(self.hass, SIGNAL_NAD_STATE_RECEIVED, state)

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

            self.schedule_update_ha_state()

        async def disconnect(event):
            await self._client.disconnect()

        async def connect(event):
            await self._client.connect()
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, disconnect)

        self._client = NADReceiverTCPC338(self._host, self.hass.loop,
                                          reconnect_interval=self._reconnect_interval,
                                          state_changed_cb=state_changed_cb)

        async_dispatcher_connect(
            self.hass, SIGNAL_NAD_STATE_RECEIVED, handle_state_changed)

        if self.hass.is_running:
            await connect(None)
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, connect)

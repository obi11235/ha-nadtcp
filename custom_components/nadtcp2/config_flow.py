"""Config flow for the NAD C338 integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry, ConfigFlow, OptionsFlow)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

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


def _options_schema(options: dict) -> vol.Schema:
    """Build the schema for the tunable options, seeded with current values."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_MIN_VOLUME,
                default=options.get(CONF_MIN_VOLUME, DEFAULT_MIN_VOLUME),
            ): int,
            vol.Optional(
                CONF_MAX_VOLUME,
                default=options.get(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME),
            ): int,
            vol.Optional(
                CONF_VOLUME_STEP,
                default=options.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP),
            ): int,
            vol.Optional(
                CONF_RECONNECT_INTERVAL,
                default=options.get(
                    CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL),
            ): int,
        }
    )


class NadConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the NAD C338 integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle configuration initiated by the user from the UI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_NAME: user_input[CONF_NAME],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_import(self, import_data: dict) -> FlowResult:
        """Import a config entry from a YAML `media_player` platform block."""
        await self.async_set_unique_id(import_data[CONF_HOST])
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=import_data.get(CONF_NAME, DEFAULT_NAME),
            data={
                CONF_HOST: import_data[CONF_HOST],
                CONF_NAME: import_data.get(CONF_NAME, DEFAULT_NAME),
            },
            options={
                CONF_MIN_VOLUME: import_data.get(
                    CONF_MIN_VOLUME, DEFAULT_MIN_VOLUME),
                CONF_MAX_VOLUME: import_data.get(
                    CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME),
                CONF_VOLUME_STEP: import_data.get(
                    CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP),
                CONF_RECONNECT_INTERVAL: import_data.get(
                    CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return NadOptionsFlow()


class NadOptionsFlow(OptionsFlow):
    """Handle the volume/reconnect options for a configured amplifier."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.config_entry.options),
        )

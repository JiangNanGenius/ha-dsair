from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, CONF_SENSORS
from homeassistant.core import callback, HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_FORCE_HEAT_MODE,
    CONF_GW,
    CONF_LINKS,
    CONF_ZHONGHONG_HOST,
    CONF_ZHONGHONG_OUTER_ADDRESS,
    CONF_ZHONGHONG_POLL_INTERVAL,
    CONF_ZHONGHONG_PORT,
    CONF_ZHONGHONG_TEMPERATURE_ENABLED,
    DEFAULT_GW,
    DEFAULT_PORT,
    DEFAULT_ZHONGHONG_HOST,
    DEFAULT_ZHONGHONG_OUTER_ADDRESS,
    DEFAULT_ZHONGHONG_POLL_INTERVAL,
    DEFAULT_ZHONGHONG_PORT,
    GW_LIST,
    DEFAULT_HOST,
)
from .ds_air_service.service import Service
from .hass_inst import GetHass

_LOGGER = logging.getLogger(__name__)


def _log(s: str) -> object:
    s = str(s)
    for i in s.split("\n"):
        _LOGGER.debug(i)


class DsAirFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.host = None
        self.port = None
        self.gw = None
        self.sensor_check = {}
        self.user_input = {}

    async def async_step_user(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors = {}
        if user_input is not None:
            self.user_input.update(user_input)
            if user_input.get(CONF_SENSORS) == False or user_input.get("temp") is not None:
                return self.async_create_entry(
                    title="金制空气", data=self.user_input
                )
            else:
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema({
                        vol.Required("temp", default=True): bool,
                        vol.Required("humidity", default=True): bool,
                        vol.Required("pm25", default=True): bool,
                        vol.Required("co2", default=True): bool,
                        vol.Required("tvoc", default=True): bool,
                        vol.Required("voc", default=False): bool,
                        vol.Required("hcho", default=False): bool,
                    }), errors=errors
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_GW, default=DEFAULT_GW): vol.In(GW_LIST),
                vol.Required(CONF_SCAN_INTERVAL, default=5): int,
                vol.Required(CONF_SENSORS, default=True): bool
            }), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
            config_entry: ConfigEntry,
    ) -> DsAirOptionsFlowHandler:
        """Options callback for DS-AIR."""
        return DsAirOptionsFlowHandler(config_entry)

class DsAirOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options for intergration"""
    
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._config_data = []
        hass: HomeAssistant = GetHass.get_hash()
        self._aircons = list(Service.get_aircons())
        self._climates = [state.alias for state in self._aircons]
        sensors = hass.states.async_all("sensor")
        self._sensors_temp = list(map(lambda state: state.entity_id,
                                 filter(lambda state: state.attributes.get("device_class") == "temperature", sensors)))
        self._sensors_humi = list(map(lambda state: state.entity_id,
                                 filter(lambda state: state.attributes.get("device_class") == "humidity", sensors)))
        self._len = len(self._climates)
        self._cur = -1
        self.host = CONF_HOST
        self.port = CONF_PORT
        self.gw = CONF_GW
        self.sensor_check = CONF_SENSORS
        self.user_input = {}
    
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "adjust_config",
                "bind_return_temperatures",
                "bind_sensors",
                "capability_overrides",
                "zhonghong_temperature_source",
            ],
        ) 

    async def async_step_adjust_config(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:

        errors = {}
        if user_input is not None:
            self.user_input.update(user_input)
            if self.user_input.get('_invaild'):
                self.user_input['_invaild'] = False
                self.hass.config_entries.async_update_entry(self._config_entry, data=self.user_input)
                return self.async_create_entry(
                    title='', data=dict(self._config_entry.options)
                )
        else:
            config_data = self._config_entry.data
            self.user_input['_invaild'] = True
            if config_data.get(CONF_SENSORS, True):
                return self.async_show_form(
                    step_id="adjust_config",
                    data_schema=vol.Schema({
                        vol.Required(CONF_HOST, default=config_data[CONF_HOST]): str,
                        vol.Required(CONF_PORT, default=config_data[CONF_PORT]): int,
                        vol.Required(CONF_GW, default=config_data[CONF_GW]): vol.In(GW_LIST),
                        vol.Required(CONF_SCAN_INTERVAL, default=config_data[CONF_SCAN_INTERVAL]): int,
                        vol.Required(CONF_SENSORS, default=True): bool,
                        vol.Required("temp", default=config_data.get("temp", True)): bool,
                        vol.Required("humidity", default=config_data.get("humidity", True)): bool,
                        vol.Required("pm25", default=config_data.get("pm25", True)): bool,
                        vol.Required("co2", default=config_data.get("co2", True)): bool,
                        vol.Required("tvoc", default=config_data.get("tvoc", True)): bool,
                        vol.Required("voc", default=config_data.get("voc", False)): bool,
                        vol.Required("hcho", default=config_data.get("hcho", False)): bool,
                    }), errors=errors
                )
            else:
                return self.async_show_form(
                    step_id="adjust_config",
                    data_schema=vol.Schema({
                        vol.Required(CONF_HOST, default=config_data[CONF_HOST]): str,
                        vol.Required(CONF_PORT, default=config_data[CONF_PORT]): int,
                        vol.Required(CONF_GW, default=config_data[CONF_GW]): vol.In(GW_LIST),
                        vol.Required(CONF_SCAN_INTERVAL, default=config_data[CONF_SCAN_INTERVAL]): int,
                        vol.Required(CONF_SENSORS, default=False): bool
                    }), errors=errors
                )
    
    async def async_step_bind_sensors(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle bind flow."""
        if self._len == 0:
            return self.async_show_form(step_id="empty", last_step=False)
        if user_input is not None:
            self._config_data.append({
                "climate": user_input.get("climate"),
                "sensor_temp": user_input.get("sensor_temp"),
                "sensor_humi": user_input.get("sensor_humi")
            })
        self._cur = self._cur + 1
        if self._cur > (self._len - 1):
            options = dict(self._config_entry.options)
            options[CONF_LINKS] = self._config_data
            return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="bind_sensors",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "climate",
                        default=self._climates[self._cur]
                    ): vol.In([self._climates[self._cur]]),
                    vol.Optional("sensor_temp"): vol.In(self._sensors_temp),
                    vol.Optional("sensor_humi"): vol.In(self._sensors_humi)
                }
            )
        )

    async def async_step_bind_return_temperatures(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Bind each native Daikin entity to an HA temperature source.

        A climate source is read from its ``current_temperature`` attribute;
        ordinary sensor sources continue to use their entity state.
        """
        if self._len == 0:
            return self.async_show_form(step_id="empty", last_step=False)
        if user_input is not None:
            aircon = self._aircons[self._cur]
            source = user_input.get("temperature_source") or None
            self._config_data.append({
                "climate": aircon.alias,
                "climate_unique_id": aircon.unique_id,
                "sensor_temp": source,
            })
        self._cur += 1
        if self._cur > (self._len - 1):
            old_links = self._config_entry.options.get(CONF_LINKS, [])
            old_by_unique_id = {
                str(item.get("climate_unique_id")): item
                for item in old_links
                if item.get("climate_unique_id") is not None
            }
            old_by_name = {
                item.get("climate"): item
                for item in old_links
                if item.get("climate")
            }
            merged = []
            for item in self._config_data:
                previous = old_by_unique_id.get(str(item["climate_unique_id"])) \
                    or old_by_name.get(item["climate"]) or {}
                if previous.get("sensor_humi"):
                    item["sensor_humi"] = previous["sensor_humi"]
                merged.append(item)
            options = dict(self._config_entry.options)
            options[CONF_LINKS] = merged
            return self.async_create_entry(title="", data=options)

        aircon = self._aircons[self._cur]
        old_links = self._config_entry.options.get(CONF_LINKS, [])
        current = next((
            item.get("sensor_temp", "")
            for item in old_links
            if str(item.get("climate_unique_id")) == str(aircon.unique_id)
            or item.get("climate") == aircon.alias
        ), "") or ""
        field = vol.Optional("temperature_source")
        if current:
            field = vol.Optional("temperature_source", default=current)
        return self.async_show_form(
            step_id="bind_return_temperatures",
            data_schema=vol.Schema({
                vol.Required("climate", default=aircon.alias): vol.In([aircon.alias]),
                field: selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "climate"])
                ),
            }),
        )

    async def async_step_capability_overrides(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure explicit, traceable capability overrides."""
        if user_input is not None:
            options = dict(self._config_entry.options)
            options[CONF_FORCE_HEAT_MODE] = bool(
                user_input.get(CONF_FORCE_HEAT_MODE, False)
            )
            return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="capability_overrides",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_FORCE_HEAT_MODE,
                    default=bool(
                        self._config_entry.options.get(CONF_FORCE_HEAT_MODE, False)
                    ),
                ): bool,
            }),
        )

    async def async_step_zhonghong_temperature_source(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the temperature-only Zhonghong TCP observer."""
        if user_input is not None:
            options = dict(self._config_entry.options)
            options.update({
                CONF_ZHONGHONG_TEMPERATURE_ENABLED: bool(user_input.get(
                    CONF_ZHONGHONG_TEMPERATURE_ENABLED, False
                )),
                CONF_ZHONGHONG_HOST: str(user_input.get(
                    CONF_ZHONGHONG_HOST, DEFAULT_ZHONGHONG_HOST
                )).strip(),
                CONF_ZHONGHONG_PORT: int(user_input.get(
                    CONF_ZHONGHONG_PORT, DEFAULT_ZHONGHONG_PORT
                )),
                CONF_ZHONGHONG_OUTER_ADDRESS: int(user_input.get(
                    CONF_ZHONGHONG_OUTER_ADDRESS,
                    DEFAULT_ZHONGHONG_OUTER_ADDRESS,
                )),
                CONF_ZHONGHONG_POLL_INTERVAL: int(user_input.get(
                    CONF_ZHONGHONG_POLL_INTERVAL,
                    DEFAULT_ZHONGHONG_POLL_INTERVAL,
                )),
            })
            return self.async_create_entry(title="", data=options)
        options = self._config_entry.options
        return self.async_show_form(
            step_id="zhonghong_temperature_source",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_ZHONGHONG_TEMPERATURE_ENABLED,
                    default=bool(options.get(
                        CONF_ZHONGHONG_TEMPERATURE_ENABLED, False
                    )),
                ): bool,
                vol.Required(
                    CONF_ZHONGHONG_HOST,
                    default=options.get(
                        CONF_ZHONGHONG_HOST, DEFAULT_ZHONGHONG_HOST
                    ),
                ): str,
                vol.Required(
                    CONF_ZHONGHONG_PORT,
                    default=int(options.get(
                        CONF_ZHONGHONG_PORT, DEFAULT_ZHONGHONG_PORT
                    )),
                ): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Required(
                    CONF_ZHONGHONG_OUTER_ADDRESS,
                    default=int(options.get(
                        CONF_ZHONGHONG_OUTER_ADDRESS,
                        DEFAULT_ZHONGHONG_OUTER_ADDRESS,
                    )),
                ): vol.All(int, vol.Range(min=0, max=255)),
                vol.Required(
                    CONF_ZHONGHONG_POLL_INTERVAL,
                    default=int(options.get(
                        CONF_ZHONGHONG_POLL_INTERVAL,
                        DEFAULT_ZHONGHONG_POLL_INTERVAL,
                    )),
                ): vol.All(int, vol.Range(min=5, max=300)),
            }),
        )

    async def async_step_empty(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """No AC found."""
        return await self.async_step_init(user_input)

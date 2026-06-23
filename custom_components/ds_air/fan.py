"""Support for Daikin DS-AIR ventilation devices."""
import logging
from typing import Optional

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.const import MAJOR_VERSION, MINOR_VERSION
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .ds_air_service.ctrl_enum import (
    EnumControl,
    get_vent_mode_enum_small_vam,
    get_vent_mode_enum_standard_vam,
    get_vent_mode_name_small_vam,
    get_vent_mode_name_standard_vam,
)
from .ds_air_service.dao import Ventilation, VentilationStatus
from .ds_air_service.display import display
from .ds_air_service.service import Service

_LOGGER = logging.getLogger(__name__)


def _log(s: str):
    s = str(s)
    for i in s.split("\n"):
        _LOGGER.debug(i)


SMALL_VAM_SUPPORT = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
STANDARD_VAM_SUPPORT = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE

if (MAJOR_VERSION, MINOR_VERSION) >= (2024, 8):
    POWER_SUPPORT = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    SMALL_VAM_SUPPORT |= POWER_SUPPORT
    STANDARD_VAM_SUPPORT |= POWER_SUPPORT

_MODE_VENT_NAME_LIST_SMALL_VAM = ["内循环", "热交换", "自动", "防污染", "排异味"]
_MODE_VENT_NAME_LIST_STANDARD_VAM = ["旁通", "热交换", "自动"]


async def async_setup_entry(hass, config_entry, async_add_entities):
    entities = [DsVent(vent) for vent in Service.get_ventilations()]
    async_add_entities(entities)


class DsVent(FanEntity):
    """Representation of a DS-AIR ventilation device."""

    def __init__(self, vent: Ventilation):
        _log("create ventilation:")
        _log(str(vent.__dict__))
        _log(str(vent.status.__dict__))
        self._name = vent.alias
        self._device_info = vent
        self._unique_id = vent.unique_id

        if vent.is_small_vam:
            self._attr_supported_features = SMALL_VAM_SUPPORT
            self._attr_speed_count = len(_MODE_VENT_NAME_LIST_SMALL_VAM) - 1
            self._attr_preset_modes = _MODE_VENT_NAME_LIST_SMALL_VAM
        else:
            self._attr_supported_features = STANDARD_VAM_SUPPORT
            self._attr_speed_count = len(_MODE_VENT_NAME_LIST_STANDARD_VAM)
            self._attr_preset_modes = _MODE_VENT_NAME_LIST_STANDARD_VAM

        Service.register_vent_hook(vent, self._status_change_hook)

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def should_poll(self):
        return False

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": "新风 %s" % self._name,
            "manufacturer": "Daikin Industries, Ltd.",
        }

    @property
    def percentage(self):
        air_flow = self._device_info.status.air_flow
        if air_flow is None:
            return None
        if self._device_info.is_small_vam:
            return min(100, air_flow.value * self.percentage_step)
        if air_flow == EnumControl.AirFlow.WEAK:
            return 50
        if air_flow in (EnumControl.AirFlow.MIDDLE, EnumControl.AirFlow.STRONG):
            return 100
        return None

    def set_percentage(self, percentage: int) -> None:
        new_status = VentilationStatus()
        if percentage <= 0:
            new_status.switch = EnumControl.Switch.OFF
            Service.control_vent(self._device_info, new_status)
            return

        new_status.switch = EnumControl.Switch.ON
        if self._device_info.is_small_vam:
            air_flow_value = max(1, min(4, round(percentage / self.percentage_step)))
            air_flow = EnumControl.AirFlow(air_flow_value)
        elif percentage > 66:
            air_flow = EnumControl.AirFlow.STRONG
        elif percentage > 33:
            air_flow = EnumControl.AirFlow.MIDDLE
        else:
            air_flow = EnumControl.AirFlow.WEAK

        new_status.air_flow = air_flow
        self._device_info.status.switch = new_status.switch
        self._device_info.status.air_flow = air_flow
        Service.control_vent(self._device_info, new_status)
        self.schedule_update_ha_state()

    @property
    def preset_mode(self):
        mode = self._device_info.status.mode
        if mode is None:
            return None
        if self._device_info.is_small_vam:
            return get_vent_mode_name_small_vam(mode)
        return get_vent_mode_name_standard_vam(mode)

    def set_preset_mode(self, preset_mode: str) -> None:
        new_status = VentilationStatus()
        if self._device_info.is_small_vam:
            mode = get_vent_mode_enum_small_vam(preset_mode)
        else:
            mode = get_vent_mode_enum_standard_vam(preset_mode)
        new_status.mode = mode
        self._device_info.status.mode = mode
        Service.control_vent(self._device_info, new_status)
        self.schedule_update_ha_state()

    @property
    def is_on(self):
        switch = self._device_info.status.switch
        if switch is None:
            return None
        return switch == EnumControl.Switch.ON

    def turn_on(self, **kwargs) -> None:
        new_status = VentilationStatus(switch=EnumControl.Switch.ON)
        self._device_info.status.switch = EnumControl.Switch.ON
        Service.control_vent(self._device_info, new_status)
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs) -> None:
        new_status = VentilationStatus(switch=EnumControl.Switch.OFF)
        self._device_info.status.switch = EnumControl.Switch.OFF
        Service.control_vent(self._device_info, new_status)
        self.schedule_update_ha_state()

    def _status_change_hook(self, **kwargs):
        if kwargs.get("vent") is not None:
            vent = kwargs["vent"]
            vent.status = self._device_info.status
            self._device_info = vent
            _log(display(self._device_info))

        if kwargs.get("status") is not None:
            status = self._device_info.status
            new_status = kwargs["status"]
            for attr in (
                "switch",
                "mode",
                "air_flow",
                "in_door_temp",
                "out_door_temp",
                "out_door_humidity",
                "pm25",
            ):
                value = getattr(new_status, attr)
                if value is not None:
                    setattr(status, attr, value)
            _log(display(self._device_info.status))
        self.schedule_update_ha_state()

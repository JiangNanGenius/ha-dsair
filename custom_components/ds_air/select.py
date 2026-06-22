"""Select entities for DS-AIR device-specific controls."""

from typing import Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .ds_air_service.ctrl_enum import EnumControl
from .ds_air_service.dao import AirCon, AirConStatus
from .fan_direction import (
    AXIS_HORIZONTAL,
    AXIS_VERTICAL,
    direction_options,
    direction_supported,
    direction_to_option,
    option_to_direction,
    status_for_axis_direction,
)

_AXIS_NAMES = {
    AXIS_VERTICAL: "垂直风向",
    AXIS_HORIZONTAL: "水平风向",
}

_BREATHE_OPTIONS = {
    "关闭": EnumControl.Breathe.CLOSE,
    "弱": EnumControl.Breathe.WEAK,
    "强": EnumControl.Breathe.STRONG,
}

_STATUS_ATTRS = (
    "switch",
    "mode",
    "humidity",
    "air_flow",
    "fan_direction1",
    "fan_direction2",
    "setted_temp",
    "current_temp",
    "breathe",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up DS-AIR select entities."""
    from .ds_air_service.service import Service

    selects = []
    for aircon in Service.get_aircons():
        for axis in (AXIS_VERTICAL, AXIS_HORIZONTAL):
            if direction_supported(aircon, axis):
                selects.append(DsAirDirectionSelect(aircon, axis))
        if breathe_supported(aircon):
            selects.append(DsAirBreatheSelect(aircon))
    async_add_entities(selects)


class DsAirSelectBase(SelectEntity):
    """Base select entity bound to one DS-AIR air conditioner."""

    def __init__(self, aircon: AirCon):
        self._device_info = aircon
        self._attr_has_entity_name = True

        from .ds_air_service.service import Service

        Service.register_status_hook(aircon, self._status_change_hook)

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    def _status_change_hook(self, **kwargs):
        if kwargs.get("aircon") is not None:
            aircon: AirCon = kwargs["aircon"]
            aircon.status = self._device_info.status
            self._device_info = aircon

        if kwargs.get("status") is not None:
            _apply_status(self._device_info.status, kwargs["status"])
        self.schedule_update_ha_state()

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {(DOMAIN, self._device_info.unique_id)},
            "name": "空调%s" % self._device_info.alias,
            "manufacturer": "Daikin Industries, Ltd.",
        }


class DsAirDirectionSelect(DsAirSelectBase):
    """Direction select for one DS-AIR fan axis."""

    def __init__(self, aircon: AirCon, axis: str):
        super().__init__(aircon)
        self._axis = axis
        self._attr_unique_id = f"{aircon.unique_id}_fan_direction_{axis}"
        self._attr_name = _AXIS_NAMES[axis]
        self._attr_options = direction_options(axis)

    @property
    def available(self):
        """Return whether this fan direction axis exists on the device."""
        return direction_supported(self._device_info, self._axis)

    @property
    def current_option(self) -> Optional[str]:
        """Return the current selected direction."""
        if self._axis == AXIS_VERTICAL:
            direction = self._device_info.status.fan_direction1
        else:
            direction = self._device_info.status.fan_direction2
        return direction_to_option(self._axis, direction)

    def select_option(self, option: str) -> None:
        """Set fan direction for this axis."""
        status = self._device_info.status
        if status.switch != EnumControl.Switch.ON:
            self.schedule_update_ha_state()
            return

        direction = option_to_direction(self._axis, option)
        new_status = status_for_axis_direction(self._device_info, self._axis, direction)
        if new_status is None:
            self.schedule_update_ha_state()
            return

        if new_status.fan_direction1 is not None:
            status.fan_direction1 = new_status.fan_direction1
        if new_status.fan_direction2 is not None:
            status.fan_direction2 = new_status.fan_direction2

        from .ds_air_service.service import Service

        Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()


class DsAirBreatheSelect(DsAirSelectBase):
    """Bathroom breathe select."""

    def __init__(self, aircon: AirCon):
        super().__init__(aircon)
        self._attr_unique_id = f"{aircon.unique_id}_breathe"
        self._attr_name = "换气档位"
        self._attr_options = list(_BREATHE_OPTIONS.keys())

    @property
    def available(self):
        """Return whether bathroom breathe selection is available."""
        return breathe_supported(self._device_info)

    @property
    def current_option(self) -> Optional[str]:
        """Return the current breathe setting."""
        for option, breathe in _BREATHE_OPTIONS.items():
            if breathe == self._device_info.status.breathe:
                return option
        return None

    def select_option(self, option: str) -> None:
        """Set bathroom breathe strength."""
        breathe = _BREATHE_OPTIONS[option]
        status = self._device_info.status
        new_status = AirConStatus(breathe=breathe)
        if status.switch != EnumControl.Switch.ON and breathe != EnumControl.Breathe.CLOSE:
            new_status.switch = EnumControl.Switch.ON
            new_status.mode = EnumControl.Mode.VENTILATION
            status.switch = EnumControl.Switch.ON
            status.mode = EnumControl.Mode.VENTILATION
        status.breathe = breathe

        from .ds_air_service.service import Service

        Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()


def breathe_supported(aircon: AirCon) -> bool:
    return aircon.bath_room


def _apply_status(status: AirConStatus, new_status: AirConStatus) -> None:
    for attr in _STATUS_ATTRS:
        value = getattr(new_status, attr, None)
        if value is not None:
            setattr(status, attr, value)

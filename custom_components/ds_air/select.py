"""Select entities for DS-AIR device-specific controls."""

from typing import Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_FORCE_HEAT_MODE, DOMAIN
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

_WORK_MODE_OPTIONS = {
    "制冷": (EnumControl.Mode.COLD, "cool", "cool_mode"),
    "除湿": (EnumControl.Mode.DRY, "dry", "dry_mode"),
    "送风": (EnumControl.Mode.VENTILATION, "fan_only", "ventilation_mode"),
    "自动": (EnumControl.Mode.AUTO, "auto", "auto_mode"),
    "制热": (EnumControl.Mode.HEAT, "heat", "heat_mode"),
    "自动除湿": (EnumControl.Mode.AUTODRY, "auto_dry", "auto_dry_mode"),
    "清爽": (EnumControl.Mode.RELAX, "comfort", "relax_mode"),
    "睡眠": (EnumControl.Mode.SLEEP, "sleep", "sleep_mode"),
    "预热": (EnumControl.Mode.PREHEAT, "preheat", "pre_heat_mode"),
    "强力除湿": (EnumControl.Mode.MOREDRY, "more_dry", "more_dry_mode"),
}
_WORK_MODE_OPTION_BY_ENUM = {
    mode: option for option, (mode, _key, _capability) in _WORK_MODE_OPTIONS.items()
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
    force_heat_mode = bool(entry.options.get(CONF_FORCE_HEAT_MODE, False))
    for aircon in Service.get_aircons():
        if work_mode_options(aircon, force_heat_mode):
            selects.append(DsAirWorkModeSelect(aircon, force_heat_mode))
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

        from .ds_air_service.service import Service

        Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()


class DsAirWorkModeSelect(DsAirSelectBase):
    """Exact DS-AIR work mode, including model-specific independent modes."""

    def __init__(self, aircon: AirCon, force_heat_mode: bool = False):
        super().__init__(aircon)
        self._force_heat_mode = force_heat_mode
        self._attr_unique_id = f"{aircon.unique_id}_native_work_mode"
        # HA 2026.7 does not consume ``_attr_suggested_object_id`` here.  Set a
        # deterministic entity id before first registration so Node-RED can
        # address the exact native mode without depending on Chinese slugging.
        self.entity_id = f"select.ds_air_{aircon.room_id}_{aircon.unit_id}_native_work_mode"
        # This is the indoor unit's real Daikin work mode, not a preset or a
        # diagnostic-only raw value.  Keep the stable entity id for existing
        # Node-RED consumers, while presenting the concise user-facing name.
        self._attr_name = "工作模式"
        self._attr_icon = "mdi:hvac"
        self._attr_options = work_mode_options(aircon, force_heat_mode)

    @property
    def available(self):
        """Return whether at least one native mode capability is known."""
        return bool(work_mode_options(self._device_info, self._force_heat_mode))

    @property
    def current_option(self) -> Optional[str]:
        """Return the exact physical mode reported by the Daikin gateway."""
        return _WORK_MODE_OPTION_BY_ENUM.get(self._device_info.status.mode)

    @property
    def extra_state_attributes(self):
        """Expose stable raw evidence for Node-RED and diagnostics."""
        mode = self._device_info.status.mode
        item = _WORK_MODE_OPTIONS.get(self.current_option or "")
        return {
            "ds_air_native_mode": item[1] if item else None,
            "ds_air_native_mode_code": None if mode is None else int(mode.value),
            "ds_air_room_id": self._device_info.room_id,
            "ds_air_unit_id": self._device_info.unit_id,
            "ds_air_evidence": "gateway_status" if mode is not None else "unknown",
        }

    def select_option(self, option: str) -> None:
        """Send an exact native mode and wait for gateway status confirmation."""
        if option not in self._attr_options:
            self.schedule_update_ha_state()
            return
        mode = _WORK_MODE_OPTIONS[option][0]
        status = self._device_info.status
        if status.switch == EnumControl.Switch.ON and status.mode == mode:
            self.schedule_update_ha_state()
            return
        new_status = AirConStatus(mode=mode)
        if status.switch != EnumControl.Switch.ON:
            new_status.switch = EnumControl.Switch.ON

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

        from .ds_air_service.service import Service

        Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()


def breathe_supported(aircon: AirCon) -> bool:
    return aircon.bath_room


def work_mode_options(aircon: AirCon, force_heat_mode: bool = False) -> list[str]:
    """Build an exact per-device mode list from the native capability bits."""
    return [
        option
        for option, (_mode, _key, capability) in _WORK_MODE_OPTIONS.items()
        if bool(getattr(aircon, capability, False))
        or (option == "制热" and force_heat_mode)
    ]


def _apply_status(status: AirConStatus, new_status: AirConStatus) -> None:
    for attr in _STATUS_ATTRS:
        value = getattr(new_status, attr, None)
        if value is not None:
            setattr(status, attr, value)

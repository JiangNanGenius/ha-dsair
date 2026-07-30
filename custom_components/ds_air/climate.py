"""
Daikin platform that offers climate devices.

For more details about this platform, please refer to the documentation
https://home-assistant.io/components/demo/
"""

import logging
import math
import time
from threading import Timer
from typing import Optional, List
from uuid import uuid4

import voluptuous as vol
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate import PLATFORM_SCHEMA
""" from homeassistant.components.climate.const import (
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_FAN_MODE,
    SUPPORT_SWING_MODE,
    SUPPORT_TARGET_HUMIDITY,
    HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL, HVAC_MODE_HEAT_COOL, HVAC_MODE_AUTO,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH) """
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode, HVACAction,
    FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_FORCE_HEAT_MODE, CONF_LINKS, DOMAIN
from .ds_air_service.ctrl_enum import EnumControl, EnumFanVolume
from .ds_air_service.dao import AirCon, AirConStatus
from .ds_air_service.display import display
from .fan_direction import (
    AXIS_HORIZONTAL,
    AXIS_VERTICAL,
    direction_supported,
    primary_direction,
    status_for_axis_direction,
)

_SUPPORT_FLAGS = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)
FAN_LEVELS = ["1", "2", "3", "4", "5"]
FAN_QUIET = "quiet"
_FAN_BY_CAPABILITY = {
    EnumFanVolume.STEP_2: [FAN_LOW, FAN_HIGH],
    EnumFanVolume.STEP_3: ["1", "3", "5"],
    EnumFanVolume.STEP_4: ["1", "2", "4", "5"],
    EnumFanVolume.STEP_5: FAN_LEVELS,
    EnumFanVolume.STEPLESS: FAN_LEVELS,
}

_NATIVE_MODE_INFO = {
    EnumControl.Mode.COLD: ("cool", "制冷"),
    EnumControl.Mode.DRY: ("dry", "除湿"),
    EnumControl.Mode.VENTILATION: ("fan_only", "送风"),
    EnumControl.Mode.AUTO: ("auto", "自动"),
    EnumControl.Mode.HEAT: ("heat", "制热"),
    EnumControl.Mode.AUTODRY: ("auto_dry", "自动除湿"),
    EnumControl.Mode.RELAX: ("comfort", "清爽"),
    EnumControl.Mode.SLEEP: ("sleep", "睡眠"),
    EnumControl.Mode.PREHEAT: ("preheat", "预热"),
    EnumControl.Mode.MOREDRY: ("more_dry", "强力除湿"),
}

_NATIVE_MODE_CAPABILITIES = (
    (EnumControl.Mode.COLD, "cool_mode"),
    (EnumControl.Mode.DRY, "dry_mode"),
    (EnumControl.Mode.VENTILATION, "ventilation_mode"),
    (EnumControl.Mode.AUTO, "auto_mode"),
    (EnumControl.Mode.HEAT, "heat_mode"),
    (EnumControl.Mode.AUTODRY, "auto_dry_mode"),
    (EnumControl.Mode.RELAX, "relax_mode"),
    (EnumControl.Mode.SLEEP, "sleep_mode"),
    (EnumControl.Mode.PREHEAT, "pre_heat_mode"),
    (EnumControl.Mode.MOREDRY, "more_dry_mode"),
)

# The official 大金空气 UI disables manual fan control in these independent
# work modes.  清爽/comfort deliberately remains controllable.
_FAN_CONTROL_DISABLED_MODES = {
    EnumControl.Mode.DRY,
    EnumControl.Mode.AUTODRY,
    EnumControl.Mode.SLEEP,
    EnumControl.Mode.PREHEAT,
    EnumControl.Mode.MOREDRY,
}

_COMPAT_HVAC_MODE = {
    EnumControl.Mode.COLD: HVACMode.COOL,
    EnumControl.Mode.DRY: HVACMode.DRY,
    EnumControl.Mode.VENTILATION: HVACMode.FAN_ONLY,
    EnumControl.Mode.AUTO: HVACMode.AUTO,
    EnumControl.Mode.HEAT: HVACMode.HEAT,
    EnumControl.Mode.AUTODRY: HVACMode.DRY,
    EnumControl.Mode.RELAX: HVACMode.COOL,
    EnumControl.Mode.PREHEAT: HVACMode.HEAT,
    EnumControl.Mode.MOREDRY: HVACMode.DRY,
}

_NATIVE_MODE_FAMILY = {
    EnumControl.Mode.COLD: "cool",
    EnumControl.Mode.DRY: "dry",
    EnumControl.Mode.VENTILATION: "fan_only",
    EnumControl.Mode.AUTO: "auto",
    EnumControl.Mode.HEAT: "heat",
    EnumControl.Mode.AUTODRY: "dry",
    EnumControl.Mode.RELAX: "cool",
    EnumControl.Mode.SLEEP: "sleep",
    EnumControl.Mode.PREHEAT: "heat",
    EnumControl.Mode.MOREDRY: "dry",
}

_PRESET_MODE_BY_ENUM = {
    EnumControl.Mode.AUTODRY: "自动除湿",
    EnumControl.Mode.RELAX: "清爽",
    EnumControl.Mode.SLEEP: "睡眠",
    EnumControl.Mode.PREHEAT: "预热",
    EnumControl.Mode.MOREDRY: "强力除湿",
}
_PRESET_ENUM_BY_MODE = {label: mode for mode, label in _PRESET_MODE_BY_ENUM.items()}


def _sleep_hvac_mode(aircon: AirCon) -> Optional[HVACMode]:
    """Project independent sleep conservatively without live run evidence.

    ``out_door_run_cond`` arrives in the capability response and currently has
    no independent freshness coordinate.  It therefore cannot safely choose a
    current cooling/heating projection.  The exact select remains ``sleep``.
    """
    return HVACMode.AUTO

_LEGACY_FAN_TO_AIR_FLOW = {
    FAN_LOW: EnumControl.AirFlow.SUPER_WEAK,
    "稍弱": EnumControl.AirFlow.WEAK,
    FAN_MEDIUM: EnumControl.AirFlow.MIDDLE,
    "稍强": EnumControl.AirFlow.STRONG,
    FAN_HIGH: EnumControl.AirFlow.SUPER_STRONG,
    FAN_AUTO: EnumControl.AirFlow.AUTO,
    FAN_QUIET: EnumControl.AirFlow.MUTE,
    "静音": EnumControl.AirFlow.MUTE,
}
_CLIMATE_SWING_OPTIONS = {
    '➡️': EnumControl.FanDirection.P0,
    '↘️': EnumControl.FanDirection.P1,
    '⬇️': EnumControl.FanDirection.P2,
    '↙️': EnumControl.FanDirection.P3,
    '⬅️': EnumControl.FanDirection.P4,
    '自动': EnumControl.FanDirection.AUTO,
}
_CLIMATE_SWING_NAMES = {v: k for k, v in _CLIMATE_SWING_OPTIONS.items()}
_FAN_VERIFY_DELAYS_SECONDS = (1.0, 3.0, 8.0, 15.0, 25.0)
_TARGET_VERIFY_DELAYS_SECONDS = (1.0, 3.0, 8.0, 15.0, 25.0)
_ZHONGHONG_TEMPERATURE_TTL_MS = 120 * 1000

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT): cv.port
})

_LOGGER = logging.getLogger(__name__)

def _log(s: str):
    s = str(s)
    for i in s.split("\n"):
        _LOGGER.debug(i)


def native_mode_key(mode: Optional[EnumControl.Mode]) -> Optional[str]:
    """Return the exact DS-AIR work-mode key without collapsing it."""
    item = _NATIVE_MODE_INFO.get(mode)
    return item[0] if item else None


def native_mode_label(mode: Optional[EnumControl.Mode]) -> Optional[str]:
    """Return the human-readable exact DS-AIR work-mode label."""
    item = _NATIVE_MODE_INFO.get(mode)
    return item[1] if item else None


def native_mode_family(mode: Optional[EnumControl.Mode]) -> Optional[str]:
    """Return a mode family, never a claim about current compressor action."""
    return _NATIVE_MODE_FAMILY.get(mode)


def native_supported_mode_keys(
        aircon: AirCon, force_heat_mode: bool = False
) -> List[str]:
    """Return exact work modes reported by this indoor unit's capability bits."""
    return [
        _NATIVE_MODE_INFO[mode][0]
        for mode, capability in _NATIVE_MODE_CAPABILITIES
        if bool(getattr(aircon, capability, False))
        or (mode == EnumControl.Mode.HEAT and force_heat_mode)
    ]


def _temperature_value_from_state(state):
    """Read temperature from a sensor state or HA climate attribute."""
    if state is None:
        return None
    entity_id = getattr(state, "entity_id", "") or ""
    if entity_id.startswith("climate."):
        return getattr(state, "attributes", {}).get("current_temperature")
    return getattr(state, "state", None)


def _humidity_value_from_state(state):
    """Read humidity from a sensor state or HA climate attribute."""
    if state is None:
        return None
    entity_id = getattr(state, "entity_id", "") or ""
    if entity_id.startswith("climate."):
        return getattr(state, "attributes", {}).get("current_humidity")
    return getattr(state, "state", None)


def fan_profile_name(aircon: AirCon) -> str:
    """Describe the native fan capability without inferring extra levels."""
    if aircon.fan_volume == EnumFanVolume.STEP_2:
        return "two_speed"
    if aircon.fan_volume == EnumFanVolume.STEP_3:
        return "three_speed"
    if aircon.fan_volume == EnumFanVolume.STEP_4:
        return "four_speed"
    if aircon.fan_volume in (EnumFanVolume.STEP_5, EnumFanVolume.STEPLESS):
        return "five_speed"
    return "unknown"


def fan_mode_name(aircon: AirCon, air_flow: Optional[EnumControl.AirFlow]) -> Optional[str]:
    """Project a physical airflow into the device-specific HA fan vocabulary."""
    if air_flow is None:
        return None
    if air_flow == EnumControl.AirFlow.AUTO:
        return FAN_AUTO if aircon.fan_volume_auto and aircon.fan_volume != EnumFanVolume.STEP_2 else None
    if air_flow == EnumControl.AirFlow.MUTE:
        return FAN_QUIET if aircon.fan_volume_mute and aircon.fan_volume != EnumFanVolume.STEP_2 else None
    raw = int(air_flow.value)
    if aircon.fan_volume == EnumFanVolume.STEP_2:
        return {
            int(EnumControl.AirFlow.SUPER_WEAK): FAN_LOW,
            int(EnumControl.AirFlow.SUPER_STRONG): FAN_HIGH,
        }.get(raw)
    name = str(raw + 1) if 0 <= raw <= 4 else None
    supported = _FAN_BY_CAPABILITY.get(aircon.fan_volume)
    return name if supported is not None and name in supported else None


def fan_mode_enum(aircon: AirCon, fan_mode: str) -> Optional[EnumControl.AirFlow]:
    """Resolve a requested fan option while preserving legacy aliases during migration."""
    name = str(fan_mode).strip()
    if aircon.fan_volume == EnumFanVolume.STEP_2:
        return {
            FAN_LOW: EnumControl.AirFlow.SUPER_WEAK,
            FAN_HIGH: EnumControl.AirFlow.SUPER_STRONG,
        }.get(name)
    requested = None
    if name in FAN_LEVELS:
        requested = EnumControl.AirFlow(int(name) - 1)
    elif name == FAN_AUTO and aircon.fan_volume_auto:
        requested = EnumControl.AirFlow.AUTO
    elif name in (FAN_QUIET, "静音") and aircon.fan_volume_mute:
        requested = EnumControl.AirFlow.MUTE
    else:
        requested = _LEGACY_FAN_TO_AIR_FLOW.get(name)
    if requested is None:
        return None
    projected = fan_mode_name(aircon, requested)
    return requested if projected in (_FAN_BY_CAPABILITY.get(aircon.fan_volume) or []) \
        or projected in (FAN_AUTO, FAN_QUIET) else None

async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the climate devices."""

    from .ds_air_service.service import Service
    climates = []
    force_heat_mode = bool(entry.options.get(CONF_FORCE_HEAT_MODE, False))
    for aircon in Service.get_aircons():
        climates.append(DsAir(aircon, force_heat_mode=force_heat_mode))
    async_add_entities(climates)
    link = entry.options.get(CONF_LINKS)
    sensor_temp_map: dict[str, list[DsAir]] = {}
    sensor_humi_map: dict[str, list[DsAir]] = {}
    if link is not None:
        for i in link:
            climate_unique_id = i.get("climate_unique_id")
            climate_name = i.get("climate")
            climate = next((
                c for c in climates
                if climate_unique_id is not None
                and str(c.unique_id) == str(climate_unique_id)
            ), None)
            if climate is None:
                climate = next((c for c in climates if c.name == climate_name), None)
            if climate is not None:
                if temp_entity_id := i.get("sensor_temp"):
                    sensor_temp_map.setdefault(temp_entity_id, []).append(climate)
                    climate.linked_temp_entity_id = temp_entity_id
                if humi_entity_id := i.get("sensor_humi"):
                    sensor_humi_map.setdefault(humi_entity_id, []).append(climate)
                    climate.linked_humi_entity_id = humi_entity_id

    zhonghong_listener_removers = []
    observer = hass.data[DOMAIN].get("zhonghong_temperature_observer")
    if observer is not None:
        for climate in climates:
            aircon = climate._device_info
            try:
                room_id = int(aircon.room_id)
                unit_id = int(aircon.unit_id)
            except (TypeError, ValueError):
                continue
            if room_id <= 0 or unit_id != 0:
                continue
            indoor_address = room_id - 1

            def observe(observation, target=climate, indoor=indoor_address):
                if observation.outer_address != observer.outer_address \
                        or observation.indoor_address != indoor:
                    return
                if not observation.online or observation.temperature_c is None:
                    return
                target.update_zhonghong_temperature(
                    observation.temperature_c,
                    observer.source_for(observation),
                    observation.observed_at_ms,
                )

            zhonghong_listener_removers.append(
                observer.register_listener(observe)
            )
            latest = observer.latest(observer.outer_address, indoor_address)
            if latest is not None:
                observe(latest)
    hass.data[DOMAIN]["zhonghong_temperature_listeners"] = \
        zhonghong_listener_removers

    async def listener(event: Event):
        sensor_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        if sensor_id in sensor_temp_map:
            for climate in sensor_temp_map[sensor_id]:
                climate.update_cur_temp(_temperature_value_from_state(new_state))
        if sensor_id in sensor_humi_map:
            for climate in sensor_humi_map[sensor_id]:
                climate.update_cur_humi(_humidity_value_from_state(new_state))

    remove_listener = async_track_state_change_event(hass, list(sensor_temp_map.keys()) + list(sensor_humi_map.keys()), listener)
    hass.data[DOMAIN]["listener"] = remove_listener


class DsAir(ClimateEntity):
    """Representation of a Daikin climate device."""

    def __init__(self, aircon: AirCon, force_heat_mode: bool = False):
        _log('create aircon:')
        _log(str(aircon.__dict__))
        _log(str(aircon.status.__dict__))
        """Initialize the climate device."""
        self._name = aircon.alias
        self._device_info = aircon
        self._unique_id = aircon.unique_id
        self._force_heat_mode = force_heat_mode
        self.linked_temp_entity_id: str | None = None
        self.linked_humi_entity_id: str | None = None
        self._link_cur_temp = False
        self._link_cur_humi = False
        self._cur_temp = None
        self._cur_humi = None
        self._linked_temp_observed_at_ms = 0
        self._linked_humi_observed_at_ms = 0
        self._zhonghong_temp_valid = False
        self._zhonghong_temp = None
        self._zhonghong_temp_source: str | None = None
        self._zhonghong_temp_observed_at_ms = 0
        # Power and exact mode use separate physical coordinates.  A partial
        # gateway status frame may update only one field; keeping independent
        # generations prevents a fresh mode report from making an old power
        # value look fresh (or vice versa).
        self._status_physical_epoch = uuid4().hex
        startup_observed_at_ms = int(time.time() * 1000)
        self._power_physical_generation = (
            1 if aircon.status.switch is not None else 0
        )
        self._power_physical_observed_at_ms = (
            startup_observed_at_ms if aircon.status.switch is not None else 0
        )
        self._power_physical_source = (
            "startup_gateway_discovery"
            if aircon.status.switch is not None else "unknown"
        )
        self._mode_physical_generation = (
            1 if aircon.status.mode is not None else 0
        )
        self._mode_physical_observed_at_ms = (
            startup_observed_at_ms if aircon.status.mode is not None else 0
        )
        self._mode_physical_source = (
            "startup_gateway_discovery"
            if aircon.status.mode is not None else "unknown"
        )
        # Fan commands must be confirmed by a gateway STATUS_CHANGED or
        # QUERY_STATUS packet.  These coordinates never advance on a local HA
        # service call, so Node-RED can distinguish physical proof from an
        # optimistic entity echo.
        self._fan_physical_generation = 1 if aircon.status.air_flow is not None else 0
        # Generation is process-local and restarts from one after an integration
        # reload.  Pair it with a fresh entity epoch so downstream controllers
        # never compare a new runtime with a persisted generation from the old
        # runtime.
        self._fan_physical_epoch = uuid4().hex
        self._fan_physical_observed_at_ms = (
            int(time.time() * 1000) if aircon.status.air_flow is not None else 0
        )
        self._fan_physical_source = (
            "startup_gateway_discovery" if aircon.status.air_flow is not None else "unknown"
        )
        self._target_physical_epoch = uuid4().hex
        self._target_physical_generation = (
            1 if aircon.status.setted_temp is not None else 0
        )
        self._target_physical_observed_at_ms = (
            startup_observed_at_ms if aircon.status.setted_temp is not None else 0
        )
        self._target_physical_source = (
            "startup_gateway_discovery"
            if aircon.status.setted_temp is not None else "unknown"
        )
        self._fan_verify_epoch = 0
        self._fan_verify_timers = []
        self._target_verify_epoch = 0
        self._target_verify_timers = []
        from .ds_air_service.service import Service
        Service.register_status_hook(aircon, self._status_change_hook)

    async def async_added_to_hass(self) -> None:
        if self.linked_temp_entity_id:
            if state := self.hass.states.get(self.linked_temp_entity_id):
                self.update_cur_temp(_temperature_value_from_state(state))
        if self.linked_humi_entity_id:
            if state := self.hass.states.get(self.linked_humi_entity_id):
                self.update_cur_humi(_humidity_value_from_state(state))

    def _status_change_hook(self, **kwargs):
        _log('hook:')
        if kwargs.get('aircon') is not None:
            aircon: AirCon = kwargs['aircon']
            aircon.status = self._device_info.status
            self._device_info = aircon
            _log(display(self._device_info))

        if kwargs.get('status') is not None:
            status: AirConStatus = self._device_info.status
            new_status: AirConStatus = kwargs['status']
            if new_status.mode is not None:
                status.mode = new_status.mode
                self._mode_physical_generation += 1
                self._mode_physical_observed_at_ms = int(time.time() * 1000)
                self._mode_physical_source = "gateway_status"
            if new_status.switch is not None:
                status.switch = new_status.switch
                self._power_physical_generation += 1
                self._power_physical_observed_at_ms = int(time.time() * 1000)
                self._power_physical_source = "gateway_status"
            if new_status.humidity is not None:
                status.humidity = new_status.humidity
            if new_status.air_flow is not None:
                status.air_flow = new_status.air_flow
                self._fan_physical_generation += 1
                self._fan_physical_observed_at_ms = int(time.time() * 1000)
                self._fan_physical_source = "gateway_status"
            if new_status.fan_direction1 is not None:
                status.fan_direction1 = new_status.fan_direction1
            if new_status.fan_direction2 is not None:
                status.fan_direction2 = new_status.fan_direction2
            if new_status.setted_temp is not None:
                status.setted_temp = new_status.setted_temp
                self._target_physical_generation += 1
                self._target_physical_observed_at_ms = int(time.time() * 1000)
                self._target_physical_source = "gateway_status"
            if new_status.current_temp is not None:
                status.current_temp = new_status.current_temp
            if new_status.breathe is not None:
                status.breathe = new_status.breathe
            _log(display(self._device_info.status))
        self.schedule_update_ha_state()

    @property
    def extra_state_attributes(self):
        """Expose exact native mode/capability and gateway-backed fan evidence."""
        mode = self._device_info.status.mode
        temp_valid, _temp_value, temp_source, temp_observed_ms, temp_role = \
            self._selected_temperature_evidence()
        return {
            "ds_air_native_mode": native_mode_key(mode),
            "ds_air_native_mode_label": native_mode_label(mode),
            "ds_air_native_mode_code": None if mode is None else int(mode.value),
            "ds_air_mode_family": native_mode_family(mode),
            "ds_air_native_supported_modes": native_supported_mode_keys(
                self._device_info, getattr(self, "_force_heat_mode", False)
            ),
            "ds_air_gateway_heat_capability": bool(self._device_info.heat_mode),
            "ds_air_effective_heat_capability": bool(
                self._device_info.heat_mode
                or getattr(self, "_force_heat_mode", False)
            ),
            "ds_air_heat_capability_source": (
                "gateway" if self._device_info.heat_mode
                else "configured_override"
                if getattr(self, "_force_heat_mode", False)
                else "gateway"
            ),
            "ds_air_status_physical_epoch": self._status_physical_epoch,
            "ds_air_power_physical_generation": self._power_physical_generation,
            "ds_air_power_physical_observed_at_ms": self._power_physical_observed_at_ms,
            "ds_air_power_physical_source": self._power_physical_source,
            "ds_air_power_physical_value": (
                None if self._device_info.status.switch is None
                else "on" if self._device_info.status.switch == EnumControl.Switch.ON
                else "off"
            ),
            "ds_air_mode_physical_generation": self._mode_physical_generation,
            "ds_air_mode_physical_observed_at_ms": self._mode_physical_observed_at_ms,
            "ds_air_mode_physical_source": self._mode_physical_source,
            "ds_air_mode_physical_key": native_mode_key(mode),
            "ds_air_mode_physical_code": None if mode is None else int(mode.value),
            "ds_air_fan_profile": fan_profile_name(self._device_info),
            "ds_air_fan_raw_code": None if self._device_info.status.air_flow is None
            else int(self._device_info.status.air_flow.value),
            "ds_air_fan_physical_epoch": self._fan_physical_epoch,
            "ds_air_fan_physical_generation": self._fan_physical_generation,
            "ds_air_fan_physical_observed_at_ms": self._fan_physical_observed_at_ms,
            "ds_air_fan_physical_source": self._fan_physical_source,
            "ds_air_fan_physical_mode": self.fan_mode,
            "ds_air_fan_verify_delays_s": list(_FAN_VERIFY_DELAYS_SECONDS),
            "ds_air_target_physical_epoch": self._target_physical_epoch,
            "ds_air_target_physical_generation": self._target_physical_generation,
            "ds_air_target_physical_observed_at_ms": self._target_physical_observed_at_ms,
            "ds_air_target_physical_source": self._target_physical_source,
            "ds_air_target_physical_value": self.target_temperature,
            "ds_air_target_verify_delays_s": list(_TARGET_VERIFY_DELAYS_SECONDS),
            "ds_air_external_temperature_entity_id": self.linked_temp_entity_id,
            "ds_air_current_temperature_source": temp_source,
            "ds_air_current_temperature_source_role": temp_role,
            "ds_air_current_temperature_observed_at_ms": temp_observed_ms,
            "ds_air_current_temperature_valid": temp_valid,
            "ds_air_zhonghong_temperature_source": getattr(
                self, "_zhonghong_temp_source", None
            ),
            "ds_air_zhonghong_temperature_observed_at_ms": getattr(
                self, "_zhonghong_temp_observed_at_ms", 0
            ),
            "ds_air_zhonghong_temperature_valid": self._zhonghong_temperature_valid(),
            "ds_air_external_humidity_entity_id": self.linked_humi_entity_id,
            "ds_air_current_humidity_source": (
                self.linked_humi_entity_id if self._link_cur_humi else None
            ),
            "ds_air_current_humidity_observed_at_ms": self._linked_humi_observed_at_ms,
            "ds_air_current_humidity_valid": self._link_cur_humi,
        }

    def _cancel_fan_verify_timers(self):
        self._fan_verify_epoch += 1
        for timer in self._fan_verify_timers:
            try:
                timer.cancel()
            except Exception:
                pass
        self._fan_verify_timers = []

    def _query_fan_status(self, verify_epoch):
        """Issue one targeted authoritative status query for this indoor unit."""
        if verify_epoch != self._fan_verify_epoch:
            return
        try:
            from .ds_air_service.dao import get_device_by_aircon
            from .ds_air_service.param import AirConQueryStatusParam
            from .ds_air_service.service import Service
            if not Service.is_ready():
                return
            query = AirConQueryStatusParam()
            query.target = get_device_by_aircon(self._device_info)
            query.device = self._device_info
            Service.send_msg(query)
        except Exception as exc:
            _LOGGER.warning("fan verification query failed for %s: %s", self._unique_id, exc)

    def _schedule_fan_verification_queries(self):
        """Query at short/medium horizons without slowing the command path."""
        self._cancel_fan_verify_timers()
        verify_epoch = self._fan_verify_epoch
        for delay in _FAN_VERIFY_DELAYS_SECONDS:
            timer = Timer(delay, self._query_fan_status, args=(verify_epoch,))
            timer.daemon = True
            self._fan_verify_timers.append(timer)
            timer.start()

    def _cancel_target_verify_timers(self):
        self._target_verify_epoch += 1
        for timer in self._target_verify_timers:
            try:
                timer.cancel()
            except Exception:
                pass
        self._target_verify_timers = []

    def _query_target_status(self, verify_epoch):
        """Issue one targeted authoritative status query for target temperature."""
        if verify_epoch != self._target_verify_epoch:
            return
        try:
            from .ds_air_service.dao import get_device_by_aircon
            from .ds_air_service.param import AirConQueryStatusParam
            from .ds_air_service.service import Service
            if not Service.is_ready():
                return
            query = AirConQueryStatusParam()
            query.target = get_device_by_aircon(self._device_info)
            query.device = self._device_info
            Service.send_msg(query)
        except Exception as exc:
            _LOGGER.warning(
                "target-temperature verification query failed for %s: %s",
                self._unique_id,
                exc,
            )

    def _schedule_target_verification_queries(self):
        """Query at short/medium horizons without creating an optimistic echo."""
        self._cancel_target_verify_timers()
        verify_epoch = self._target_verify_epoch
        for delay in _TARGET_VERIFY_DELAYS_SECONDS:
            timer = Timer(delay, self._query_target_status, args=(verify_epoch,))
            timer.daemon = True
            self._target_verify_timers.append(timer)
            timer.start()

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_fan_verify_timers()
        self._cancel_target_verify_timers()
        await super().async_will_remove_from_hass()

    def update_cur_temp(self, value):
        try:
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError("non-finite external temperature")
        except (TypeError, ValueError):
            self._link_cur_temp = False
            self._cur_temp = None
            self._linked_temp_observed_at_ms = 0
        else:
            self._link_cur_temp = True
            self._cur_temp = parsed
            self._linked_temp_observed_at_ms = int(time.time() * 1000)
        self.schedule_update_ha_state()

    def update_cur_humi(self, value):
        try:
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError("non-finite external humidity")
        except (TypeError, ValueError):
            self._link_cur_humi = False
            self._cur_humi = None
            self._linked_humi_observed_at_ms = 0
        else:
            self._link_cur_humi = True
            self._cur_humi = int(parsed)
            self._linked_humi_observed_at_ms = int(time.time() * 1000)
        self.schedule_update_ha_state()

    def _zhonghong_temperature_valid(self) -> bool:
        if not getattr(self, "_zhonghong_temp_valid", False):
            return False
        observed_ms = int(getattr(self, "_zhonghong_temp_observed_at_ms", 0) or 0)
        now = int(time.time() * 1000)
        return observed_ms > 0 and observed_ms <= now + 60 * 1000 \
            and now - observed_ms <= _ZHONGHONG_TEMPERATURE_TTL_MS

    def _selected_temperature_evidence(self):
        if self._link_cur_temp:
            return (
                True,
                self._cur_temp,
                self.linked_temp_entity_id,
                self._linked_temp_observed_at_ms,
                "linked_ha_entity",
            )
        if self._zhonghong_temperature_valid():
            return (
                True,
                getattr(self, "_zhonghong_temp", None),
                getattr(self, "_zhonghong_temp_source", None),
                getattr(self, "_zhonghong_temp_observed_at_ms", 0),
                "zhonghong_temperature_only",
            )
        return False, None, None, 0, "unavailable"

    def update_zhonghong_temperature(
            self, value, source: str, observed_at_ms: int
    ) -> None:
        """Accept one checksum-verified, temperature-only Zhonghong sample."""
        try:
            parsed = float(value)
            observed = int(observed_at_ms)
            if not math.isfinite(parsed) or not -20 <= parsed <= 80:
                raise ValueError("temperature out of range")
            if observed <= 0:
                raise ValueError("invalid observation timestamp")
        except (TypeError, ValueError):
            return
        self._zhonghong_temp_valid = True
        self._zhonghong_temp = parsed
        self._zhonghong_temp_source = str(source)
        self._zhonghong_temp_observed_at_ms = observed
        self.schedule_update_ha_state()

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def target_humidity(self):
        """Do not expose the native 0-3 level enum as relative humidity."""
        return None

    @property
    def hvac_action(self):
        """Return only action states backed by actual run evidence."""
        status = self._device_info.status
        if status.switch == EnumControl.Switch.OFF:
            return HVACAction.OFF
        # The gateway currently reports requested work mode, not compressor,
        # coil, refrigerant or thermostat-call state.  Reporting COOLING or
        # HEATING here would turn a compatibility projection into fake runtime
        # evidence, so fail closed until a proven operating-state field exists.
        return None

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return hvac operation ie. heat, cool mode.

        Need to be one of HVAC_MODE_*.
        """
        status = self._device_info.status
        if status.switch == EnumControl.Switch.OFF:
            return HVACMode.OFF
        if status.switch is None or status.mode is None:
            return None
        if status.mode == EnumControl.Mode.SLEEP:
            return _sleep_hvac_mode(self._device_info)
        return _COMPAT_HVAC_MODE.get(status.mode)

    @property
    def hvac_modes(self):
        """Return the list of supported features."""
        li = []
        aircon = self._device_info
        sleep_compat_mode = _sleep_hvac_mode(aircon) if aircon.sleep_mode else None
        if aircon.cool_mode or aircon.relax_mode or (
            aircon.sleep_mode and sleep_compat_mode == HVACMode.COOL
        ):
            li.append(HVACMode.COOL)
        if aircon.heat_mode or getattr(self, "_force_heat_mode", False) \
                or aircon.pre_heat_mode or (
            aircon.sleep_mode and sleep_compat_mode == HVACMode.HEAT
        ):
            li.append(HVACMode.HEAT)
        if aircon.auto_dry_mode or aircon.dry_mode or aircon.more_dry_mode:
            li.append(HVACMode.DRY)
        if aircon.ventilation_mode:
            li.append(HVACMode.FAN_ONLY)
        if aircon.auto_mode or (
            aircon.sleep_mode and sleep_compat_mode == HVACMode.AUTO
        ):
            li.append(HVACMode.AUTO)
        li.append(HVACMode.OFF)
        return li

    @property
    def current_temperature(self):
        """Return the current temperature."""
        valid, value, _source, _observed_ms, _role = \
            self._selected_temperature_evidence()
        if valid:
            return value
        # DTA117D611 cmd3 bit 3 is a reserved byte, not a measured room
        # temperature.  cmd243 is exposed as its own room-scoped sensor and is
        # intentionally not folded into this per-indoor-unit climate field.
        return None

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        setted_temp = self._device_info.status.setted_temp
        return None if setted_temp is None else setted_temp / 10

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 0.5

    @property
    def target_temperature_high(self):
        """Return the highbound target temperature we try to reach."""
        return None

    @property
    def target_temperature_low(self):
        """Return the lowbound target temperature we try to reach."""
        return None

    @property
    def current_humidity(self):
        """Return the current humidity."""
        if self._link_cur_humi:
            return self._cur_humi
        else:
            return None

    @property
    def preset_mode(self) -> Optional[str]:
        """Expose exact extended Daikin modes through HA's native panel API."""
        return _PRESET_MODE_BY_ENUM.get(self._device_info.status.mode)

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return exact extended work modes supported by this indoor unit."""
        modes = [
            label
            for mode, label in _PRESET_MODE_BY_ENUM.items()
            if bool(getattr(
                self._device_info,
                dict(_NATIVE_MODE_CAPABILITIES)[mode],
                False,
            ))
        ]
        return modes or None

    @property
    def is_aux_heat(self):
        """Return true if aux heat is on."""
        return None

    @property
    def fan_mode(self):
        """Return the fan setting."""
        air_flow = self._device_info.status.air_flow
        return fan_mode_name(self._device_info, air_flow)

    @property
    def fan_modes(self) -> Optional[List[str]]:
        """Return the list of available fan modes.

        Requires SUPPORT_FAN_MODE.
        """
        modes = list(_FAN_BY_CAPABILITY.get(self._device_info.fan_volume, []))
        if self._device_info.fan_volume_auto and self._device_info.fan_volume != EnumFanVolume.STEP_2:
            modes.append(FAN_AUTO)
        if self._device_info.fan_volume_mute and self._device_info.fan_volume != EnumFanVolume.STEP_2:
            modes.append(FAN_QUIET)
        return modes

    @property
    def swing_mode(self):
        """Return the swing setting."""
        fan_direction = primary_direction(self._device_info)
        if fan_direction is None or fan_direction == EnumControl.FanDirection.INVALID:
            return None
        if fan_direction == EnumControl.FanDirection.SWING:
            return "自动"
        return _CLIMATE_SWING_NAMES.get(fan_direction)

    @property
    def swing_modes(self) -> Optional[List[str]]:
        """Return the list of available swing modes.

        Requires SUPPORT_SWING_MODE.
        """
        return list(_CLIMATE_SWING_OPTIONS.keys())

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            status = self._device_info.status
            if status.switch == EnumControl.Switch.ON \
                    and status.mode not in [EnumControl.Mode.VENTILATION, EnumControl.Mode.MOREDRY]:
                new_status = AirConStatus(
                    setted_temp=round(kwargs.get(ATTR_TEMPERATURE) * 10.0)
                )
                from .ds_air_service.service import Service
                Service.control(self._device_info, new_status)
                self._schedule_target_verification_queries()
        self.schedule_update_ha_state()

    def set_humidity(self, humidity):
        """Reject the legacy percent API; the wire value is an unproven level."""
        _LOGGER.warning(
            "Ignoring humidity percentage request for %s; native humidity is a 0-3 level enum",
            self._unique_id,
        )
        self.schedule_update_ha_state()

    def set_fan_mode(self, fan_mode):
        """Set new fan mode."""
        status = self._device_info.status
        if status.switch == EnumControl.Switch.ON \
                and status.mode not in _FAN_CONTROL_DISABLED_MODES:
            requested_air_flow = fan_mode_enum(self._device_info, fan_mode)
            if requested_air_flow is None:
                self.schedule_update_ha_state()
                return
            # Match the official Daikin app: a fan change carries only the
            # AIR_FLOW bit.  Reliability comes from authoritative follow-up
            # queries and controller retries, not from adding unrelated fields.
            # Do not mutate the local cache before physical confirmation.
            new_status = AirConStatus(air_flow=requested_air_flow)
            from .ds_air_service.service import Service
            Service.control(self._device_info, new_status)
            self._schedule_fan_verification_queries()
        self.schedule_update_ha_state()

    def _set_switch(self, switch: EnumControl.Switch) -> None:
        """Set only the power state without changing the current mode."""
        # The shared AirCon object feeds climate/select/sensor entities.  Do
        # not mutate it optimistically: only gateway status frames may change
        # physical state exposed to HA and Node-RED.
        new_status = AirConStatus(switch=switch)
        from .ds_air_service.service import Service
        Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()

    def turn_on(self) -> None:
        """Turn the device on using the existing mode."""
        self._set_switch(EnumControl.Switch.ON)

    def turn_off(self) -> None:
        """Turn the device off using the native power command."""
        self._set_switch(EnumControl.Switch.OFF)

    async def async_turn_on(self) -> None:
        """Turn the device on from async HA service calls."""
        await self.hass.async_add_executor_job(self.turn_on)

    async def async_turn_off(self) -> None:
        """Turn the device off from async HA service calls."""
        await self.hass.async_add_executor_job(self.turn_off)

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        aircon = self._device_info
        status = aircon.status
        new_status = AirConStatus()
        hvac_mode_value = getattr(hvac_mode, "value", hvac_mode)
        if hvac_mode == HVACMode.OFF or str(hvac_mode_value).lower() == "off":
            self.turn_off()
            return
        else:
            m = EnumControl.Mode
            mode = None
            if hvac_mode == HVACMode.COOL:
                mode = m.COLD
            elif hvac_mode == HVACMode.HEAT:
                if aircon.heat_mode or getattr(self, "_force_heat_mode", False):
                    mode = m.HEAT
                else:
                    mode = m.PREHEAT
            elif hvac_mode == HVACMode.DRY:
                if aircon.dry_mode:
                    mode = m.DRY
                elif aircon.auto_dry_mode:
                    mode = m.AUTODRY
                elif aircon.more_dry_mode:
                    mode = m.MOREDRY
            elif hvac_mode == HVACMode.FAN_ONLY:
                mode = m.VENTILATION
            elif hvac_mode == HVACMode.AUTO:
                if aircon.auto_mode:
                    mode = m.AUTO
            if mode is None:
                self.schedule_update_ha_state()
                return
            new_status.switch = EnumControl.Switch.ON
            new_status.mode = mode
            from .ds_air_service.service import Service
            Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()

    def set_swing_mode(self, swing_mode):
        """Set new swing mode."""
        status = self._device_info.status
        if status.switch == EnumControl.Switch.ON:
            fan_direction = _CLIMATE_SWING_OPTIONS[swing_mode]
            axis = AXIS_VERTICAL
            if not direction_supported(self._device_info, AXIS_VERTICAL):
                axis = AXIS_HORIZONTAL
            new_status = status_for_axis_direction(self._device_info, axis, fan_direction)
            if new_status is not None:
                if new_status.fan_direction1 is not None:
                    status.fan_direction1 = new_status.fan_direction1
                if new_status.fan_direction2 is not None:
                    status.fan_direction2 = new_status.fan_direction2
                from .ds_air_service.service import Service
                Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()

    def set_preset_mode(self, preset_mode: str) -> None:
        """Send one exact extended Daikin work mode from the native HA panel."""
        mode = _PRESET_ENUM_BY_MODE.get(preset_mode)
        if mode is None or preset_mode not in (self.preset_modes or []):
            self.schedule_update_ha_state()
            return
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

    def turn_aux_heat_on(self) -> None:
        pass

    def turn_aux_heat_off(self) -> None:
        pass

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        SUPPORT_FLAGS = _SUPPORT_FLAGS
        aircon = self._device_info
        if not _FAN_BY_CAPABILITY.get(aircon.fan_volume) \
                or aircon.status.mode in _FAN_CONTROL_DISABLED_MODES:
            SUPPORT_FLAGS = SUPPORT_FLAGS & ~ClimateEntityFeature.FAN_MODE
        if direction_supported(aircon, AXIS_VERTICAL) or direction_supported(aircon, AXIS_HORIZONTAL):
            SUPPORT_FLAGS = SUPPORT_FLAGS | ClimateEntityFeature.SWING_MODE
        if self.preset_modes:
            SUPPORT_FLAGS = SUPPORT_FLAGS | ClimateEntityFeature.PRESET_MODE
        return SUPPORT_FLAGS

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return 16

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return 32

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": "空调%s" % self._name,
            "manufacturer": "Daikin Industries, Ltd."
        }

    @property
    def unique_id(self) -> Optional[str]:
        return self._unique_id

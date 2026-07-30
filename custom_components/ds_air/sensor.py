"""Support for Daikin sensors."""
import time
from datetime import timedelta
from typing import Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo

from .cleaning_device import cleaning_device_info
from .const import DOMAIN, SENSOR_TYPES
from .ds_air_service.dao import (
    AirCon,
    GatewayDiagnostics,
    Sensor,
    UNINITIALIZED_VALUE,
    Ventilation,
)
from .ds_air_service.service import Service


# Entity polling performs no gateway I/O.  It only makes Home Assistant
# recompute age/staleness even when cmd243 replies stop arriving.
SCAN_INTERVAL = timedelta(seconds=30)
INLET_OBSERVATION_TTL_SECONDS = 180
ZHONGHONG_DIAGNOSTIC_TTL_SECONDS = 120


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Perform the setup for Daikin devices."""
    entities = []
    observer = None if hass is None else hass.data[DOMAIN].get(
        "zhonghong_temperature_observer"
    )
    for device in Service.get_sensors():
        for key in SENSOR_TYPES:
            if config_entry.data.get(key):
                entities.append(DsSensor(device, key))
    aircons_by_room = {}
    for aircon in Service.get_aircons():
        aircons_by_room.setdefault(aircon.room_id, []).append(aircon)
        entities.append(DsAirUnitDiagnosticsSensor(
            aircon,
            observer,
        ))
        entities.append(DsAirFilterCleanStatusSensor(aircon))
        if aircon.heat_exchange_cleaning_allow:
            entities.append(DsAirHeatExchangeCleaningStatusSensor(aircon))
    # cmd243 contains room IDs, never indoor-unit IDs.  Publish one entity pair
    # per room even if the integration happens to discover multiple units in
    # that room; duplicating the observation per unit would invent precision.
    for room_aircons in aircons_by_room.values():
        entities.append(DsAirInletSensor(room_aircons, "temperature"))
        entities.append(DsAirInletSensor(room_aircons, "humidity"))
    for vent in Service.get_ventilations():
        entities.append(DsAirVentilationFilterLifeSensor(vent))
    entities.append(DsAirGatewayDiagnosticsSensor(Service.get_gateway_diagnostics()))
    async_add_entities(entities)


class DsSensor(SensorEntity):
    """Representation of a DaikinSensor."""

    def __init__(self, device: Sensor, data_key):
        """Initialize the DaikinSensor."""
        self._data_key = data_key
        self._name = device.alias
        self._unique_id = device.unique_id
        self._is_available = False
        self._state = 0
        self.parse_data(device, True)
        Service.register_sensor_hook(device.unique_id, self.parse_data)

    @property
    def name(self):
        return "%s_%s" % (self._data_key, self._unique_id)

    @property
    def unique_id(self):
        return "%s_%s" % (self._data_key, self._unique_id)

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": "传感器%s" % self._name,
            "manufacturer": "Daikin Industries, Ltd."
        }

    @property
    def available(self):
        return self._is_available

    @property
    def should_poll(self):
        return False

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        try:
            return SENSOR_TYPES.get(self._data_key)[1]
        except TypeError:
            return None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        try:
            return SENSOR_TYPES.get(self._data_key)[0]
        except TypeError:
            return None

    @property
    def device_class(self):
        """Return the device class of this entity."""
        return (
            SENSOR_TYPES.get(self._data_key)[2]
            if self._data_key in SENSOR_TYPES
            else None
        )
    
    @property
    def state_class(self):
        """Return the state class of this entity."""
        return SensorStateClass.MEASUREMENT

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    def parse_data(self, device: Sensor, not_update: bool = False):
        """Parse data sent by gateway."""
        self._is_available = device.connected
        if UNINITIALIZED_VALUE != getattr(device, self._data_key):
            scaling = SENSOR_TYPES.get(self._data_key)[3]
            if type(scaling) != int and type(scaling) != float:
                self._state = str(getattr(device, self._data_key))
            else:
                self._state = getattr(device, self._data_key) / scaling

        if not not_update:
            self.schedule_update_ha_state()
        return True


class DsAirUnitDiagnosticsSensor(SensorEntity):
    """Merge local DS-AIR fault evidence with read-only Zhonghong status."""

    def __init__(self, aircon: AirCon, observer=None):
        self._device_info = aircon
        self._observer = observer
        self._zhonghong_observation = None
        self._remove_zhonghong_listener = None
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{aircon.unique_id}_unit_diagnostics"
        self._attr_name = "机组诊断"
        self._attr_icon = "mdi:hvac"
        Service.register_status_hook(aircon, self._status_change_hook)

        if observer is not None and aircon.unit_id == 0 and aircon.room_id > 0:
            indoor_address = int(aircon.room_id) - 1

            def observe(observation):
                if observation.outer_address != observer.outer_address \
                        or observation.indoor_address != indoor_address:
                    return
                self._zhonghong_observation = observation
                if getattr(self, "hass", None) is not None:
                    self.schedule_update_ha_state()

            self._remove_zhonghong_listener = observer.register_listener(observe)
            latest = observer.latest(observer.outer_address, indoor_address)
            if latest is not None:
                observe(latest)

    @property
    def should_poll(self):
        # Polling performs no network I/O; it only refreshes Zhonghong age/TTL.
        return True

    def update(self):
        """Refresh TTL-derived state only."""

    @property
    def _zhonghong_age_seconds(self):
        observation = self._zhonghong_observation
        if observation is None:
            return None
        return max(0.0, time.time() - observation.observed_at_ms / 1000.0)

    @property
    def _zhonghong_fresh(self):
        age = self._zhonghong_age_seconds
        return age is not None and age <= ZHONGHONG_DIAGNOSTIC_TTL_SECONDS

    @property
    def native_value(self):
        ds_code = self._device_info.failure_code_normalized
        observation = self._zhonghong_observation if self._zhonghong_fresh else None
        if ds_code not in (None, "", "00"):
            return "fault"
        if observation is not None and observation.has_fault:
            return "fault"
        if observation is not None and not observation.online:
            return "offline"
        if ds_code == "00" or (
                observation is not None and observation.fault_code == 0):
            return "normal"
        return "unknown"

    @property
    def available(self):
        return self._device_info.failure_source_timestamp is not None \
            or self._zhonghong_fresh

    @property
    def extra_state_attributes(self):
        observation = self._zhonghong_observation
        attributes = {
            "condition": self.native_value,
            "command_authority": "native_ds_air",
            "diagnostic_sources": ["daikin_local_cmd6", "zhonghong_readonly_0x50"],
            "ds_air_fault_code_raw": self._device_info.failure_code_raw,
            "ds_air_fault_code_normalized": self._device_info.failure_code_normalized,
            "ds_air_fault_level": self._device_info.failure_level,
            "ds_air_fault_observed_at": self._device_info.failure_source_timestamp,
            "zhonghong_valid": self._zhonghong_fresh,
            "zhonghong_age_seconds": (
                None if self._zhonghong_age_seconds is None
                else round(self._zhonghong_age_seconds, 1)
            ),
        }
        if observation is None:
            return attributes
        attributes.update({
            "zhonghong_source": self._observer.source_for(observation)
            if self._observer is not None else None,
            "zhonghong_observed_at_ms": observation.observed_at_ms,
            "zhonghong_outer_address": observation.outer_address,
            "zhonghong_indoor_address": observation.indoor_address,
            "zhonghong_online": observation.online,
            "zhonghong_power_code": observation.power_code,
            "zhonghong_set_temperature_c": observation.set_temperature_c,
            "zhonghong_mode_code": observation.mode_code,
            "zhonghong_fan_code": observation.fan_code,
            "zhonghong_return_temperature_c": observation.temperature_c,
            "zhonghong_fault_code": observation.fault_code,
            "zhonghong_fault_code_hex": f"0x{observation.fault_code:02X}",
            "zhonghong_has_fault": observation.has_fault,
            "zhonghong_baffle_code": observation.baffle_code,
            "zhonghong_baffle_vertical_raw": (observation.baffle_code >> 4) & 0x0F,
            "zhonghong_baffle_horizontal_raw": observation.baffle_code & 0x0F,
            "zhonghong_other_info": observation.other_info,
            "zhonghong_is_main_unit": observation.is_main_unit,
        })
        return attributes

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {(DOMAIN, self._device_info.unique_id)},
            "name": "空调%s" % self._device_info.alias,
            "manufacturer": "Daikin Industries, Ltd.",
        }

    def _status_change_hook(self, **kwargs):
        if kwargs.get("aircon") is not None:
            self._device_info = kwargs["aircon"]
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self):
        if self._remove_zhonghong_listener is not None:
            self._remove_zhonghong_listener()
            self._remove_zhonghong_listener = None
        await super().async_will_remove_from_hass()


class DsAirFilterCleanStatusSensor(SensorEntity):
    """Local cmd9 filter-clean reminder state for one indoor unit."""

    def __init__(self, aircon: AirCon):
        self._device_info = aircon
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{aircon.unique_id}_filter_clean_status"
        self._attr_name = "滤网清洗提醒"
        self._attr_icon = "mdi:air-filter"
        Service.register_status_hook(aircon, self._status_change_hook)

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return self._device_info.filter_clean_sign_source_timestamp is not None

    @property
    def native_value(self):
        status = self._device_info.filter_clean_sign_status
        if status is None:
            return "unknown"
        if status == 0:
            return "normal"
        if status in (1, 2, 4):
            return "service_required"
        return "unknown_code"

    @property
    def extra_state_attributes(self):
        return {
            "source": "daikin_official_local_cmd9",
            "raw_status": self._device_info.filter_clean_sign_status,
            "service_required_codes": [1, 2, 4],
            "observed_at": self._device_info.filter_clean_sign_source_timestamp,
            "reset_command": "daikin_official_local_cmd21",
            "lifetime_note": "indoor_used_time_is_cloud_getFilterUsedInfo",
        }

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {(DOMAIN, self._device_info.unique_id)},
            "name": "空调%s" % self._device_info.alias,
            "manufacturer": "Daikin Industries, Ltd.",
        }

    def _status_change_hook(self, **kwargs):
        if kwargs.get("aircon") is not None:
            self._device_info = kwargs["aircon"]
        self.schedule_update_ha_state()


class DsAirVentilationFilterLifeSensor(SensorEntity):
    """Local cmd10 VAM filter remaining percentage."""

    def __init__(self, vent: Ventilation):
        self._device_info = vent
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{vent.unique_id}_filter_remaining"
        self._attr_name = "滤网剩余寿命"
        self._attr_icon = "mdi:air-filter"
        self._attr_native_unit_of_measurement = PERCENTAGE
        Service.register_vent_hook(vent, self._status_change_hook)

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return (
            self._device_info.filter_service_life_source_timestamp is not None
            and self._device_info.filter_used_percent is not None
        )

    @property
    def native_value(self):
        used = self._device_info.filter_used_percent
        return None if used is None else 100 - used

    @property
    def extra_state_attributes(self):
        return {
            "source": "daikin_official_local_cmd10",
            "scope": "vam_room",
            "used_percent": self._device_info.filter_used_percent,
            "observed_at": self._device_info.filter_service_life_source_timestamp,
            "indoor_unit_lifetime_included": False,
        }

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {(DOMAIN, self._device_info.unique_id)},
            "name": "新风 %s" % self._device_info.alias,
            "manufacturer": "Daikin Industries, Ltd.",
        }

    def _status_change_hook(self, **kwargs):
        if kwargs.get("vent") is not None:
            self._device_info = kwargs["vent"]
        self.schedule_update_ha_state()


class DsAirInletSensor(SensorEntity):
    """Room-scoped inlet observation read through official Daikin cmd243."""

    def __init__(self, room_aircons: list[AirCon], kind: str):
        if not room_aircons:
            raise ValueError("cmd243 room sensor requires at least one indoor unit")
        aircon = room_aircons[0]
        self._device_info = aircon
        self._kind = kind
        self._room_id = aircon.room_id
        self._room_alias = aircon.alias
        self._room_unit_ids = sorted({item.unit_id for item in room_aircons})
        self._attr_has_entity_name = True
        suffix = "inlet_temperature" if kind == "temperature" else "inlet_humidity"
        self._attr_unique_id = f"daikin_room_{self._room_id}_{suffix}"
        self.entity_id = f"sensor.ds_air_room_{self._room_id}_{suffix}"
        self._attr_name = "回风温度" if kind == "temperature" else "回风湿度"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        if kind == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        else:
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        Service.register_status_hook(aircon, self._status_change_hook)

    @property
    def should_poll(self):
        return True

    def update(self):
        """Refresh TTL-derived state only; network polling lives in Service."""

    @property
    def age_seconds(self):
        observed = self._device_info.inlet_source_monotonic
        if observed is None:
            return None
        return max(0.0, time.monotonic() - observed)

    @property
    def stale(self):
        age = self.age_seconds
        return age is None or age > INLET_OBSERVATION_TTL_SECONDS

    @property
    def measurement_quality(self):
        if self._kind == "temperature":
            return self._device_info.inlet_temperature_quality
        return self._device_info.inlet_humidity_quality

    @property
    def quality(self):
        if self._device_info.inlet_source_timestamp is None:
            return "missing"
        if self.stale:
            return "stale"
        return self.measurement_quality

    @property
    def available(self):
        return self.native_value is not None and self.quality == "valid"

    @property
    def native_value(self):
        if self._kind == "temperature":
            return self._device_info.inlet_temperature_c
        return self._device_info.inlet_humidity_percent

    @property
    def extra_state_attributes(self):
        return {
            "source": "daikin_official_local_cmd243",
            "scope": "room",
            "scope_key": f"room:{self._room_id}",
            "room_id": self._room_id,
            "room_unit_ids": self._room_unit_ids,
            "room_unit_count": len(self._room_unit_ids),
            "scope_relationship": (
                "one_room_one_unit"
                if len(self._room_unit_ids) == 1
                else "one_room_multiple_units_shared_observation"
            ),
            "observed_at": self._device_info.inlet_source_timestamp,
            "age_seconds": None if self.age_seconds is None else round(self.age_seconds, 1),
            "stale": self.stale,
            "quality": self.quality,
            "measurement_quality": self.measurement_quality,
            "raw_value": self.native_value,
            "parse_status": self._device_info.inlet_parse_status,
            "raw_tlvs": self._device_info.inlet_raw_tlvs,
        }

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {(DOMAIN, f"daikin_room_{self._room_id}")},
            "name": "大金空调区域%s" % self._room_alias,
            "manufacturer": "Daikin Industries, Ltd.",
        }

    def _status_change_hook(self, **kwargs):
        aircon = kwargs.get("aircon")
        if aircon is not None and aircon.room_id == self._room_id:
            self._device_info = aircon
        self.schedule_update_ha_state()


class DsAirHeatExchangeCleaningStatusSensor(SensorEntity):
    """Protocol-backed status sensor for one DS-AIR self-cleaning target."""

    def __init__(self, aircon: AirCon):
        self._device_info = aircon
        # A new identity avoids mixing legacy percent history with work-state codes.
        self._attr_unique_id = f"{aircon.unique_id}_heat_exchange_cleaning_status"
        self._attr_name = f"{aircon.alias} 自清洁状态"
        self._attr_icon = "mdi:air-filter"

        Service.register_status_hook(aircon, self._status_change_hook)

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return self._device_info.heat_exchange_cleaning_allow

    @property
    def native_value(self):
        return self._device_info.heat_exchange_cleaning_work_state

    @property
    def extra_state_attributes(self):
        return {
            "state_semantics": "work_state_code",
            "capability": self._device_info.heat_exchange_cleaning_capability,
            "can_join": self._device_info.heat_exchange_cleaning_can_join,
            "phase_duration": self._device_info.heat_exchange_cleaning_phase_duration,
            "v_sleep_value_1": self._device_info.heat_exchange_cleaning_v_sleep_value_1,
            "v_sleep_value_2": self._device_info.heat_exchange_cleaning_v_sleep_value_2,
            "finish": self._device_info.heat_exchange_cleaning_finish,
            "outdoor_status": self._device_info.heat_exchange_cleaning_outdoor_status,
            "raw_tlvs": self._device_info.heat_exchange_cleaning_raw_tlvs,
            "parse_status": self._device_info.heat_exchange_cleaning_parse_status,
            "source_timestamp": self._device_info.heat_exchange_cleaning_source_timestamp,
        }

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return cleaning_device_info()

    def _status_change_hook(self, **kwargs):
        if kwargs.get("aircon") is not None:
            aircon: AirCon = kwargs["aircon"]
            aircon.status = self._device_info.status
            self._device_info = aircon
        self.schedule_update_ha_state()


class DsAirGatewayDiagnosticsSensor(SensorEntity):
    """One non-sensitive gateway diagnostic entity with unknown-safe values."""

    def __init__(self, diagnostics: GatewayDiagnostics):
        self._diagnostics = diagnostics
        self._attr_unique_id = "ds_air_gateway_diagnostics"
        self._attr_name = "DS-AIR 网关诊断"
        self._attr_icon = "mdi:router-wireless"
        Service.register_diagnostics_hook(self._diagnostics_hook)

    @property
    def should_poll(self):
        return False

    @property
    def native_value(self):
        return self._diagnostics.gateway_version

    @property
    def extra_state_attributes(self):
        return {
            "wifi_version": self._diagnostics.wifi_version,
            "gateway_time": self._diagnostics.gateway_time,
            "gateway_info_source_timestamp": self._diagnostics.gateway_info_source_timestamp,
            "wifi_signal_strength_dbm": self._diagnostics.wifi_signal_strength,
            "wifi_ping_success_count": self._diagnostics.wifi_ping_success_count,
            "wifi_network_delay_ms": self._diagnostics.wifi_network_delay,
            "gateway_signal_raw": self._diagnostics.gateway_signal_raw,
            "gateway_signal_source_timestamp": self._diagnostics.gateway_signal_source_timestamp,
            "last_error_code_raw": self._diagnostics.last_error_code_raw,
            "last_error_code_normalized": self._diagnostics.last_error_code_normalized,
            "last_error_device_id": self._diagnostics.last_error_device_id,
            "last_error_device": self._diagnostics.last_error_device,
            "last_error_room": self._diagnostics.last_error_room,
            "last_error_unit": self._diagnostics.last_error_unit,
            "last_error_level": self._diagnostics.last_error_level,
            "last_error_source_timestamp": self._diagnostics.last_error_source_timestamp,
            "cmd10_supported": self._diagnostics.filter_service_life_supported,
            "cmd10_source_timestamp": self._diagnostics.filter_service_life_source_timestamp,
            "cmd220_supported": self._diagnostics.daikin_care_exponent_supported,
            "cmd220_source_timestamp": self._diagnostics.daikin_care_exponent_source_timestamp,
            "vam_cleaning_unmapped": self._diagnostics.vam_cleaning_unmapped,
        }

    def _diagnostics_hook(self, diagnostics: GatewayDiagnostics):
        self._diagnostics = diagnostics
        self.schedule_update_ha_state()

"""Support for Daikin sensors."""
from typing import Optional

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.entity import DeviceInfo

from .cleaning_device import cleaning_device_info
from .const import DOMAIN, SENSOR_TYPES
from .ds_air_service.dao import AirCon, Sensor, UNINITIALIZED_VALUE
from .ds_air_service.service import Service


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Perform the setup for Daikin devices."""
    entities = []
    for device in Service.get_sensors():
        for key in SENSOR_TYPES:
            if config_entry.data.get(key):
                entities.append(DsSensor(device, key))
    for aircon in Service.get_aircons():
        if aircon.heat_exchange_cleaning_allow:
            entities.append(DsAirHeatExchangeCleaningProgressSensor(aircon))
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


class DsAirHeatExchangeCleaningProgressSensor(SensorEntity):
    """Progress sensor for one DS-AIR self-cleaning target."""

    def __init__(self, aircon: AirCon):
        self._device_info = aircon
        self._attr_unique_id = f"{aircon.unique_id}_heat_exchange_cleaning_progress"
        self._attr_name = f"{aircon.alias} 自清洁进度"
        self._attr_icon = "mdi:progress-clock"
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT

        Service.register_status_hook(aircon, self._status_change_hook)

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return self._device_info.heat_exchange_cleaning_allow

    @property
    def native_value(self):
        if self._device_info.heat_exchange_cleaning_percent is None:
            return 0
        return self._device_info.heat_exchange_cleaning_percent

    @property
    def extra_state_attributes(self):
        return {
            "status_code": self._device_info.heat_exchange_cleaning_status,
            "phase_duration": self._device_info.heat_exchange_cleaning_phase_duration,
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

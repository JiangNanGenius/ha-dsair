from homeassistant.const import UnitOfTemperature, PERCENTAGE, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, \
    CONCENTRATION_PARTS_PER_MILLION, CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER
from homeassistant.components.sensor import SensorDeviceClass

from .ds_air_service.ctrl_enum import EnumSensor

DOMAIN = "ds_air"
CONF_GW = "gw"
CONF_LINKS = "link"
CONF_FORCE_HEAT_MODE = "force_heat_mode"
CONF_ZHONGHONG_TEMPERATURE_ENABLED = "zhonghong_temperature_enabled"
CONF_ZHONGHONG_HOST = "zhonghong_host"
CONF_ZHONGHONG_PORT = "zhonghong_port"
CONF_ZHONGHONG_OUTER_ADDRESS = "zhonghong_outer_address"
CONF_ZHONGHONG_POLL_INTERVAL = "zhonghong_poll_interval"
DEFAULT_ZHONGHONG_HOST = "192.168.20.7"
DEFAULT_ZHONGHONG_PORT = 9999
DEFAULT_ZHONGHONG_OUTER_ADDRESS = 1
DEFAULT_ZHONGHONG_POLL_INTERVAL = 10
DEFAULT_HOST = "192.168.1."
DEFAULT_PORT = 8008
DEFAULT_GW = "DTA117C611"
GW_LIST = ["DTA117C611", "DTA117B611", "DTA117D611"]
SENSOR_TYPES = {
    "temp": [UnitOfTemperature.CELSIUS, None, SensorDeviceClass.TEMPERATURE, 10],
    "humidity": [PERCENTAGE, None, SensorDeviceClass.HUMIDITY, 10],
    "pm25": [CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, None, SensorDeviceClass.PM25, 1],
    "co2": [CONCENTRATION_PARTS_PER_MILLION, None, SensorDeviceClass.CO2, 1],
    "tvoc": [CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, None, SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS, 0.1],
    "voc": [None, None, SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS, EnumSensor.Voc],
    "hcho": [CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER, None, None, 100],
}

SMALL_VAM_SENSOR_TYPES = {
    "in_door_temp": [UnitOfTemperature.CELSIUS, None, SensorDeviceClass.TEMPERATURE, 10],
    "out_door_temp": [UnitOfTemperature.CELSIUS, None, SensorDeviceClass.TEMPERATURE, 10],
    "out_door_humidity": [PERCENTAGE, None, SensorDeviceClass.HUMIDITY, 1],
    "pm25": [CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, None, SensorDeviceClass.PM25, 1],
}

import asyncio
import importlib
import sys
import time
import types
import unittest
from enum import Enum, IntFlag
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "custom_components" / "ds_air"


def _module(name):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


def _install_homeassistant_stubs():
    """Install the narrow HA surface needed to import the climate entity."""
    voluptuous = _module("voluptuous")
    voluptuous.Optional = lambda value: value

    homeassistant = _module("homeassistant")
    components = _module("homeassistant.components")
    climate = _module("homeassistant.components.climate")
    climate_const = _module("homeassistant.components.climate.const")
    select = _module("homeassistant.components.select")
    config_entries = _module("homeassistant.config_entries")
    ha_const = _module("homeassistant.const")
    core = _module("homeassistant.core")
    helpers = _module("homeassistant.helpers")
    config_validation = _module("homeassistant.helpers.config_validation")
    entity = _module("homeassistant.helpers.entity")
    entity_platform = _module("homeassistant.helpers.entity_platform")
    event = _module("homeassistant.helpers.event")

    class ClimateEntity:
        pass

    class ClimateEntityFeature(IntFlag):
        TARGET_TEMPERATURE = 1
        FAN_MODE = 2
        PRESET_MODE = 4
        TURN_ON = 8
        TURN_OFF = 16
        TARGET_HUMIDITY = 32
        SWING_MODE = 64

    class SelectEntity:
        pass

    class HVACMode(str, Enum):
        OFF = "off"
        AUTO = "auto"
        COOL = "cool"
        DRY = "dry"
        FAN_ONLY = "fan_only"
        HEAT = "heat"

    class HVACAction(str, Enum):
        OFF = "off"
        COOLING = "cooling"
        DRYING = "drying"
        FAN = "fan"
        HEATING = "heating"
        PREHEATING = "preheating"

    class _Schema:
        def extend(self, _value):
            return self

    climate.ClimateEntity = ClimateEntity
    climate.ClimateEntityFeature = ClimateEntityFeature
    climate.HVACMode = HVACMode
    climate.HVACAction = HVACAction
    climate.PLATFORM_SCHEMA = _Schema()
    climate.PRESET_NONE = "none"
    climate.PRESET_SLEEP = "sleep"
    climate.PRESET_COMFORT = "comfort"
    climate.FAN_AUTO = "auto"
    climate.FAN_LOW = "low"
    climate.FAN_MEDIUM = "medium"
    climate.FAN_HIGH = "high"
    climate_const.FAN_AUTO = climate.FAN_AUTO
    climate_const.FAN_LOW = climate.FAN_LOW
    climate_const.FAN_MEDIUM = climate.FAN_MEDIUM
    climate_const.FAN_HIGH = climate.FAN_HIGH
    select.SelectEntity = SelectEntity

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    class Event:
        pass

    class DeviceInfo:
        pass

    class UnitOfTemperature:
        CELSIUS = "°C"

    config_entries.ConfigEntry = ConfigEntry
    core.HomeAssistant = HomeAssistant
    core.Event = Event
    entity.DeviceInfo = DeviceInfo
    entity_platform.AddEntitiesCallback = object
    event.async_track_state_change_event = lambda *args, **kwargs: None
    config_validation.string = str
    config_validation.port = int
    ha_const.UnitOfTemperature = UnitOfTemperature
    ha_const.ATTR_TEMPERATURE = "temperature"
    ha_const.CONF_HOST = "host"
    ha_const.CONF_PORT = "port"

    homeassistant.components = components
    homeassistant.config_entries = config_entries
    homeassistant.const = ha_const
    homeassistant.core = core
    homeassistant.helpers = helpers
    components.climate = climate
    components.select = select
    helpers.config_validation = config_validation
    helpers.entity = entity
    helpers.entity_platform = entity_platform
    helpers.event = event


def _install_ds_air_package_stub():
    """Import climate.py without executing the integration package initializer."""
    custom_components = _module("custom_components")
    custom_components.__path__ = [str(PROJECT_ROOT / "custom_components")]
    package = _module("custom_components.ds_air")
    package.__path__ = [str(PACKAGE_ROOT)]

    const = _module("custom_components.ds_air.const")
    const.DOMAIN = "ds_air"
    const.CONF_LINKS = "link"
    const.CONF_FORCE_HEAT_MODE = "force_heat_mode"


_install_homeassistant_stubs()
_install_ds_air_package_stub()

climate_module = importlib.import_module("custom_components.ds_air.climate")
DsAir = climate_module.DsAir
EnumControl = climate_module.EnumControl
EnumFanVolume = climate_module.EnumFanVolume
EnumOutDoorRunCond = importlib.import_module(
    "custom_components.ds_air.ds_air_service.ctrl_enum"
).EnumOutDoorRunCond
Config = importlib.import_module(
    "custom_components.ds_air.ds_air_service.config"
).Config
AirCon = importlib.import_module(
    "custom_components.ds_air.ds_air_service.dao"
).AirCon
AirConStatus = importlib.import_module(
    "custom_components.ds_air.ds_air_service.dao"
).AirConStatus
select_module = importlib.import_module("custom_components.ds_air.select")


class ClimatePartialStatusTest(unittest.TestCase):
    def setUp(self):
        self._is_c611 = Config.is_c611
        Config.is_c611 = False

    def tearDown(self):
        Config.is_c611 = self._is_c611

    def _entity(self, status=None):
        aircon = AirCon()
        aircon.status = status or AirConStatus()
        entity = DsAir.__new__(DsAir)
        entity._device_info = aircon
        entity._force_heat_mode = False
        entity._link_cur_temp = False
        entity._link_cur_humi = False
        entity._cur_temp = None
        entity._cur_humi = None
        entity._linked_temp_observed_at_ms = 0
        entity._linked_humi_observed_at_ms = 0
        entity.linked_temp_entity_id = None
        entity.linked_humi_entity_id = None
        entity._unique_id = aircon.unique_id
        entity._status_physical_epoch = "test-status-epoch"
        entity._power_physical_generation = 1 if aircon.status.switch is not None else 0
        entity._power_physical_observed_at_ms = int(time.time() * 1000)
        entity._power_physical_source = "test_gateway_status"
        entity._mode_physical_generation = 1 if aircon.status.mode is not None else 0
        entity._mode_physical_observed_at_ms = int(time.time() * 1000)
        entity._mode_physical_source = "test_gateway_status"
        entity._fan_physical_epoch = "test-physical-epoch"
        entity._fan_physical_generation = 1 if aircon.status.air_flow is not None else 0
        entity._fan_physical_observed_at_ms = int(time.time() * 1000)
        entity._fan_physical_source = "test_gateway_status"
        entity._target_physical_epoch = "test-target-epoch"
        entity._target_physical_generation = 1 if aircon.status.setted_temp is not None else 0
        entity._target_physical_observed_at_ms = (
            int(time.time() * 1000) if aircon.status.setted_temp is not None else 0
        )
        entity._target_physical_source = (
            "test_gateway_status" if aircon.status.setted_temp is not None else "unknown"
        )
        entity._fan_verify_epoch = 0
        entity._fan_verify_timers = []
        entity._target_verify_epoch = 0
        entity._target_verify_timers = []
        entity.schedule_update_ha_state = lambda: None
        return entity

    def test_unknown_partial_status_is_safe_for_climate_properties(self):
        entity = self._entity()

        self.assertIsNone(entity.target_humidity)
        self.assertIsNone(entity.hvac_action)
        self.assertIsNone(entity.hvac_mode)
        self.assertIsNone(entity.current_temperature)
        self.assertIsNone(entity.target_temperature)
        self.assertIsNone(entity.preset_mode)
        self.assertIsNone(entity.fan_mode)

    def test_partial_status_does_not_replace_last_real_fan_or_temperatures(self):
        stored = AirConStatus(
            current_temp=270,
            setted_temp=215,
            switch=EnumControl.Switch.ON,
            air_flow=EnumControl.AirFlow.SUPER_STRONG,
            mode=EnumControl.Mode.COLD,
        )
        entity = self._entity(stored)
        entity._device_info.fan_volume = EnumFanVolume.STEP_5

        entity._status_change_hook(status=AirConStatus())

        self.assertEqual(EnumControl.AirFlow.SUPER_STRONG, entity._device_info.status.air_flow)
        self.assertEqual(270, entity._device_info.status.current_temp)
        self.assertEqual(215, entity._device_info.status.setted_temp)
        self.assertEqual("5", entity.fan_mode)
        self.assertIsNone(
            entity.current_temperature,
            "legacy cmd2/cmd3 bit3 cache must never be exposed as temperature",
        )
        self.assertEqual(21.5, entity.target_temperature)

        entity._link_cur_temp = True
        entity._cur_temp = 24.3
        self.assertEqual(24.3, entity.current_temperature)

    def test_fan_command_is_not_optimistically_applied_and_uses_official_field(self):
        stored = AirConStatus(
            switch=EnumControl.Switch.ON,
            air_flow=EnumControl.AirFlow.AUTO,
            mode=EnumControl.Mode.COLD,
        )
        entity = self._entity(stored)
        entity._device_info.fan_volume = EnumFanVolume.STEP_5
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        sent = []
        original_control = service_module.Service.control
        try:
            service_module.Service.control = staticmethod(
                lambda aircon, status: sent.append((aircon, status))
            )
            entity._schedule_fan_verification_queries = lambda: sent.append("verify")
            entity.set_fan_mode("5")
        finally:
            service_module.Service.control = original_control

        self.assertEqual(EnumControl.AirFlow.AUTO, entity._device_info.status.air_flow)
        self.assertEqual(2, len(sent))
        new_status = sent[0][1]
        self.assertIsNone(new_status.switch)
        self.assertIsNone(new_status.mode)
        self.assertEqual(EnumControl.AirFlow.SUPER_STRONG, new_status.air_flow)
        self.assertEqual("verify", sent[1])

    def test_gateway_airflow_status_advances_physical_generation(self):
        stored = AirConStatus(
            switch=EnumControl.Switch.ON,
            air_flow=EnumControl.AirFlow.AUTO,
            mode=EnumControl.Mode.COLD,
        )
        entity = self._entity(stored)
        entity._device_info.fan_volume = EnumFanVolume.STEP_5
        before = entity._fan_physical_generation
        entity._status_change_hook(
            status=AirConStatus(air_flow=EnumControl.AirFlow.SUPER_STRONG)
        )

        self.assertEqual(before + 1, entity._fan_physical_generation)
        self.assertEqual("gateway_status", entity._fan_physical_source)
        self.assertGreater(entity._fan_physical_observed_at_ms, 0)
        self.assertEqual("5", entity.fan_mode)
        self.assertEqual(
            entity._fan_physical_generation,
            entity.extra_state_attributes["ds_air_fan_physical_generation"],
        )
        self.assertTrue(entity.extra_state_attributes["ds_air_fan_physical_epoch"])
        self.assertEqual(
            "5", entity.extra_state_attributes["ds_air_fan_physical_mode"]
        )
        self.assertEqual(
            [1.0, 3.0, 8.0, 15.0, 25.0],
            entity.extra_state_attributes["ds_air_fan_verify_delays_s"],
        )

    def test_gateway_power_and_mode_updates_have_independent_physical_coordinates(self):
        entity = self._entity(AirConStatus(
            switch=EnumControl.Switch.ON,
            mode=EnumControl.Mode.COLD,
        ))
        power_before = entity._power_physical_generation
        mode_before = entity._mode_physical_generation

        entity._status_change_hook(status=AirConStatus(mode=EnumControl.Mode.RELAX))
        self.assertEqual(mode_before + 1, entity._mode_physical_generation)
        self.assertEqual(power_before, entity._power_physical_generation)
        self.assertEqual("gateway_status", entity._mode_physical_source)

        entity._status_change_hook(status=AirConStatus(switch=EnumControl.Switch.OFF))
        self.assertEqual(power_before + 1, entity._power_physical_generation)
        self.assertEqual(mode_before + 1, entity._mode_physical_generation)
        attrs = entity.extra_state_attributes
        self.assertEqual("test-status-epoch", attrs["ds_air_status_physical_epoch"])
        self.assertEqual("off", attrs["ds_air_power_physical_value"])
        self.assertEqual("comfort", attrs["ds_air_mode_physical_key"])
        self.assertEqual(6, attrs["ds_air_mode_physical_code"])
        self.assertGreater(attrs["ds_air_power_physical_observed_at_ms"], 0)
        self.assertGreater(attrs["ds_air_mode_physical_observed_at_ms"], 0)

    def test_fan_verification_replaces_old_timers_and_covers_25_seconds(self):
        entity = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                air_flow=EnumControl.AirFlow.AUTO,
                mode=EnumControl.Mode.COLD,
            )
        )
        cancelled = []
        entity._fan_verify_timers = [
            type("OldTimer", (), {"cancel": lambda self: cancelled.append(True)})()
        ]
        created = []

        class FakeTimer:
            def __init__(self, delay, callback, args=()):
                self.delay = delay
                self.callback = callback
                self.args = args
                self.daemon = False
                self.started = False
                created.append(self)

            def start(self):
                self.started = True

            def cancel(self):
                cancelled.append(True)

        original_timer = climate_module.Timer
        try:
            climate_module.Timer = FakeTimer
            entity._schedule_fan_verification_queries()
        finally:
            climate_module.Timer = original_timer

        self.assertEqual([True], cancelled)
        self.assertEqual([1.0, 3.0, 8.0, 15.0, 25.0], [t.delay for t in created])
        self.assertTrue(all(t.daemon and t.started for t in created))
        self.assertTrue(all(t.args == (entity._fan_verify_epoch,) for t in created))

    def test_targeted_fan_query_uses_this_aircon_and_runtime_epoch(self):
        entity = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                air_flow=EnumControl.AirFlow.AUTO,
                mode=EnumControl.Mode.COLD,
            )
        )
        entity._device_info.room_id = 5
        entity._device_info.unit_id = 0
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        sent = []
        original_ready = service_module.Service.is_ready
        original_send = service_module.Service.send_msg
        try:
            service_module.Service.is_ready = staticmethod(lambda: True)
            service_module.Service.send_msg = staticmethod(lambda query: sent.append(query))
            entity._query_fan_status(entity._fan_verify_epoch)
            entity._query_fan_status(entity._fan_verify_epoch + 1)
        finally:
            service_module.Service.is_ready = original_ready
            service_module.Service.send_msg = original_send

        self.assertEqual(1, len(sent))
        self.assertIs(entity._device_info, sent[0].device)
        self.assertEqual(5, sent[0].device.room_id)
        self.assertEqual(0, sent[0].device.unit_id)

    def test_target_temperature_waits_for_gateway_and_has_independent_evidence(self):
        entity = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                mode=EnumControl.Mode.COLD,
                setted_temp=215,
            )
        )
        generation = entity._target_physical_generation
        sent = []
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        original_control = service_module.Service.control
        try:
            service_module.Service.control = staticmethod(
                lambda aircon, status: sent.append((aircon, status))
            )
            entity._schedule_target_verification_queries = lambda: sent.append("verify")
            entity.set_temperature(temperature=23.0)
        finally:
            service_module.Service.control = original_control

        self.assertEqual(21.5, entity.target_temperature)
        self.assertEqual(generation, entity._target_physical_generation)
        self.assertEqual(230, sent[0][1].setted_temp)
        self.assertEqual("verify", sent[1])

        entity._status_change_hook(status=AirConStatus(setted_temp=230))
        self.assertEqual(23.0, entity.target_temperature)
        self.assertEqual(generation + 1, entity._target_physical_generation)
        attrs = entity.extra_state_attributes
        self.assertEqual("test-target-epoch", attrs["ds_air_target_physical_epoch"])
        self.assertEqual("gateway_status", attrs["ds_air_target_physical_source"])
        self.assertEqual(23.0, attrs["ds_air_target_physical_value"])
        self.assertGreater(attrs["ds_air_target_physical_observed_at_ms"], 0)

    def test_targeted_temperature_query_uses_this_aircon_and_runtime_epoch(self):
        entity = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                mode=EnumControl.Mode.COLD,
                setted_temp=215,
            )
        )
        entity._device_info.room_id = 5
        entity._device_info.unit_id = 0
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        sent = []
        original_ready = service_module.Service.is_ready
        original_send = service_module.Service.send_msg
        try:
            service_module.Service.is_ready = staticmethod(lambda: True)
            service_module.Service.send_msg = staticmethod(lambda query: sent.append(query))
            entity._query_target_status(entity._target_verify_epoch)
            entity._query_target_status(entity._target_verify_epoch + 1)
        finally:
            service_module.Service.is_ready = original_ready
            service_module.Service.send_msg = original_send

        self.assertEqual(1, len(sent))
        self.assertIs(entity._device_info, sent[0].device)
        self.assertEqual(5, sent[0].device.room_id)
        self.assertEqual(0, sent[0].device.unit_id)

    def test_external_measurements_clear_on_invalid_or_unavailable_state(self):
        entity = self._entity()
        entity.linked_temp_entity_id = "sensor.external_temperature"
        entity.linked_humi_entity_id = "sensor.external_humidity"

        entity.update_cur_temp("24.25")
        entity.update_cur_humi("57.9")
        self.assertEqual(24.25, entity.current_temperature)
        self.assertEqual(57, entity.current_humidity)
        attrs = entity.extra_state_attributes
        self.assertTrue(attrs["ds_air_current_temperature_valid"])
        self.assertEqual(
            "sensor.external_temperature",
            attrs["ds_air_current_temperature_source"],
        )
        self.assertGreater(attrs["ds_air_current_temperature_observed_at_ms"], 0)

        entity.update_cur_temp("unavailable")
        entity.update_cur_humi(None)
        self.assertIsNone(entity.current_temperature)
        self.assertIsNone(entity.current_humidity)
        attrs = entity.extra_state_attributes
        self.assertFalse(attrs["ds_air_current_temperature_valid"])
        self.assertFalse(attrs["ds_air_current_humidity_valid"])
        self.assertIsNone(attrs["ds_air_current_temperature_source"])
        self.assertEqual(0, attrs["ds_air_current_temperature_observed_at_ms"])

        entity.update_cur_temp("nan")
        entity.update_cur_humi("inf")
        self.assertIsNone(entity.current_temperature)
        self.assertIsNone(entity.current_humidity)

    def test_link_listener_clears_value_when_source_entity_is_removed(self):
        aircon = AirCon()
        aircon.alias = "test room"
        added = []
        captured = {}
        entry = types.SimpleNamespace(options={
            "link": [{
                "climate": "test room",
                "sensor_temp": "sensor.external_temperature",
            }]
        })
        hass = types.SimpleNamespace(data={"ds_air": {}})
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        original_get_aircons = service_module.Service.get_aircons
        original_register = service_module.Service.register_status_hook
        original_track = climate_module.async_track_state_change_event
        try:
            service_module.Service.get_aircons = staticmethod(lambda: [aircon])
            service_module.Service.register_status_hook = staticmethod(lambda *_args: None)
            climate_module.async_track_state_change_event = (
                lambda _hass, _entity_ids, listener: (
                    captured.setdefault("listener", listener),
                    (lambda: None),
                )[1]
            )
            asyncio.run(
                climate_module.async_setup_entry(
                    hass,
                    entry,
                    lambda entities: added.extend(entities),
                )
            )
        finally:
            service_module.Service.get_aircons = original_get_aircons
            service_module.Service.register_status_hook = original_register
            climate_module.async_track_state_change_event = original_track

        entity = added[0]
        entity.schedule_update_ha_state = lambda: None
        entity.update_cur_temp("24.5")
        self.assertEqual(24.5, entity.current_temperature)
        event = types.SimpleNamespace(data={
            "entity_id": "sensor.external_temperature",
            "new_state": None,
        })
        asyncio.run(captured["listener"](event))
        self.assertIsNone(entity.current_temperature)
        self.assertFalse(entity.extra_state_attributes["ds_air_current_temperature_valid"])

    def test_native_humidity_level_is_not_exposed_as_ha_percentage(self):
        entity = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                mode=EnumControl.Mode.RELAX,
                humidity=EnumControl.Humidity.STEP2,
            )
        )
        entity._device_info.relax_mode = 1
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        sent = []
        original_control = service_module.Service.control
        try:
            service_module.Service.control = staticmethod(
                lambda aircon, status: sent.append((aircon, status))
            )
            entity.set_humidity(3)
        finally:
            service_module.Service.control = original_control

        self.assertIsNone(entity.target_humidity)
        self.assertFalse(
            entity.supported_features
            & climate_module.ClimateEntityFeature.TARGET_HUMIDITY
        )
        self.assertEqual(EnumControl.Humidity.STEP2, entity._device_info.status.humidity)
        self.assertEqual([], sent)

    def test_hvac_action_fails_closed_without_runtime_evidence(self):
        entity = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                mode=EnumControl.Mode.RELAX,
            )
        )
        self.assertIsNone(entity.hvac_action)
        self.assertEqual("cool", entity.extra_state_attributes["ds_air_mode_family"])
        entity._status_change_hook(status=AirConStatus(switch=EnumControl.Switch.OFF))
        self.assertEqual(climate_module.HVACAction.OFF, entity.hvac_action)

    def test_extended_modes_use_native_panel_presets_without_losing_exact_mode(self):
        entity = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                mode=EnumControl.Mode.RELAX,
                air_flow=EnumControl.AirFlow.STRONG,
            )
        )
        entity._device_info.cool_mode = 1
        entity._device_info.relax_mode = 1
        entity._device_info.sleep_mode = 1
        entity._device_info.auto_mode = 0

        self.assertEqual(climate_module.HVACMode.COOL, entity.hvac_mode)
        self.assertEqual("清爽", entity.preset_mode)
        self.assertEqual(["清爽", "睡眠"], entity.preset_modes)
        self.assertIn(
            climate_module.HVACMode.AUTO,
            entity.hvac_modes,
            "sleep capability needs a conservative HA compatibility projection",
        )
        self.assertEqual("comfort", entity.extra_state_attributes["ds_air_native_mode"])
        self.assertEqual("cool", entity.extra_state_attributes["ds_air_mode_family"])
        self.assertEqual("清爽", entity.extra_state_attributes["ds_air_native_mode_label"])
        self.assertEqual(6, entity.extra_state_attributes["ds_air_native_mode_code"])
        self.assertEqual(
            ["cool", "comfort", "sleep"],
            entity.extra_state_attributes["ds_air_native_supported_modes"],
        )
        self.assertTrue(
            entity.supported_features & climate_module.ClimateEntityFeature.PRESET_MODE
        )

        entity._device_info.status.mode = EnumControl.Mode.SLEEP
        entity._device_info.out_door_run_cond = EnumOutDoorRunCond.COLD
        self.assertEqual(climate_module.HVACMode.AUTO, entity.hvac_mode)
        self.assertIsNone(entity.hvac_action)
        entity._device_info.out_door_run_cond = EnumOutDoorRunCond.HEAT
        self.assertEqual(climate_module.HVACMode.AUTO, entity.hvac_mode)
        self.assertIsNone(entity.hvac_action)
        entity._device_info.out_door_run_cond = EnumOutDoorRunCond.VENT
        self.assertEqual(climate_module.HVACMode.AUTO, entity.hvac_mode)
        self.assertIsNone(entity.hvac_action)
        self.assertIn(climate_module.HVACMode.AUTO, entity.hvac_modes)
        self.assertEqual("sleep", entity.extra_state_attributes["ds_air_native_mode"])
        self.assertEqual("睡眠", entity.extra_state_attributes["ds_air_native_mode_label"])
        self.assertEqual("sleep", entity.extra_state_attributes["ds_air_mode_family"])

    def test_climate_temperature_source_reads_current_temperature_attribute(self):
        climate_state = types.SimpleNamespace(
            entity_id="climate.zhonghong_hvac_1_3",
            state="cool",
            attributes={"current_temperature": 27.5},
        )
        sensor_state = types.SimpleNamespace(
            entity_id="sensor.room_temperature",
            state="26.25",
            attributes={},
        )
        self.assertEqual(
            27.5, climate_module._temperature_value_from_state(climate_state)
        )
        self.assertEqual(
            "26.25", climate_module._temperature_value_from_state(sensor_state)
        )

    def test_zhonghong_temperature_only_fills_missing_native_temperature(self):
        entity = self._entity()
        entity.update_zhonghong_temperature(
            27.0, "zhonghong_readonly://192.168.20.7:9999/1/3",
            int(time.time() * 1000),
        )
        self.assertEqual(27.0, entity.current_temperature)
        attrs = entity.extra_state_attributes
        self.assertTrue(attrs["ds_air_current_temperature_valid"])
        self.assertEqual(
            "zhonghong_temperature_only",
            attrs["ds_air_current_temperature_source_role"],
        )
        self.assertEqual(
            "zhonghong_readonly://192.168.20.7:9999/1/3",
            attrs["ds_air_current_temperature_source"],
        )

        entity.linked_temp_entity_id = "sensor.explicit_room_temperature"
        entity.update_cur_temp("25.5")
        self.assertEqual(25.5, entity.current_temperature)
        self.assertEqual(
            "sensor.explicit_room_temperature",
            entity.extra_state_attributes["ds_air_current_temperature_source"],
        )

    def test_heat_override_is_visible_and_sends_exact_heat_mode(self):
        entity = self._entity(AirConStatus(switch=EnumControl.Switch.OFF))
        entity._device_info.heat_mode = 0
        entity._force_heat_mode = True
        sent = []
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        original_control = service_module.Service.control
        try:
            service_module.Service.control = staticmethod(
                lambda aircon, status: sent.append((aircon, status))
            )
            entity.set_hvac_mode(climate_module.HVACMode.HEAT)
        finally:
            service_module.Service.control = original_control

        self.assertIn(climate_module.HVACMode.HEAT, entity.hvac_modes)
        self.assertEqual(EnumControl.Mode.HEAT, sent[0][1].mode)
        self.assertEqual(EnumControl.Switch.ON, sent[0][1].switch)
        attrs = entity.extra_state_attributes
        self.assertFalse(attrs["ds_air_gateway_heat_capability"])
        self.assertTrue(attrs["ds_air_effective_heat_capability"])
        self.assertEqual("configured_override", attrs["ds_air_heat_capability_source"])

    def test_preset_command_sends_exact_extended_mode_without_optimistic_state(self):
        entity = self._entity(AirConStatus(
            switch=EnumControl.Switch.ON,
            mode=EnumControl.Mode.COLD,
        ))
        entity._device_info.relax_mode = 1
        sent = []
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        original_control = service_module.Service.control
        try:
            service_module.Service.control = staticmethod(
                lambda aircon, status: sent.append((aircon, status))
            )
            entity.set_preset_mode("清爽")
        finally:
            service_module.Service.control = original_control

        self.assertEqual(EnumControl.Mode.COLD, entity._device_info.status.mode)
        self.assertEqual(EnumControl.Mode.RELAX, sent[0][1].mode)
        self.assertIsNone(sent[0][1].switch)

    def test_five_speed_is_numeric_and_two_speed_stays_low_high(self):
        five = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                mode=EnumControl.Mode.COLD,
                air_flow=EnumControl.AirFlow.WEAK,
            )
        )
        five._device_info.fan_volume = EnumFanVolume.STEP_5
        five._device_info.fan_volume_auto = True
        five._device_info.fan_volume_mute = True
        self.assertEqual("2", five.fan_mode)
        self.assertEqual(
            ["1", "2", "3", "4", "5", "auto", "quiet"], five.fan_modes
        )
        self.assertEqual("five_speed", five.extra_state_attributes["ds_air_fan_profile"])
        five._device_info.status.air_flow = EnumControl.AirFlow.MUTE
        self.assertEqual("quiet", five.fan_mode)
        self.assertEqual(
            EnumControl.AirFlow.MUTE,
            climate_module.fan_mode_enum(five._device_info, "quiet"),
        )

        two = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                mode=EnumControl.Mode.COLD,
                air_flow=EnumControl.AirFlow.SUPER_WEAK,
            )
        )
        two._device_info.fan_volume = EnumFanVolume.STEP_2
        two._device_info.fan_volume_auto = True
        two._device_info.fan_volume_mute = True
        self.assertEqual("low", two.fan_mode)
        self.assertEqual(["low", "high"], two.fan_modes)
        two._device_info.status.air_flow = EnumControl.AirFlow.SUPER_STRONG
        self.assertEqual("high", two.fan_mode)
        two._device_info.status.air_flow = EnumControl.AirFlow.MIDDLE
        self.assertIsNone(two.fan_mode, "unexpected raw value must not be silently downgraded")

        three = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                mode=EnumControl.Mode.COLD,
                air_flow=EnumControl.AirFlow.WEAK,
            )
        )
        three._device_info.fan_volume = EnumFanVolume.STEP_3
        three._device_info.fan_volume_auto = False
        self.assertEqual(["1", "3", "5"], three.fan_modes)
        self.assertIsNone(three.fan_mode, "raw level 2 is not a STEP_3 capability")
        three._device_info.status.air_flow = EnumControl.AirFlow.MIDDLE
        self.assertEqual("3", three.fan_mode)

        unknown = self._entity(
            AirConStatus(
                switch=EnumControl.Switch.ON,
                mode=EnumControl.Mode.COLD,
                air_flow=EnumControl.AirFlow.MIDDLE,
            )
        )
        unknown._device_info.fan_volume = EnumFanVolume.NO
        unknown._device_info.fan_volume_auto = False
        self.assertEqual([], unknown.fan_modes)
        self.assertIsNone(unknown.fan_mode)
        self.assertFalse(
            unknown.supported_features & climate_module.ClimateEntityFeature.FAN_MODE
        )

    def test_official_modes_disable_fan_control_but_comfort_allows_it(self):
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        original_control = service_module.Service.control
        sent = []
        try:
            service_module.Service.control = staticmethod(
                lambda aircon, status: sent.append((aircon, status))
            )
            for mode in (
                EnumControl.Mode.DRY,
                EnumControl.Mode.AUTODRY,
                EnumControl.Mode.SLEEP,
                EnumControl.Mode.PREHEAT,
                EnumControl.Mode.MOREDRY,
            ):
                entity = self._entity(
                    AirConStatus(
                        switch=EnumControl.Switch.ON,
                        mode=mode,
                        air_flow=EnumControl.AirFlow.SUPER_WEAK,
                    )
                )
                entity._device_info.fan_volume = EnumFanVolume.STEP_5
                entity._schedule_fan_verification_queries = lambda: None
                self.assertFalse(
                    entity.supported_features
                    & climate_module.ClimateEntityFeature.FAN_MODE,
                    mode,
                )
                entity.set_fan_mode("5")

            self.assertEqual([], sent)

            comfort = self._entity(
                AirConStatus(
                    switch=EnumControl.Switch.ON,
                    mode=EnumControl.Mode.RELAX,
                    air_flow=EnumControl.AirFlow.SUPER_WEAK,
                )
            )
            comfort._device_info.fan_volume = EnumFanVolume.STEP_5
            comfort._schedule_fan_verification_queries = lambda: None
            self.assertTrue(
                comfort.supported_features
                & climate_module.ClimateEntityFeature.FAN_MODE
            )
            comfort.set_fan_mode("5")
        finally:
            service_module.Service.control = original_control

        self.assertEqual(1, len(sent))
        self.assertEqual(EnumControl.AirFlow.SUPER_STRONG, sent[0][1].air_flow)

    def test_native_work_mode_select_is_capability_scoped_and_not_optimistic(self):
        aircon = AirCon()
        aircon.room_id = 5
        aircon.unit_id = 0
        aircon.cool_mode = 1
        aircon.relax_mode = 1
        aircon.sleep_mode = 1
        aircon.status = AirConStatus(
            switch=EnumControl.Switch.ON,
            mode=EnumControl.Mode.RELAX,
        )
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        sent = []
        original_register = service_module.Service.register_status_hook
        original_control = service_module.Service.control
        try:
            service_module.Service.register_status_hook = staticmethod(lambda *_args: None)
            service_module.Service.control = staticmethod(
                lambda device, status: sent.append((device, status))
            )
            entity = select_module.DsAirWorkModeSelect(aircon)
            entity.schedule_update_ha_state = lambda: None
            self.assertEqual(["制冷", "清爽", "睡眠"], entity._attr_options)
            self.assertEqual("清爽", entity.current_option)
            self.assertEqual(
                "select.ds_air_5_0_native_work_mode", entity.entity_id
            )

            entity.select_option("睡眠")
        finally:
            service_module.Service.register_status_hook = original_register
            service_module.Service.control = original_control

        self.assertEqual(EnumControl.Mode.RELAX, aircon.status.mode)
        self.assertEqual(1, len(sent))
        self.assertIs(aircon, sent[0][0])
        self.assertEqual(EnumControl.Mode.SLEEP, sent[0][1].mode)
        self.assertIsNone(sent[0][1].switch)

    def test_climate_mode_and_power_commands_do_not_pollute_shared_physical_state(self):
        aircon = AirCon()
        aircon.room_id = 5
        aircon.unit_id = 0
        aircon.cool_mode = 1
        aircon.relax_mode = 1
        aircon.status = AirConStatus(
            switch=EnumControl.Switch.ON,
            mode=EnumControl.Mode.RELAX,
        )
        climate = self._entity(aircon.status)
        climate._device_info = aircon
        power_generation = climate._power_physical_generation
        mode_generation = climate._mode_physical_generation
        service_module = importlib.import_module(
            "custom_components.ds_air.ds_air_service.service"
        )
        sent = []
        original_register = service_module.Service.register_status_hook
        original_control = service_module.Service.control
        try:
            service_module.Service.register_status_hook = staticmethod(lambda *_args: None)
            service_module.Service.control = staticmethod(
                lambda device, status: sent.append((device, status))
            )
            exact = select_module.DsAirWorkModeSelect(aircon)
            exact.schedule_update_ha_state = lambda: None

            climate.set_hvac_mode(climate_module.HVACMode.COOL)
            self.assertEqual(EnumControl.Mode.RELAX, aircon.status.mode)
            self.assertEqual("清爽", exact.current_option)
            self.assertEqual("comfort", climate.extra_state_attributes["ds_air_native_mode"])

            climate.turn_off()
            self.assertEqual(EnumControl.Switch.ON, aircon.status.switch)
            self.assertEqual("清爽", exact.current_option)
            self.assertEqual(power_generation, climate._power_physical_generation)
            self.assertEqual(mode_generation, climate._mode_physical_generation)
        finally:
            service_module.Service.register_status_hook = original_register
            service_module.Service.control = original_control

        self.assertEqual(2, len(sent))
        self.assertEqual(EnumControl.Mode.COLD, sent[0][1].mode)
        self.assertEqual(EnumControl.Switch.ON, sent[0][1].switch)
        self.assertEqual(EnumControl.Switch.OFF, sent[1][1].switch)


if __name__ == "__main__":
    unittest.main()

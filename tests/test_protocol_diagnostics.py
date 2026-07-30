import struct
import importlib
import asyncio
import sys
import time
import types
import unittest
from enum import Enum, IntFlag
from pathlib import Path
from threading import RLock
from unittest.mock import patch


def _install_homeassistant_stubs():
    """Provide the constants imported by protocol modules."""
    homeassistant = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = sys.modules.setdefault(
        "homeassistant.components", types.ModuleType("homeassistant.components")
    )
    climate = sys.modules.setdefault(
        "homeassistant.components.climate", types.ModuleType("homeassistant.components.climate")
    )
    climate_const = sys.modules.setdefault(
        "homeassistant.components.climate.const",
        types.ModuleType("homeassistant.components.climate.const"),
    )

    if not hasattr(climate, "HVACMode"):
        class HVACMode(str, Enum):
            AUTO = "auto"
            COOL = "cool"
            DRY = "dry"
            FAN_ONLY = "fan_only"
            HEAT = "heat"

        climate.HVACMode = HVACMode

    if not hasattr(climate, "HVACAction"):
        class HVACAction(str, Enum):
            COOLING = "cooling"
            DRYING = "drying"
            FAN = "fan"
            HEATING = "heating"
            PREHEATING = "preheating"

        climate.HVACAction = HVACAction

    climate_const.FAN_AUTO = "auto"
    climate_const.FAN_LOW = "low"
    climate_const.FAN_MEDIUM = "medium"
    climate_const.FAN_HIGH = "high"
    homeassistant.components = components
    components.climate = climate


_install_homeassistant_stubs()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "custom_components" / "ds_air"))

from ds_air_service.ctrl_enum import EnumControl, EnumDevice
from ds_air_service.dao import AirCon, Room, Ventilation, VentilationStatus
from ds_air_service.decoder import (
    AirConInletTempAndHumidityQueryResult,
    AirConCleaningControlResult,
    AirConCleaningQueryResult,
    DaikinCareExponentFeatureResult,
    ErrCodeResult,
    FilterCleanSignResult,
    FilterServiceLifeResult,
    GatewaySignalResult,
    GetGWInfoResult,
    HeartbeatResult,
    VentilationQueryCompositeSituationResult,
    VentilationQueryStatusResult,
    VentilationCapabilityQueryResult,
)
from ds_air_service.param import (
    AirConCleaningControlParam,
    AirConInletTempAndHumidityQueryParam,
    DaikinCareExponentQueryParam,
    FilterCleanSignResetParam,
    FilterServiceLifeQueryParam,
    GatewaySignalQueryParam,
    OfficialSystemCmd,
    Param,
)
from ds_air_service.service import Service, SocketClient, _log_received_frame
import ds_air_service.service as service_module


def _sized(value: bytes) -> bytes:
    return bytes((len(value),)) + value


def _load_sensor_module():
    """Install the narrow HA sensor surface and import the real platform."""
    sensor_component = sys.modules.setdefault(
        "homeassistant.components.sensor",
        types.ModuleType("homeassistant.components.sensor"),
    )

    class SensorEntity:
        pass

    class SensorStateClass:
        MEASUREMENT = "measurement"

    class SensorDeviceClass:
        TEMPERATURE = "temperature"
        HUMIDITY = "humidity"

    sensor_component.SensorEntity = SensorEntity
    sensor_component.SensorStateClass = SensorStateClass
    sensor_component.SensorDeviceClass = SensorDeviceClass
    sys.modules["homeassistant.components"].sensor = sensor_component

    ha_const = sys.modules.setdefault(
        "homeassistant.const", types.ModuleType("homeassistant.const")
    )
    ha_const.PERCENTAGE = "%"
    ha_const.UnitOfTemperature = types.SimpleNamespace(CELSIUS="°C")

    helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    helper_entity = sys.modules.setdefault(
        "homeassistant.helpers.entity", types.ModuleType("homeassistant.helpers.entity")
    )
    helper_entity.DeviceInfo = dict
    helpers.entity = helper_entity

    custom_components = sys.modules.setdefault(
        "custom_components", types.ModuleType("custom_components")
    )
    custom_components.__path__ = [str(PROJECT_ROOT / "custom_components")]
    package = sys.modules.setdefault(
        "custom_components.ds_air", types.ModuleType("custom_components.ds_air")
    )
    package.__path__ = [str(PROJECT_ROOT / "custom_components" / "ds_air")]
    package_const = sys.modules.setdefault(
        "custom_components.ds_air.const", types.ModuleType("custom_components.ds_air.const")
    )
    package_const.DOMAIN = "ds_air"
    package_const.SENSOR_TYPES = {}
    return importlib.import_module("custom_components.ds_air.sensor")


class SocketReconnectTest(unittest.TestCase):
    def test_orderly_eof_closes_old_socket_clears_buffer_and_reconnects(self):
        class FakeSocket:
            def __init__(self, payload=b""):
                self.payload = payload
                self.closed = False
                self.sent = []

            def recv(self, _size):
                return self.payload

            def sendall(self, frame):
                self.sent.append(frame)

            def close(self):
                self.closed = True

        old_socket = FakeSocket(b"")
        replacement = FakeSocket()
        client = SocketClient.__new__(SocketClient)
        client._host = "127.0.0.1"
        client._port = 8008
        client._ready = True
        client._locker = RLock()
        client._s = old_socket
        client._recv_buffer = b"partial-old-session-frame"
        attempts = []

        def connect_replacement():
            attempts.append(True)
            client._s = replacement
            client._recv_buffer = b""
            return True

        client.do_connect = connect_replacement

        self.assertEqual([], client.recv())
        self.assertTrue(old_socket.closed)
        self.assertIs(replacement, client._s)
        self.assertEqual(b"", client._recv_buffer)
        self.assertEqual([True], attempts)
        self.assertTrue(replacement.sent)
        self.assertEqual(bytes.fromhex("00 a0"), replacement.sent[0][17:19])


class CleaningProtocolTest(unittest.TestCase):
    def test_cmd36_matches_official_room_scoped_golden_bytes(self):
        room7_unit0 = AirCon()
        room7_unit0.room_id = 7
        room7_unit0.unit_id = 0
        room7_unit1 = AirCon()
        room7_unit1.room_id = 7
        room7_unit1.unit_id = 1
        room9 = AirCon()
        room9.room_id = 9
        room9.unit_id = 3

        param = AirConCleaningControlParam(
            [room7_unit0, room7_unit1, room9], switch_status=1
        )
        self.assertTrue(param.has_result)
        self.assertEqual(
            bytes.fromhex(
                "02 "
                "00 07 00 02 04 01 01 01 00 00 "
                "01 09 00 02 04 01 01 01 00 00"
            ),
            param.to_string()[19:-1],
        )

    @patch.object(Service, "send_msg")
    def test_cmd36_queries_authoritative_state_only_after_success(self, send_msg):
        success = AirConCleaningControlResult(1, EnumDevice.SYSTEM)
        success.load_bytes(b"\x00\x00")
        success.do()
        self.assertEqual(1, send_msg.call_count)

        send_msg.reset_mock()
        failure = AirConCleaningControlResult(2, EnumDevice.SYSTEM)
        failure.load_bytes(b"\x01\x09")
        failure.do()
        send_msg.assert_not_called()

    def test_cmd35_maps_confirmed_tlvs_without_fabricating_percent(self):
        payload = bytes(
            (
                1,  # record count
                7, 1, 0,  # room + two protocol header bytes
                4, 1, 1,
                5, 1, 0,
                6, 1, 2,
                7, 2, 0x34, 0x12,
                8, 2, 3, 45,
                14, 1, 1,
                15, 1, 2,
                16, 1, 9,
                17, 1, 8,
                18, 1, 0x80,
                19, 2, 0x78, 0x56,
                20, 1, 7,
                0,
            )
        )

        result = AirConCleaningQueryResult(1, EnumDevice.SYSTEM)
        result.load_bytes(payload)
        item = result.items[0]

        self.assertEqual(7, item["room"])
        self.assertEqual("0100", item["protocol_header_raw"])
        self.assertEqual(1, item["heat_exchange_cleaning_capability"])
        self.assertEqual(0, item["heat_exchange_cleaning_can_join"])
        self.assertEqual(2, item["heat_exchange_cleaning_work_state"])
        self.assertEqual(0x1234, item["heat_exchange_cleaning_phase_duration"])
        self.assertEqual(3, item["heat_exchange_cleaning_v_sleep_value_1"])
        self.assertEqual(45, item["heat_exchange_cleaning_v_sleep_value_2"])
        self.assertEqual(1, item["heat_exchange_cleaning_finish"])
        self.assertEqual(2, item["heat_exchange_cleaning_outdoor_status"])
        self.assertEqual(1, item["vam_cleaning_tlv_18"])
        self.assertEqual(0x5678, item["vam_cleaning_tlv_19"])
        self.assertEqual("unmapped", item["vam_cleaning_semantic_status"])
        self.assertEqual("complete", item["heat_exchange_cleaning_parse_status"])
        self.assertNotIn("heat_exchange_cleaning_percent", item)
        self.assertNotIn("heat_exchange_cleaning_status", item)

    def test_cmd35_wrong_length_stays_raw_and_unknown(self):
        result = AirConCleaningQueryResult(1, EnumDevice.SYSTEM)
        result.load_bytes(bytes((1, 2, 1, 0, 7, 1, 99, 0)))
        item = result.items[0]

        self.assertNotIn("heat_exchange_cleaning_phase_duration", item)
        self.assertEqual(
            [{"key": 7, "length": 1, "raw": "63"}],
            item["heat_exchange_cleaning_raw_tlvs"],
        )

    def test_cmd35_truncation_keeps_evidence_but_does_not_publish_partial_state(self):
        result = AirConCleaningQueryResult(1, EnumDevice.SYSTEM)
        result.load_bytes(bytes((1, 2, 1, 0, 6, 1, 3, 7, 2, 0x34)))
        item = result.items[0]

        self.assertEqual("truncated", item["heat_exchange_cleaning_parse_status"])
        self.assertNotIn("heat_exchange_cleaning_work_state", item)
        self.assertNotIn("heat_exchange_cleaning_phase_duration", item)
        self.assertEqual(2, len(item["heat_exchange_cleaning_raw_tlvs"]))

    def test_service_applies_room_level_cleaning_record_without_unit_guess(self):
        aircon0 = AirCon()
        aircon0.room_id = 7
        aircon0.unit_id = 0
        aircon1 = AirCon()
        aircon1.room_id = 7
        aircon1.unit_id = 1

        old_values = (Service._aircons, Service._new_aircons, Service._bathrooms, Service._ready)
        Service._aircons = [aircon0, aircon1]
        Service._new_aircons = []
        Service._bathrooms = []
        Service._ready = False
        try:
            Service.set_cleaning_info(
                [{
                    "room": 7,
                    "heat_exchange_cleaning_capability": 1,
                    "heat_exchange_cleaning_work_state": 0,
                    "source_timestamp": 123.0,
                }]
            )
        finally:
            Service._aircons, Service._new_aircons, Service._bathrooms, Service._ready = old_values

        for aircon in (aircon0, aircon1):
            self.assertTrue(aircon.heat_exchange_cleaning_allow)
            self.assertEqual(0, aircon.heat_exchange_cleaning_work_state)
            self.assertEqual(123.0, aircon.heat_exchange_cleaning_source_timestamp)

    def test_vam_tlvs_are_stored_as_unmapped_diagnostics_not_aircon_fields(self):
        aircon = AirCon()
        aircon.room_id = 7
        vent = Ventilation()
        vent.room_id = 7
        old_values = (
            Service._aircons,
            Service._new_aircons,
            Service._bathrooms,
            Service._ventilations,
            Service._gateway_diagnostics,
            Service._ready,
        )
        from ds_air_service.dao import GatewayDiagnostics
        Service._aircons = [aircon]
        Service._new_aircons = []
        Service._bathrooms = []
        Service._ventilations = [vent]
        Service._gateway_diagnostics = GatewayDiagnostics()
        Service._ready = False
        try:
            Service.set_cleaning_info(
                [{
                    "room": 7,
                    "vam_cleaning_tlv_16": 2,
                    "vam_cleaning_tlv_19": 300,
                    "vam_cleaning_semantic_status": "unmapped",
                    "heat_exchange_cleaning_raw_tlvs": [
                        {"key": 16, "length": 1, "raw": "02"},
                        {"key": 19, "length": 2, "raw": "2c01"},
                    ],
                    "heat_exchange_cleaning_parse_status": "complete",
                    "source_timestamp": 321.0,
                }]
            )
            record = Service._gateway_diagnostics.vam_cleaning_unmapped["7"]
        finally:
            (
                Service._aircons,
                Service._new_aircons,
                Service._bathrooms,
                Service._ventilations,
                Service._gateway_diagnostics,
                Service._ready,
            ) = old_values

        self.assertFalse(hasattr(aircon, "vam_cleaning_tlv_16"))
        self.assertEqual(2, vent.vam_cleaning_tlv_16)
        self.assertEqual(300, vent.vam_cleaning_tlv_19)
        self.assertEqual("unmapped", vent.vam_cleaning_semantic_status)
        self.assertEqual("unmapped", record["semantic_status"])
        self.assertEqual(321.0, record["source_timestamp"])

    def test_can_join_gates_cleaning_selection(self):
        aircon = AirCon()
        aircon.heat_exchange_cleaning_allow = True
        aircon.heat_exchange_cleaning_work_state = 0
        old_selected = Service._cleaning_selected
        Service._cleaning_selected = set()
        try:
            aircon.heat_exchange_cleaning_can_join = 0
            Service.select_heat_exchange_cleaning(aircon, True)
            self.assertTrue(Service.is_heat_exchange_cleaning_selected(aircon))

            aircon.heat_exchange_cleaning_can_join = 1
            Service.select_heat_exchange_cleaning(aircon, True)
            self.assertFalse(Service.is_heat_exchange_cleaning_selected(aircon))

            aircon.heat_exchange_cleaning_can_join = 0
            aircon.heat_exchange_cleaning_work_state = 2
            Service.select_heat_exchange_cleaning(aircon, True)
            self.assertFalse(Service.is_heat_exchange_cleaning_selected(aircon))
        finally:
            Service._cleaning_selected = old_selected

    def test_cleaning_entity_unknown_is_none_not_fake_zero_percent(self):
        sensor_component = sys.modules.setdefault(
            "homeassistant.components.sensor",
            types.ModuleType("homeassistant.components.sensor"),
        )

        class SensorEntity:
            pass

        class SensorStateClass:
            MEASUREMENT = "measurement"

        class SensorDeviceClass:
            TEMPERATURE = "temperature"
            HUMIDITY = "humidity"

        sensor_component.SensorEntity = SensorEntity
        sensor_component.SensorStateClass = SensorStateClass
        sensor_component.SensorDeviceClass = SensorDeviceClass
        sys.modules["homeassistant.components"].sensor = sensor_component

        ha_const = sys.modules.setdefault(
            "homeassistant.const", types.ModuleType("homeassistant.const")
        )
        ha_const.PERCENTAGE = "%"
        ha_const.UnitOfTemperature = types.SimpleNamespace(CELSIUS="°C")

        helpers = sys.modules.setdefault(
            "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
        )
        helper_entity = sys.modules.setdefault(
            "homeassistant.helpers.entity", types.ModuleType("homeassistant.helpers.entity")
        )
        helper_entity.DeviceInfo = dict
        helpers.entity = helper_entity

        custom_components = sys.modules.setdefault(
            "custom_components", types.ModuleType("custom_components")
        )
        custom_components.__path__ = [str(PROJECT_ROOT / "custom_components")]
        package = sys.modules.setdefault(
            "custom_components.ds_air", types.ModuleType("custom_components.ds_air")
        )
        package.__path__ = [str(PROJECT_ROOT / "custom_components" / "ds_air")]
        package_const = sys.modules.setdefault(
            "custom_components.ds_air.const", types.ModuleType("custom_components.ds_air.const")
        )
        package_const.DOMAIN = "ds_air"
        package_const.SENSOR_TYPES = {}

        sensor_module = importlib.import_module("custom_components.ds_air.sensor")
        package_dao = importlib.import_module(
            "custom_components.ds_air.ds_air_service.dao"
        )
        aircon = package_dao.AirCon()
        entity = sensor_module.DsAirHeatExchangeCleaningStatusSensor.__new__(
            sensor_module.DsAirHeatExchangeCleaningStatusSensor
        )
        entity._device_info = aircon

        self.assertIsNone(entity.native_value)
        aircon.heat_exchange_cleaning_work_state = 0
        self.assertEqual(0, entity.native_value)
        self.assertFalse(hasattr(entity, "_attr_native_unit_of_measurement"))


class OfficialInletProtocolTest(unittest.TestCase):
    def test_startup_diagnostics_params_preserve_system_target(self):
        previous_count = Param.cnt
        Param.cnt = 0
        try:
            params = [
                GatewaySignalQueryParam(),
                FilterServiceLifeQueryParam(),
                DaikinCareExponentQueryParam(),
                AirConInletTempAndHumidityQueryParam(),
            ]
            frames = [param.to_string() for param in params]
        finally:
            Param.cnt = previous_count

        for param in params:
            self.assertEqual(EnumDevice.SYSTEM, param.target)
            self.assertTrue(param.has_result)
        self.assertEqual(bytes.fromhex("ea 00"), frames[0][17:19])
        self.assertEqual(b"\x00", frames[0][19:-1])
        self.assertEqual(bytes.fromhex("0a 00"), frames[1][17:19])
        self.assertEqual(bytes.fromhex("dc 00"), frames[2][17:19])
        self.assertEqual(bytes.fromhex("f3 00"), frames[3][17:19])

    def test_cmd243_request_matches_official_app_golden_bytes(self):
        previous_count = Param.cnt
        Param.cnt = 0
        try:
            param = AirConInletTempAndHumidityQueryParam()
            frame = param.to_string()
        finally:
            Param.cnt = previous_count

        self.assertEqual(
            OfficialSystemCmd.AIR_CON_INLET_TEMP_AND_HUMIDITY_INFO_QUERY,
            param.cmd_type,
        )
        self.assertTrue(param.has_result)
        self.assertEqual(
            bytes.fromhex(
                "02 11 00 0d 00 00 00 01 00 00 00 "
                "00 00 00 00 00 01 f3 00 ff 03"
            ),
            frame,
        )
        self.assertEqual(0, frame[5])
        self.assertEqual(bytes.fromhex("f3 00"), frame[17:19])
        self.assertEqual(b"\xff", frame[19:-1])
        self.assertEqual(17, struct.unpack("<H", frame[1:3])[0])

    @patch.object(Service, "set_aircon_inlet_observations")
    def test_cmd243_decodes_signed_tenths_and_preserves_unknown_tlvs(self, set_values):
        payload = (
            bytes((2, 5, 1, 2))
            + struct.pack("<h", 267)
            + bytes((2, 2))
            + struct.pack("<h", 615)
            + bytes((9, 1, 0xA5, 0, 7, 1, 2))
            + struct.pack("<h", -25)
            + bytes((0,))
        )
        result = AirConInletTempAndHumidityQueryResult(1, EnumDevice.SYSTEM)
        result.load_bytes(payload)

        self.assertEqual(2, len(result.items))
        self.assertEqual(26.7, result.items[0]["inlet_temperature_c"])
        self.assertEqual(61.5, result.items[0]["inlet_humidity_percent"])
        self.assertEqual("valid", result.items[0]["inlet_temperature_quality"])
        self.assertEqual("valid", result.items[0]["inlet_humidity_quality"])
        self.assertEqual(-2.5, result.items[1]["inlet_temperature_c"])
        self.assertNotIn("inlet_humidity_percent", result.items[1])
        self.assertEqual("valid", result.items[1]["inlet_temperature_quality"])
        self.assertEqual("missing", result.items[1]["inlet_humidity_quality"])
        self.assertEqual(
            {"key": 9, "length": 1, "raw": "a5"},
            result.items[0]["inlet_raw_tlvs"][2],
        )

        result.do()
        self.assertEqual(2, len(set_values.call_args.args[0]))

    def test_cmd243_keeps_out_of_range_raw_values_but_marks_quality(self):
        payload = (
            bytes((1, 5, 1, 2))
            + struct.pack("<h", -401)
            + bytes((2, 2))
            + struct.pack("<h", 1001)
            + bytes((0,))
        )
        result = AirConInletTempAndHumidityQueryResult(1, EnumDevice.SYSTEM)
        result.load_bytes(payload)

        self.assertEqual(-40.1, result.items[0]["inlet_temperature_c"])
        self.assertEqual(100.1, result.items[0]["inlet_humidity_percent"])
        self.assertEqual(
            "out_of_range", result.items[0]["inlet_temperature_quality"]
        )
        self.assertEqual(
            "out_of_range", result.items[0]["inlet_humidity_quality"]
        )

    @patch.object(Service, "set_aircon_inlet_observations")
    def test_cmd243_truncation_never_publishes_partial_value(self, set_values):
        result = AirConInletTempAndHumidityQueryResult(1, EnumDevice.SYSTEM)
        result.load_bytes(bytes((1, 5, 1, 2, 0x10)))

        self.assertEqual("truncated", result.items[0]["inlet_parse_status"])
        self.assertNotIn("inlet_temperature_c", result.items[0])
        self.assertNotIn("inlet_temperature_quality", result.items[0])
        result.do()
        set_values.assert_not_called()

    def test_service_keeps_cmd243_room_scope_without_unit_duplication(self):
        room5_unit0 = AirCon()
        room5_unit0.room_id = 5
        room5_unit1 = AirCon()
        room5_unit1.room_id = 5
        room5_unit1.unit_id = 1
        room6 = AirCon()
        room6.room_id = 6
        old_values = (
            Service._aircons,
            Service._new_aircons,
            Service._bathrooms,
            Service._ready,
        )
        Service._aircons = [room5_unit0, room5_unit1, room6]
        Service._new_aircons = []
        Service._bathrooms = []
        Service._ready = False
        try:
            Service.set_aircon_inlet_observations(
                [{
                    "room": 5,
                    "inlet_temperature_c": 24.6,
                    "inlet_humidity_percent": 58.2,
                    "inlet_temperature_quality": "valid",
                    "inlet_humidity_quality": "valid",
                    "inlet_parse_status": "complete",
                    "inlet_raw_tlvs": [],
                    "source_timestamp": 123.0,
                }]
            )
        finally:
            (
                Service._aircons,
                Service._new_aircons,
                Service._bathrooms,
                Service._ready,
            ) = old_values

        self.assertEqual(24.6, room5_unit0.inlet_temperature_c)
        self.assertEqual(58.2, room5_unit0.inlet_humidity_percent)
        self.assertEqual(123.0, room5_unit0.inlet_source_timestamp)
        self.assertIsNotNone(room5_unit0.inlet_source_monotonic)
        self.assertEqual("valid", room5_unit0.inlet_temperature_quality)
        self.assertEqual("valid", room5_unit0.inlet_humidity_quality)
        self.assertIsNone(room5_unit1.inlet_temperature_c)
        self.assertIsNone(room5_unit1.inlet_humidity_percent)
        self.assertIsNone(room6.inlet_temperature_c)

    def test_room_sensor_has_ttl_quality_and_no_per_unit_identity(self):
        sensor_module = _load_sensor_module()
        package_dao = importlib.import_module(
            "custom_components.ds_air.ds_air_service.dao"
        )
        unit0 = package_dao.AirCon()
        unit0.room_id = 5
        unit0.unit_id = 0
        unit0.alias = "客厅"
        unit0.inlet_temperature_c = 24.6
        unit0.inlet_source_timestamp = time.time()
        unit0.inlet_source_monotonic = time.monotonic()
        unit0.inlet_temperature_quality = "valid"
        unit0.inlet_parse_status = "complete"
        unit1 = package_dao.AirCon()
        unit1.room_id = 5
        unit1.unit_id = 1
        unit1.alias = "客厅1"

        with patch.object(sensor_module.Service, "register_status_hook"):
            entity = sensor_module.DsAirInletSensor(
                [unit0, unit1], "temperature"
            )

        self.assertEqual("daikin_room_5_inlet_temperature", entity._attr_unique_id)
        self.assertEqual("sensor.ds_air_room_5_inlet_temperature", entity.entity_id)
        self.assertTrue(entity.should_poll)
        self.assertTrue(entity.available)
        self.assertEqual("valid", entity.quality)
        attrs = entity.extra_state_attributes
        self.assertEqual("room", attrs["scope"])
        self.assertNotIn("unit_id", attrs)
        self.assertEqual([0, 1], attrs["room_unit_ids"])
        self.assertEqual(
            "one_room_multiple_units_shared_observation",
            attrs["scope_relationship"],
        )
        self.assertFalse(attrs["stale"])

        unit0.inlet_source_monotonic -= (
            sensor_module.INLET_OBSERVATION_TTL_SECONDS + 1
        )
        self.assertTrue(entity.stale)
        self.assertEqual("stale", entity.quality)
        self.assertFalse(entity.available)
        self.assertGreater(entity.extra_state_attributes["age_seconds"], 180)

        unit0.inlet_source_monotonic = time.monotonic()
        unit0.inlet_temperature_quality = "out_of_range"
        self.assertEqual("out_of_range", entity.quality)
        self.assertFalse(entity.available)
        self.assertEqual(24.6, entity.extra_state_attributes["raw_value"])

    def test_setup_creates_one_cmd243_entity_pair_per_room(self):
        sensor_module = _load_sensor_module()
        package_dao = importlib.import_module(
            "custom_components.ds_air.ds_air_service.dao"
        )
        unit0 = package_dao.AirCon()
        unit0.room_id = 5
        unit0.unit_id = 0
        unit0.alias = "客厅"
        unit1 = package_dao.AirCon()
        unit1.room_id = 5
        unit1.unit_id = 1
        unit1.alias = "客厅1"
        added = []
        entry = types.SimpleNamespace(data={})

        with patch.object(
            sensor_module.Service, "get_aircons", return_value=[unit0, unit1]
        ), patch.object(
            sensor_module.Service, "get_sensors", return_value=[]
        ), patch.object(
            sensor_module.Service,
            "get_gateway_diagnostics",
            return_value=package_dao.GatewayDiagnostics(),
        ), patch.object(
            sensor_module.Service, "register_status_hook"
        ), patch.object(
            sensor_module.Service, "register_diagnostics_hook"
        ):
            asyncio.run(
                sensor_module.async_setup_entry(
                    None, entry, lambda entities: added.extend(entities)
                )
            )

        inlet_entities = [
            item
            for item in added
            if isinstance(item, sensor_module.DsAirInletSensor)
        ]
        self.assertEqual(2, len(inlet_entities))
        self.assertEqual(
            {
                "daikin_room_5_inlet_temperature",
                "daikin_room_5_inlet_humidity",
            },
            {item._attr_unique_id for item in inlet_entities},
        )


class GatewayProtocolTest(unittest.TestCase):
    @patch.object(Service, "set_error_info")
    def test_cmd6_parses_lengths_and_preserves_raw_error(self, set_error_info):
        payload = (
            struct.pack("<iBB", EnumDevice.AIRCON.value[1], 7, 99)
            + _sized(bytes((2,)))
            + _sized(b"source")
            + _sized(b"AF")
        )
        result = ErrCodeResult(1, EnumDevice.SYSTEM)
        result.load_bytes(payload)

        self.assertTrue(result.valid)
        self.assertEqual(EnumDevice.AIRCON, result.device)
        self.assertEqual("AF", result.code)
        self.assertEqual("00", result.normalized_code)
        self.assertEqual(7, result.room)
        self.assertEqual(2, result.unit)
        result.do()
        self.assertEqual("AF", set_error_info.call_args.kwargs["code_raw"])

    def test_cmd6_unknown_device_is_safe(self):
        payload = struct.pack("<iBB", 999, 3, 0) + _sized(b"") + _sized(b"") + _sized(b"E1")
        result = ErrCodeResult(1, EnumDevice.SYSTEM)
        result.load_bytes(payload)

        self.assertTrue(result.valid)
        self.assertIsNone(result.device)
        self.assertEqual(999, result.device_id)
        self.assertEqual("E1", result.code)

    @patch.object(Service, "set_filter_clean_sign")
    def test_cmd9_decodes_local_filter_clean_notification(self, set_filter):
        payload = struct.pack("<iBBB", EnumDevice.AIRCON.value[1], 7, 0, 4)
        result = FilterCleanSignResult(1, EnumDevice.SYSTEM)
        result.load_bytes(payload)

        self.assertTrue(result.valid)
        self.assertEqual(EnumDevice.AIRCON, result.device)
        self.assertEqual(7, result.room)
        self.assertEqual(4, result.status)
        result.do()
        self.assertEqual(4, set_filter.call_args.kwargs["status"])

    def test_cmd21_filter_reset_matches_official_local_dto(self):
        aircon = AirCon()
        aircon.room_id = 7
        param = FilterCleanSignResetParam(aircon)
        frame = param.to_string()

        self.assertEqual(21, struct.unpack("<H", frame[17:19])[0])
        self.assertEqual(bytes.fromhex("12000000070007"), frame[19:-1])

    @patch.object(Service, "set_gateway_info")
    def test_cmd80_exposes_only_non_sensitive_fields(self, set_gateway_info):
        payload = (
            _sized(b"03.19.00")
            + bytes((1,))
            + bytes.fromhex("001122334455")
            + _sized(b"192.168.10.17")
            + _sized(b"255.255.255.0")
            + _sized(b"192.168.10.1")
            + _sized(b"192.168.10.2")
            + _sized(b"192.168.10.3")
            + _sized(bytes((0xEA, 0x07, 7, 17, 12, 34, 56)))
            + _sized("区域".encode())
            + _sized(b"13800000000")
            + _sized("经销商".encode())
            + _sized(b"WIFI-1.2")
        )
        result = GetGWInfoResult(1, EnumDevice.SYSTEM)
        result.load_bytes(payload)

        self.assertTrue(result.valid)
        self.assertEqual("03.19.00", result.gateway_version)
        self.assertEqual("WIFI-1.2", result.wifi_version)
        self.assertEqual("2026-07-17 12:34:56", result.gateway_time)
        for sensitive_name in ("mac", "ip", "dns1", "distributor"):
            self.assertFalse(hasattr(result, sensitive_name))
        result.do()
        self.assertEqual(
            {"gateway_version", "wifi_version", "gateway_time", "source_timestamp"},
            set_gateway_info.call_args.kwargs.keys(),
        )

    @patch.object(Service, "set_gateway_signal")
    def test_cmd234_decodes_real_and_sentinel_values(self, set_gateway_signal):
        result = GatewaySignalResult(1, EnumDevice.SYSTEM)
        result.load_bytes(bytes.fromhex("D6 05 7B 00"))
        self.assertTrue(result.valid)
        self.assertEqual(-42, result.signal_strength)
        self.assertEqual(5, result.ping_success_count)
        self.assertEqual(123, result.network_delay)
        result.do()
        self.assertEqual(-42, set_gateway_signal.call_args.kwargs["signal_strength"])

        sentinel = GatewaySignalResult(2, EnumDevice.SYSTEM)
        sentinel.load_bytes(bytes.fromhex("7F 00 FF 7F"))
        self.assertTrue(sentinel.valid)
        self.assertIsNone(sentinel.signal_strength)
        self.assertEqual(0, sentinel.ping_success_count)
        self.assertIsNone(sentinel.network_delay)

        truncated = GatewaySignalResult(3, EnumDevice.SYSTEM)
        truncated.load_bytes(b"\x01\x02\x03")
        self.assertFalse(truncated.valid)


class FeatureDetectionTest(unittest.TestCase):
    @patch.object(Service, "set_filter_service_life")
    @patch.object(Service, "set_feature_support")
    def test_cmd10_decodes_only_complete_vam_filter_records(
            self, set_support, set_filter_service_life):
        empty = FilterServiceLifeResult(1, EnumDevice.SYSTEM)
        empty.load_bytes(b"\x00")
        self.assertTrue(empty.valid)
        self.assertFalse(empty.has_data)
        empty.do()
        set_support.assert_called_once()
        set_filter_service_life.assert_called_once_with(
            [], source_timestamp=empty.source_timestamp
        )

        truncated = FilterServiceLifeResult(2, EnumDevice.SYSTEM)
        truncated.load_bytes(bytes.fromhex("01 00 07"))
        self.assertFalse(truncated.valid)

        record = FilterServiceLifeResult(3, EnumDevice.SYSTEM)
        record.load_bytes(bytes.fromhex("01 AA 07 BB 00"))
        self.assertTrue(record.valid)
        self.assertTrue(record.has_data)
        self.assertEqual(7, record.items[0]["room"])
        self.assertEqual(0, record.items[0]["used_percent"])

        sentinel = FilterServiceLifeResult(4, EnumDevice.SYSTEM)
        sentinel.load_bytes(bytes.fromhex("01 00 07 00 FF"))
        self.assertTrue(sentinel.valid)
        self.assertIsNone(sentinel.items[0]["used_percent"])

    @patch.object(Service, "set_feature_support")
    def test_cmd220_is_feature_detection_only(self, set_support):
        empty = DaikinCareExponentFeatureResult(1, EnumDevice.SYSTEM)
        empty.load_bytes(bytes.fromhex("00 00 00"))
        self.assertTrue(empty.valid)
        self.assertFalse(empty.has_data)
        empty.do()
        set_support.assert_called_once()

        complete = DaikinCareExponentFeatureResult(2, EnumDevice.SYSTEM)
        complete.load_bytes(
            bytes.fromhex(
                "01 01 01 07 12 34 56 78 01 "
                "41 01 02 48 02 AA BB 4A 01 02 00"
            )
        )
        self.assertTrue(complete.valid)
        self.assertTrue(complete.has_data)

        truncated = DaikinCareExponentFeatureResult(3, EnumDevice.SYSTEM)
        truncated.load_bytes(bytes.fromhex("01 01 01 07 12 34 56 78 01 41 02 01"))
        self.assertFalse(truncated.valid)


class VentilationPreservationTest(unittest.TestCase):
    def test_room_does_not_create_a_phantom_vam(self):
        room = Room()
        self.assertIsNone(room.ventilation)
        self.assertEqual([], room.ventilations)

    def test_vam_status_decoder_preserves_unknown_fields(self):
        vent = Ventilation()
        self.assertIsInstance(vent.status, VentilationStatus)

        result = VentilationQueryStatusResult(1, EnumDevice.VENTILATION)
        result.load_bytes(
            bytes((7, 0, EnumControl.Type.SWITCH, EnumControl.Switch.ON))
        )
        self.assertEqual(EnumControl.Switch.ON, result._status.switch)
        self.assertIsNone(result._status.mode)
        self.assertIsNone(result._status.air_flow)

    def test_initial_vam_capability_is_not_dropped_before_service_ready(self):
        vent = Ventilation()
        vent.room_id = 7
        vent.unit_id = 0
        old_values = (Service._ventilations, Service._ready)
        Service._ventilations = [vent]
        Service._ready = False
        try:
            result = VentilationCapabilityQueryResult(1, EnumDevice.VENTILATION)
            result.load_bytes(bytes((1, 7, 1, 0, 0xA5)))
            result.do()
        finally:
            Service._ventilations, Service._ready = old_values

        self.assertEqual(0xA5, vent.capability)

    def test_same_coordinates_keep_standard_and_small_vam_status_isolated(self):
        standard = Ventilation()
        standard.room_id = 7
        standard.unit_id = 0
        small = Ventilation()
        small.room_id = 7
        small.unit_id = 0
        small.is_small_vam = True

        old_values = (Service._ventilations, Service._ready)
        Service._ventilations = [standard, small]
        Service._ready = False
        try:
            Service.set_ventilation_status(
                EnumDevice.SMALL_VAM,
                7,
                0,
                VentilationStatus(switch=EnumControl.Switch.ON),
            )
        finally:
            Service._ventilations, Service._ready = old_values

        self.assertIsNone(standard.status.switch)
        self.assertEqual(EnumControl.Switch.ON, small.status.switch)

    def test_cmd52_is_correctly_framed_but_evidence_only(self):
        result = VentilationQueryCompositeSituationResult(
            1, EnumDevice.SMALL_VAM
        )
        result.load_bytes(
            bytes.fromhex(
                "07 00 41 42 43 44 01 02 03 "
                "01 02 34 12 "
                "05 02 C9 FF "
                "00 00 00"
            )
        )

        self.assertEqual(7, result._room)
        self.assertEqual("41424344", result._service_code_raw)
        self.assertEqual("010203", result._header_raw)
        self.assertEqual(-5.5, result._temperature)
        self.assertEqual("complete", result._parse_status)
        self.assertEqual("0000", result._trailing_raw)

        small = Ventilation()
        small.room_id = 7
        small.status.in_door_temp = 23.5
        result.do()
        self.assertEqual(23.5, small.status.in_door_temp)

    def test_cmd52_partial_payload_never_synthesizes_or_overwrites_state(self):
        result = VentilationQueryCompositeSituationResult(
            1, EnumDevice.SMALL_VAM
        )
        result.load_bytes(bytes.fromhex("07 00 41 42 43 44 01 02 03 05 02 10"))

        self.assertEqual("truncated_tlv_value", result._parse_status)
        self.assertIsNone(result._temperature)

    def test_standard_and_small_vam_speed_round_trip(self):
        fan_component = sys.modules.setdefault(
            "homeassistant.components.fan",
            types.ModuleType("homeassistant.components.fan"),
        )

        class FanEntity:
            @property
            def percentage_step(self):
                return 100 / self._attr_speed_count

            def schedule_update_ha_state(self):
                return None

        class FanEntityFeature(IntFlag):
            SET_SPEED = 1
            PRESET_MODE = 2
            TURN_ON = 4
            TURN_OFF = 8

        fan_component.FanEntity = FanEntity
        fan_component.FanEntityFeature = FanEntityFeature
        sys.modules["homeassistant.components"].fan = fan_component

        ha_const = sys.modules.setdefault(
            "homeassistant.const", types.ModuleType("homeassistant.const")
        )
        ha_const.MAJOR_VERSION = 2026
        ha_const.MINOR_VERSION = 7

        helpers = sys.modules.setdefault(
            "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
        )
        helper_entity = sys.modules.setdefault(
            "homeassistant.helpers.entity", types.ModuleType("homeassistant.helpers.entity")
        )
        helper_entity.DeviceInfo = dict
        helpers.entity = helper_entity

        custom_components = sys.modules.setdefault(
            "custom_components", types.ModuleType("custom_components")
        )
        custom_components.__path__ = [str(PROJECT_ROOT / "custom_components")]
        package = sys.modules.setdefault(
            "custom_components.ds_air", types.ModuleType("custom_components.ds_air")
        )
        package.__path__ = [str(PROJECT_ROOT / "custom_components" / "ds_air")]
        package_const = sys.modules.setdefault(
            "custom_components.ds_air.const", types.ModuleType("custom_components.ds_air.const")
        )
        package_const.DOMAIN = "ds_air"

        fan_module = importlib.import_module("custom_components.ds_air.fan")
        package_dao = importlib.import_module(
            "custom_components.ds_air.ds_air_service.dao"
        )

        with patch.object(fan_module.Service, "register_vent_hook"), patch.object(
            fan_module.Service, "control_vent"
        ) as control_vent:
            standard = package_dao.Ventilation()
            standard.room_id = 7
            standard.status.air_flow = fan_module.EnumControl.AirFlow.WEAK
            standard_entity = fan_module.DsVent(standard)
            self.assertEqual(2, standard_entity._attr_speed_count)
            for air_flow, percentage in (
                (fan_module.EnumControl.AirFlow.WEAK, 50),
                (fan_module.EnumControl.AirFlow.STRONG, 100),
            ):
                standard.status.air_flow = air_flow
                self.assertEqual(percentage, standard_entity.percentage)
                standard_entity.set_percentage(percentage)
                self.assertEqual(air_flow, control_vent.call_args.args[1].air_flow)

            standard_entity.set_percentage(67)
            self.assertEqual(
                fan_module.EnumControl.AirFlow.STRONG,
                control_vent.call_args.args[1].air_flow,
            )

            small = package_dao.Ventilation()
            small.room_id = 8
            small.is_small_vam = True
            small_entity = fan_module.DsVent(small)
            self.assertEqual(4, small_entity._attr_speed_count)
            for rank, percentage in ((1, 25), (2, 50), (3, 75), (4, 100)):
                air_flow = fan_module.EnumControl.AirFlow(rank)
                small.status.air_flow = air_flow
                self.assertEqual(percentage, small_entity.percentage)
                small_entity.set_percentage(percentage)
                self.assertEqual(air_flow, control_vent.call_args.args[1].air_flow)


class TransportSafetyTest(unittest.TestCase):
    def test_socket_client_reassembles_split_heartbeat(self):
        class FakeSocket:
            def __init__(self):
                self._chunks = [b"\x02\x00", b"\x00\x03"]

            def recv(self, _size):
                return self._chunks.pop(0)

        client = SocketClient.__new__(SocketClient)
        client._s = FakeSocket()
        client._ready = True
        client._recv_buffer = b""

        self.assertEqual([], client.recv())
        results = client.recv()
        self.assertEqual(1, len(results))
        self.assertIsInstance(results[0], HeartbeatResult)

    def test_cmd80_receive_logging_redacts_payload(self):
        frame = bytearray(24)
        frame[0] = 2
        frame[1:3] = struct.pack("<H", 20)
        frame[17:19] = struct.pack("<H", 80)
        frame[19:23] = bytes.fromhex("DE AD BE EF")
        frame[23] = 3

        with patch.object(service_module, "_log") as log:
            _log_received_frame(bytes(frame))

        message = log.call_args.args[0]
        self.assertIn("payload=redacted", message)
        self.assertNotIn("deadbeef", message.lower())


if __name__ == "__main__":
    unittest.main()

import sys
import types
import unittest
from enum import Enum
from pathlib import Path
from unittest.mock import patch


def _install_homeassistant_stubs():
    """Provide only the HA constants imported by the protocol-only modules."""
    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    climate = types.ModuleType("homeassistant.components.climate")
    climate_const = types.ModuleType("homeassistant.components.climate.const")

    class HVACMode(str, Enum):
        AUTO = "auto"
        COOL = "cool"
        DRY = "dry"
        FAN_ONLY = "fan_only"
        HEAT = "heat"

    class HVACAction(str, Enum):
        COOLING = "cooling"
        DRYING = "drying"
        FAN = "fan"
        HEATING = "heating"
        PREHEATING = "preheating"

    climate.HVACMode = HVACMode
    climate.HVACAction = HVACAction
    climate_const.FAN_AUTO = "auto"
    climate_const.FAN_LOW = "low"
    climate_const.FAN_MEDIUM = "medium"
    climate_const.FAN_HIGH = "high"

    homeassistant.components = components
    components.climate = climate
    sys.modules.setdefault("homeassistant", homeassistant)
    sys.modules.setdefault("homeassistant.components", components)
    sys.modules.setdefault("homeassistant.components.climate", climate)
    sys.modules.setdefault("homeassistant.components.climate.const", climate_const)


_install_homeassistant_stubs()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "custom_components" / "ds_air"))

from ds_air_service.config import Config
from ds_air_service.ctrl_enum import EnumControl, EnumDevice, EnumOutDoorRunCond
from ds_air_service.decoder import (
    AckResult,
    AirConCapabilityQueryResult,
    AirConQueryStatusResult,
    AirConStatusChangedResult,
)
from ds_air_service.service import Service


class AirConQueryStatusResultTest(unittest.TestCase):
    _OPTIONAL_STATUS_FIELDS = (
        "current_temp",
        "setted_temp",
        "switch",
        "air_flow",
        "breathe",
        "fan_direction1",
        "fan_direction2",
        "humidity",
        "mode",
    )

    def setUp(self):
        self._is_c611 = Config.is_c611
        self._is_new_version = Config.is_new_version
        Config.is_c611 = False
        Config.is_new_version = False

    def tearDown(self):
        Config.is_c611 = self._is_c611
        Config.is_new_version = self._is_new_version

    def assert_optional_status_unknown(self, status, except_fields=()):
        for field in self._OPTIONAL_STATUS_FIELDS:
            if field not in except_fields:
                self.assertIsNone(getattr(status, field), field)

    @patch.object(Service, "set_aircon_status")
    def test_empty_status_flags_keep_every_optional_field_unknown(self, set_status):
        result = AirConQueryStatusResult(1, EnumDevice.AIRCON)
        result.load_bytes(bytes((3, 4, 0)))

        self.assert_optional_status_unknown(result)
        self.assertIsNone(result.hum_allow)
        self.assertIsNone(result.fresh_air_allow)
        self.assertIsNone(result.fresh_air_humidification)
        self.assertIsNone(result.three_d_fresh)

        result.do()
        self.assert_optional_status_unknown(set_status.call_args.args[3])

    @patch.object(Service, "set_aircon_status")
    def test_missing_air_flow_flag_does_not_emit_auto(self, set_status):
        result = AirConQueryStatusResult(1, EnumDevice.AIRCON)
        result.load_bytes(bytes((3, 4, EnumControl.Type.MODE, EnumControl.Mode.COLD)))

        self.assertEqual(EnumControl.Mode.COLD, result.mode)
        self.assert_optional_status_unknown(result, except_fields=("mode",))

        result.do()
        status = set_status.call_args.args[3]
        self.assertEqual(EnumControl.Mode.COLD, status.mode)
        self.assert_optional_status_unknown(status, except_fields=("mode",))

    @patch.object(Service, "set_aircon_status")
    def test_air_flow_flag_still_decodes_reported_value(self, set_status):
        result = AirConQueryStatusResult(2, EnumDevice.AIRCON)
        result.load_bytes(
            bytes(
                (
                    3,
                    4,
                    EnumControl.Type.AIR_FLOW,
                    EnumControl.AirFlow.SUPER_STRONG,
                )
            )
        )

        self.assertEqual(EnumControl.AirFlow.SUPER_STRONG, result.air_flow)
        self.assert_optional_status_unknown(result, except_fields=("air_flow",))

        result.do()
        status = set_status.call_args.args[3]
        self.assertEqual(EnumControl.AirFlow.SUPER_STRONG, status.air_flow)
        self.assert_optional_status_unknown(status, except_fields=("air_flow",))

    def test_d611_bit3_is_one_reserved_byte_and_does_not_create_temperature(self):
        result = AirConQueryStatusResult(3, EnumDevice.AIRCON)
        result.load_bytes(
            bytes(
                (
                    3,
                    4,
                    EnumControl.Type.CURRENT_TEMP | EnumControl.Type.SETTED_TEMP,
                    0xA5,  # official DTO consumes exactly one reserved byte
                    0xD7,
                    0x00,  # 21.5 C target, little endian tenths
                )
            )
        )

        self.assertIsNone(result.current_temp)
        self.assertEqual(215, result.setted_temp)
        self.assert_optional_status_unknown(result, except_fields=("setted_temp",))

    def test_status_changed_bit3_is_one_reserved_byte_and_stays_aligned(self):
        result = AirConStatusChangedResult(4, EnumDevice.AIRCON)
        result.load_bytes(
            bytes(
                (
                    3,
                    4,
                    EnumControl.Type.CURRENT_TEMP | EnumControl.Type.SETTED_TEMP,
                    0xA5,
                    0xD7,
                    0x00,
                )
            )
        )

        self.assertIsNone(result._status.current_temp)
        self.assertEqual(215, result._status.setted_temp)

    def test_capability_third_byte_matches_official_app_bit_layout(self):
        Config.is_new_version = True

        def decode(third_flag):
            result = AirConCapabilityQueryResult(1, EnumDevice.AIRCON)
            # room count, room, unit count, unit, first capability byte,
            # second capability byte, official third capability byte
            result.load_bytes(bytes((1, 7, 1, 0, 0, 0, third_flag)))
            return result.aircons[0]

        auto_dry = decode(1 << 0)
        self.assertEqual(1, auto_dry.auto_dry_mode)
        self.assertEqual(0, auto_dry.relax_mode)
        self.assertEqual(0, auto_dry.sleep_mode)

        comfort = decode(1 << 1)
        self.assertEqual(1, comfort.relax_mode)
        self.assertEqual(0, comfort.auto_dry_mode)

        sleep = decode(1 << 2)
        self.assertEqual(1, sleep.sleep_mode)
        self.assertEqual(0, sleep.auto_dry_mode)

        remaining = decode((1 << 3) | (1 << 4) | (1 << 5) | (2 << 6))
        self.assertEqual(1, remaining.pre_heat_mode)
        self.assertEqual(1, remaining.more_dry_mode)
        self.assertTrue(remaining.fan_volume_mute)
        self.assertEqual(EnumOutDoorRunCond.COLD, remaining.out_door_run_cond)

    def test_raw_six_decodes_as_mute_airflow(self):
        self.assertEqual(EnumControl.AirFlow.MUTE, EnumControl.AirFlow(6))


class GatewayProtocolProfileTest(unittest.TestCase):
    def setUp(self):
        self._config = (
            Config.gateway_model,
            Config.protocol_profile,
            Config.protocol_version_locked,
            Config.is_c611,
            Config.is_new_version,
        )

    def tearDown(self):
        (
            Config.gateway_model,
            Config.protocol_profile,
            Config.protocol_version_locked,
            Config.is_c611,
            Config.is_new_version,
        ) = self._config

    def test_d611_uses_verified_immutable_layout(self):
        Config.configure_gateway("DTA117D611")

        self.assertEqual(Config.PROFILE_D611, Config.protocol_profile)
        self.assertFalse(Config.is_c611)
        self.assertTrue(Config.is_new_version)
        self.assertTrue(Config.protocol_version_locked)

        AckResult(1, EnumDevice.SYSTEM).load_bytes(b"\x00")
        self.assertTrue(
            Config.is_new_version,
            "an ordinary ACK must not rewrite the verified D611 parser layout",
        )

    def test_legacy_profiles_lock_only_the_first_protocol_ack(self):
        for model in ("DTA117B611", "DTA117C611"):
            with self.subTest(model=model):
                Config.configure_gateway(model)
                self.assertFalse(Config.protocol_version_locked)

                AckResult(1, EnumDevice.SYSTEM).load_bytes(b"\x02")
                self.assertTrue(Config.is_new_version)
                self.assertTrue(Config.protocol_version_locked)

                AckResult(2, EnumDevice.SYSTEM).load_bytes(b"\x00")
                self.assertTrue(
                    Config.is_new_version,
                    "later generic ACKs must not flap the selected layout",
                )


if __name__ == "__main__":
    unittest.main()

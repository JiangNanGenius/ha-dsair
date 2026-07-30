import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "custom_components" / \
    "ds_air" / "zhonghong_temperature.py"
SPEC = importlib.util.spec_from_file_location("zhonghong_temperature_test", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def status_frame(records):
    raw = bytearray((0x01, 0x50, 0xFF, len(records)))
    for record in records:
        if len(record) != 10:
            raise ValueError("record must contain ten bytes")
        raw.extend(record)
    raw.append(sum(raw) & 0xFF)
    return bytes(raw)


class ZhonghongTemperatureDeframerTest(unittest.TestCase):
    def test_fragmented_status_extracts_complete_read_only_record(self):
        frame = status_frame([
            bytes((1, 0, 1, 24, 1, 4, 31, 0, 0, 0)),
            bytes((1, 3, 1, 25, 3, 2, 28, 0, 0, 0)),
        ])
        parser = module.ZhonghongStatusDeframer(outer_address=1)

        self.assertEqual([], parser.feed(b"\x12\x34" + frame[:7], 1234))
        observations = parser.feed(frame[7:], 1234)

        self.assertEqual(2, len(observations))
        self.assertEqual((1, 0, 31.0, 1234), (
            observations[0].outer_address,
            observations[0].indoor_address,
            observations[0].temperature_c,
            observations[0].observed_at_ms,
        ))
        self.assertEqual(3, observations[1].indoor_address)
        self.assertEqual(28.0, observations[1].temperature_c)
        self.assertEqual(25.0, observations[1].set_temperature_c)
        self.assertEqual(3, observations[1].mode_code)
        self.assertEqual(2, observations[1].fan_code)
        self.assertEqual(0, observations[1].fault_code)
        self.assertTrue(observations[1].online)
        self.assertFalse(observations[1].has_fault)

    def test_fault_and_offline_records_survive_missing_temperature(self):
        parser = module.ZhonghongStatusDeframer(outer_address=1)
        frame = status_frame([
            bytes((1, 2, 1, 24, 1, 4, 0xFF, 0x12, 0x35, 0x01)),
            bytes((1, 4, 0, 0xFF, 0, 0, 0xFF, 0xFF, 0, 0)),
        ])

        observations = parser.feed(frame, 2000)

        self.assertEqual(2, len(observations))
        fault = observations[0]
        self.assertIsNone(fault.temperature_c)
        self.assertEqual(0x12, fault.fault_code)
        self.assertTrue(fault.online)
        self.assertTrue(fault.has_fault)
        self.assertTrue(fault.is_main_unit)
        offline = observations[1]
        self.assertIsNone(offline.set_temperature_c)
        self.assertFalse(offline.online)
        self.assertFalse(offline.has_fault)

    def test_bad_checksum_and_other_outer_address_are_rejected(self):
        good = status_frame([
            bytes((2, 0, 1, 24, 1, 4, 30, 0, 0, 0)),
        ])
        bad = bytearray(status_frame([
            bytes((1, 0, 1, 24, 1, 4, 30, 0, 0, 0)),
        ]))
        bad[-1] ^= 0x01
        parser = module.ZhonghongStatusDeframer(outer_address=1)

        self.assertEqual([], parser.feed(good, 1000))
        self.assertEqual([], parser.feed(bytes(bad), 1001))

    def test_query_is_checksum_complete_and_read_only(self):
        self.assertEqual(bytes.fromhex("0150FFFFFFFF4D"), module.STATUS_QUERY)
        self.assertTrue(module._checksum_valid(module.STATUS_QUERY))


if __name__ == "__main__":
    unittest.main()

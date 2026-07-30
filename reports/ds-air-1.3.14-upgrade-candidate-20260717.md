# DS-AIR 1.3.14 Local Upgrade Candidate

Date: 2026-07-17

Status: local candidate only. No Home Assistant deployment, restart, or live
control command was performed while preparing this package.

## Candidate Scope

- Version is bumped from live `1.3.13` to local `1.3.14`.
- The live VAM implementation was copied read-only and preserved, then corrected
  where official APK protocol evidence showed unsafe behavior.
- Existing climate, sensor, and select behavior remains in place.
- The candidate adds protocol-backed cleaning status and one non-sensitive
  gateway diagnostics sensor.
- Optional cmd36 cleaning write entities exist, but the selection switches and
  start button are disabled in the entity registry by default.

## Files in the Candidate

- Integration/platform wiring: `custom_components/ds_air/__init__.py`,
  `manifest.json`, `climate.py`, `const.py`, `fan.py`, `sensor.py`, `switch.py`,
  `button.py`, `cleaning_device.py`.
- Protocol/runtime: `ds_air_service/ctrl_enum.py`, `dao.py`, `decoder.py`,
  `param.py`, `service.py`.
- Regression coverage: `tests/test_protocol_diagnostics.py`, plus the preserved
  partial-status tests in `tests/test_aircon_query_status_decoder.py` and
  `tests/test_climate_partial_status.py`.

## Read Capabilities and Safety Boundaries

| Command | Candidate behavior | Entity boundary |
| --- | --- | --- |
| 35 | Parses confirmed keys 4, 5, 6, 7, 8, 14, and 15 without creating a fake percentage. Truncated records retain raw evidence but publish no partial semantics. | One work-state sensor per capable air conditioner. Unknown stays `None`, not `0%`. |
| 35 keys 16-20 | Keeps stable names `vam_cleaning_tlv_16` through `_20`, raw TLVs, and `semantic_status=unmapped`. Key 18 uses the confirmed bit/nibble transform. | Attributes on the single gateway diagnostics entity only; no standalone/default entities. |
| 6 | Length-bounded error parsing, unknown device-safe, raw and normalized error codes, source timestamp. | Attributes on the gateway diagnostics entity. |
| 80 | Reads only gateway version, Wi-Fi firmware version, and gateway time. MAC, IP, DNS, area, phone, and distributor fields are discarded; raw cmd80 receive logging is redacted. | Gateway version is the diagnostics sensor state; other non-sensitive values are attributes. |
| 234 | Reads signed signal dBm, ping success count, delay, raw four-byte evidence, and official sentinel values. | Diagnostics attributes; polled at low frequency. |
| 10 / 220 | Validates complete responses and records command support only. Empty valid responses do not become zero-valued measurements. | Diagnostics support/timestamp attributes only. |
| 52 MiniVAM composite | Correctly recognizes the official room/reserved + seven-byte header and TLV terminator. Only key 5's signed `/10` temperature encoding is proven; keys 1-4 remain unnamed. | No polling and no state/entity publication in 1.3.14; unsolicited packets remain evidence-only. |
| 243 / 259 / 60 / 61 | Unsupported and deliberately not inferred. | No entities. No auxiliary-heat inference. |

## VAM Preservation

- Standard VAM and MiniVAM discovery, status, control, preset modes, and fan
  entities from the live integration are retained.
- Initial capability replies are no longer dropped before service readiness.
- Multiple VAMs are retained, and status updates distinguish standard VAM from
  MiniVAM even when room/unit coordinates match.
- Standard VAM is constrained to the official weak/strong values `1` and `3`
  (`50%`/`100%`). MiniVAM retains four linear ranks `1..4`
  (`25%`/`50%`/`75%`/`100%`).
- A partial VAM status cannot erase previously known fields with fabricated
  defaults.

## Cleaning Write Boundary

- Cmd36 is room-scoped and now encodes each record as
  `record_index, room, reserved=0, type=2, TLV, record_terminator`.
- Duplicate selected units in the same room are deduplicated before encoding.
- The authoritative cmd35 state query is sent only after a successful two-byte
  cmd36 response; button press itself is not treated as success.
- Per-air-conditioner selection switches and the start button are disabled by
  default and require explicit entity-registry opt-in after live read-only
  verification.

## Verification

Commands run locally:

```sh
python3 -m py_compile custom_components/ds_air/*.py \
  custom_components/ds_air/ds_air_service/*.py
python3 -m unittest discover -s tests -v
```

Result: **29 tests passed**. Coverage includes cmd35 mapping/truncation, cmd36
golden bytes and success gating, cmd6/10/80/220/234, non-sensitive cmd80 logs,
TCP split-frame reassembly, VAM capability/status isolation, MiniVAM cmd52
evidence-only parsing, two-speed standard VAM, four-speed MiniVAM, and inherited
air-conditioner partial-status preservation.

An independent protocol review found and the candidate resolved:

1. Official `canJoin` selection logic (`workState == 0` and `canJoin != 1`).
2. Cmd36's missing record index/room-scoped encoding and premature state query.
3. MiniVAM cmd52's seven-byte header, one-byte terminator, signed/scaled key 5,
   and unsafe `-1000` partial-state overwrites.
4. Standard VAM's official two-speed values versus MiniVAM's four-speed values.
5. Cmd234 sentinel handling, cmd80 raw payload privacy, initial VAM capability,
   and same-coordinate VAM status routing.

## Known Residual Risks

- Home Assistant is not installed in this local test runtime, so platform import
  behavior was exercised with narrow stubs rather than a full HA instance.
- No live gateway packet or entity-registry migration was tested. The current
  live gateway facts (`03.19.00`, `192.168.10.17:8008`) are read-only evidence,
  not a post-deployment validation.
- `Device.unique_id` remains `daikin_<room>_<unit>`. Changing it now would break
  existing entity identities; therefore a standard VAM and MiniVAM at identical
  coordinates can still collide at the HA entity/device-registry layer even
  though runtime status routing is isolated.
- The new work-state sensor uses suffix
  `_heat_exchange_cleaning_status`. A prior experimental
  `_heat_exchange_cleaning_progress` entity, if present, will become orphaned;
  remove it only after validating the new sensor.
- Initial TCP connection retry remains inherited/blocking behavior. Device
  discovery after connection is bounded to 30 seconds, and split/coalesced TCP
  frames are now preserved.
- The working copy is iCloud-backed. Deployment must exclude AppleDouble,
  `.DS_Store`, `__pycache__`, `.git`, reports, tests, and any backup files.

## Suggested Live Migration (Not Performed)

1. Keep the current live `1.3.13` directory intact and make a timestamped backup
   outside `custom_components/ds_air`.
2. Copy the whole local `custom_components/ds_air` directory to a temporary
   directory on the HA host, excluding non-runtime artifacts listed above.
3. Run `python3 -m py_compile` against the staged runtime files, compare the
   staged manifest/version, then atomically replace the component directory.
4. Restart Home Assistant once. Do not enable either cleaning write entity yet.
5. Verify first, read-only:
   - integration setup completes and existing climate/entity unique IDs remain;
   - actual discovered VAM count and fan entities match the pre-upgrade registry;
   - gateway diagnostics reports firmware `03.19.00` and logs contain no cmd80
     sensitive payload;
   - cmd35 unknowns remain unknown and no cleaning `0%` entity is created;
   - keys 16-20 appear only as `unmapped` diagnostics when actually received;
   - cmd10/cmd220 show support only after valid responses and never fake zero;
   - no cmd52 polling is emitted.
6. After those checks and a separate confirmation for a real room, optionally
   enable the cleaning selection/start entities and validate one cmd36 action.
7. After the new status identity is proven, remove any orphaned legacy
   `_heat_exchange_cleaning_progress` registry entry.

## Rollback

1. Restore the timestamped `1.3.13` component directory as one unit.
2. Restart Home Assistant once.
3. Confirm the original climates, sensors, selects, and VAM fans reload.
4. Leave newly introduced registry entries disabled/unavailable until the next
   attempt; do not delete historical entities during the rollback itself.

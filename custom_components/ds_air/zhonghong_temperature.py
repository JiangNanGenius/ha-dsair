"""Read-only Zhonghong indoor-unit status observer.

This module deliberately implements only the checksum-verified 0x50 status
query.  It exposes the ten-byte indoor-unit status record but never sends a
Zhonghong control command.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import Callable

_LOGGER = logging.getLogger(__name__)

STATUS_QUERY = bytes((0x01, 0x50, 0xFF, 0xFF, 0xFF, 0xFF, 0x4D))
MAX_BUFFER_BYTES = 8192


@dataclass(frozen=True)
class TemperatureObservation:
    """One checksum-verified Zhonghong indoor-unit status observation.

    The historical class name is kept for compatibility with the existing
    temperature listener.  Every field below is copied directly from the
    documented ten-byte 0x50 record; no capability or state is inferred.
    """

    outer_address: int
    indoor_address: int
    power_code: int
    set_temperature_c: float | None
    mode_code: int
    fan_code: int
    temperature_c: float | None
    fault_code: int
    baffle_code: int
    other_info: int
    observed_at_ms: int

    @property
    def online(self) -> bool:
        """The protocol reserves FF as the indoor-unit offline marker."""
        return self.fault_code != 0xFF

    @property
    def has_fault(self) -> bool:
        """Return true only for a real nonzero, non-offline fault byte."""
        return self.fault_code not in (0x00, 0xFF)

    @property
    def is_main_unit(self) -> bool:
        """Bit zero of the documented other-info byte marks the main unit."""
        return bool(self.other_info & 0x01)


def _checksum_valid(frame: bytes) -> bool:
    return len(frame) >= 2 and (sum(frame[:-1]) & 0xFF) == frame[-1]


class ZhonghongStatusDeframer:
    """Incrementally extract only valid 0x50 status records from a TCP stream."""

    def __init__(self, outer_address: int = 1) -> None:
        self._outer_address = outer_address
        self._buffer = bytearray()

    def feed(
        self, data: bytes, observed_at_ms: int | None = None
    ) -> list[TemperatureObservation]:
        if not data:
            return []
        self._buffer.extend(data)
        if len(self._buffer) > MAX_BUFFER_BYTES:
            del self._buffer[:-MAX_BUFFER_BYTES]
        observed_ms = observed_at_ms or int(time.time() * 1000)
        result: list[TemperatureObservation] = []

        guard = 0
        while self._buffer and guard < MAX_BUFFER_BYTES * 2:
            guard += 1
            if self._buffer[0] == 0x12:
                if len(self._buffer) < 2:
                    break
                if self._buffer[1] == 0x34:
                    del self._buffer[:2]
                    continue
            if self._buffer[0] != 0x01:
                del self._buffer[:1]
                continue
            if len(self._buffer) < 2:
                break
            function = self._buffer[1]
            if function != 0x50:
                del self._buffer[:1]
                continue
            if len(self._buffer) < 4:
                break
            control = self._buffer[2]
            count = self._buffer[3]
            if control in (0xFF, 0x02) and count == 0xFF:
                frame_length = 7
                is_status = False
            elif control in (0x01, 0x0F, 0xFF) and count <= 64:
                frame_length = 5 + count * 10
                is_status = True
            elif control == 0x02 and count <= 64:
                frame_length = 5 + count * 3
                is_status = False
            else:
                del self._buffer[:1]
                continue
            if len(self._buffer) < frame_length:
                break
            frame = bytes(self._buffer[:frame_length])
            if not _checksum_valid(frame):
                del self._buffer[:1]
                continue
            del self._buffer[:frame_length]
            if not is_status:
                continue
            for index in range(count):
                start = 4 + index * 10
                record = frame[start:start + 10]
                outer = int(record[0])
                indoor = int(record[1])
                if outer != self._outer_address or not 0 <= indoor <= 63:
                    continue
                raw_set_temperature = int(record[3])
                raw_temperature = int(record[6])
                set_temperature = (
                    float(raw_set_temperature)
                    if raw_set_temperature != 0xFF
                    and 0 <= raw_set_temperature <= 80
                    else None
                )
                temperature = (
                    float(raw_temperature)
                    if raw_temperature != 0xFF and 0 <= raw_temperature <= 80
                    else None
                )
                result.append(TemperatureObservation(
                    outer_address=outer,
                    indoor_address=indoor,
                    power_code=int(record[2]),
                    set_temperature_c=set_temperature,
                    mode_code=int(record[4]),
                    fan_code=int(record[5]),
                    temperature_c=temperature,
                    fault_code=int(record[7]),
                    baffle_code=int(record[8]),
                    other_info=int(record[9]),
                    observed_at_ms=observed_ms,
                ))
        return result


class ZhonghongTemperatureObserver:
    """Maintain one read-only TCP session and publish validated temperatures."""

    def __init__(
        self,
        host: str,
        port: int,
        poll_interval: float = 10.0,
        outer_address: int = 1,
    ) -> None:
        self.host = host
        self.port = port
        self.poll_interval = max(5.0, float(poll_interval))
        self.outer_address = int(outer_address)
        self._deframer = ZhonghongStatusDeframer(self.outer_address)
        self._listeners: set[Callable[[TemperatureObservation], None]] = set()
        self._latest: dict[tuple[int, int], TemperatureObservation] = {}
        self._task: asyncio.Task | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.connected = False
        self.last_error: str | None = None
        self.last_frame_observed_at_ms = 0

    @property
    def source_prefix(self) -> str:
        return f"zhonghong_readonly://{self.host}:{self.port}"

    def source_for(self, observation: TemperatureObservation) -> str:
        return (
            f"{self.source_prefix}/{observation.outer_address}/"
            f"{observation.indoor_address}"
        )

    def latest(
        self, outer_address: int, indoor_address: int
    ) -> TemperatureObservation | None:
        return self._latest.get((outer_address, indoor_address))

    def register_listener(
        self, listener: Callable[[TemperatureObservation], None]
    ) -> Callable[[], None]:
        self._listeners.add(listener)

        def remove() -> None:
            self._listeners.discard(listener)

        return remove

    async def async_start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(), name="ds_air_zhonghong_temperature"
            )

    async def async_stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
        self._close_writer()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass

    def _close_writer(self) -> None:
        writer = self._writer
        self._writer = None
        self.connected = False
        if writer is not None:
            writer.close()

    def _publish(self, observations: list[TemperatureObservation]) -> None:
        for observation in observations:
            self._latest[(
                observation.outer_address, observation.indoor_address
            )] = observation
            self.last_frame_observed_at_ms = max(
                self.last_frame_observed_at_ms, observation.observed_at_ms
            )
            for listener in tuple(self._listeners):
                try:
                    listener(observation)
                except Exception:  # pragma: no cover - defensive HA callback guard
                    _LOGGER.exception("Zhonghong temperature listener failed")

    async def _run(self) -> None:
        backoff = 2.0
        while True:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=5.0
                )
                self._deframer = ZhonghongStatusDeframer(self.outer_address)
                self._writer = writer
                self.connected = True
                self.last_error = None
                backoff = 2.0
                await self._connected_loop(reader, writer)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                _LOGGER.warning(
                    "Zhonghong read-only temperature link %s:%s unavailable: %s",
                    self.host,
                    self.port,
                    self.last_error,
                )
            finally:
                self._close_writer()
            await asyncio.sleep(backoff)
            backoff = min(30.0, backoff * 2.0)

    async def _connected_loop(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while True:
            started = asyncio.get_running_loop().time()
            writer.write(STATUS_QUERY)
            await writer.drain()
            deadline = started + min(8.0, self.poll_interval)
            received_status = False
            quiet_deadline = None
            while asyncio.get_running_loop().time() < deadline:
                now = asyncio.get_running_loop().time()
                read_deadline = min(
                    deadline,
                    quiet_deadline if quiet_deadline is not None else deadline,
                )
                timeout = max(0.01, read_deadline - now)
                try:
                    data = await asyncio.wait_for(reader.read(4096), timeout=timeout)
                except asyncio.TimeoutError:
                    if received_status:
                        break
                    raise
                if not data:
                    raise ConnectionError("peer closed TCP stream")
                observations = self._deframer.feed(data)
                if observations:
                    self._publish(observations)
                    received_status = True
                    quiet_deadline = asyncio.get_running_loop().time() + 0.5
            if not received_status:
                raise TimeoutError("0x50 status response timeout")
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.0, self.poll_interval - elapsed))

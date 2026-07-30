import logging
import socket
import struct
import time
import typing
from threading import Thread, Lock, RLock

from .ctrl_enum import EnumDevice, EnumCmdType
from .dao import Room, AirCon, AirConStatus, get_device_by_aircon, Sensor, STATUS_ATTR, \
    Ventilation, VentilationStatus, get_device_by_vent, GatewayDiagnostics
from .decoder import decoder, BaseResult
from .display import display
from .param import Param, HandShakeParam, HeartbeatParam, AirConControlParam, AirConQueryStatusParam, Sensor2InfoParam, \
    AirConCleaningQueryParam, AirConCleaningControlParam, VentilationControlParam, VentilationQueryStatusParam, \
    GetGWInfoParam, GatewaySignalQueryParam, \
    FilterServiceLifeQueryParam, FilterCleanSignResetParam, \
    DaikinCareExponentQueryParam, \
    AirConInletTempAndHumidityQueryParam

_LOGGER = logging.getLogger(__name__)


def _log(s: str):
    s = str(s)
    for i in s.split('\n'):
        _LOGGER.debug(i)


def _log_received_frame(frame: bytes):
    """Keep protocol evidence while redacting sensitive gateway-info payloads."""
    cmd_type = None
    if len(frame) >= 19:
        cmd_type = struct.unpack("<H", frame[17:19])[0]
    if cmd_type == EnumCmdType.SYS_GET_GW_INFO.value:
        _log(f"recv command={cmd_type} bytes={len(frame)} payload=redacted")
    else:
        _log("recv hex: 0x" + frame.hex())


class SocketClient:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._locker = RLock()
        self._s = None
        self._recv_buffer = b""
        while not self.do_connect():
            time.sleep(3)
        self._ready = True
        self._recv_thread = RecvThread(self)
        self._recv_thread.start()

    def destroy(self):
        self._ready = False
        self._recv_thread.terminate()
        self._disconnect()

    def _disconnect(self):
        """Close the active transport and discard any partial old-session frame."""
        sock = self._s
        self._s = None
        self._recv_buffer = b""
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def do_connect(self):
        candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            candidate.connect((self._host, self._port))
            old_socket = self._s
            self._s = candidate
            self._recv_buffer = b""
            if old_socket is not None and old_socket is not candidate:
                try:
                    old_socket.close()
                except OSError:
                    pass
            _log('connected')
            return True
        except socket.error as exc:
            try:
                candidate.close()
            except OSError:
                pass
            _log('connected error')
            _log(str(exc))
            return False

    def _send_frame_unlocked(self, frame: bytes):
        self._s.sendall(frame)

    def _reconnect(self):
        """Replace a dead TCP session and prove the new session with handshake."""
        with self._locker:
            self._disconnect()
            handshake_frame = HandShakeParam().to_string()
            while self._ready:
                if not self.do_connect():
                    time.sleep(3)
                    continue
                try:
                    _log("send hex: 0x" + handshake_frame.hex())
                    _log("send reconnect handshake")
                    self._send_frame_unlocked(handshake_frame)
                    return True
                except Exception as exc:
                    _log("reconnect handshake failed")
                    _log(str(exc))
                    self._disconnect()
                    time.sleep(3)
            return False

    def send(self, p: Param):
        frame = p.to_string()
        with self._locker:
            _log("send hex: 0x" + frame.hex())
            _log('\033[31msend:\033[0m')
            _log(display(p))
            done = False
            while not done:
                try:
                    self._send_frame_unlocked(frame)
                    done = True
                except Exception:
                    if not self._reconnect():
                        break

    def recv(self) -> (typing.List[BaseResult], bytes):
        res = []
        done = False
        data = None

        while not done:
            try:
                data = self._s.recv(1024)
                done = True
            except Exception:
                if not self._ready:
                    return [], None
                if not self._reconnect():
                    return [], None
        if data == b"":
            # An orderly TCP close is not an empty protocol packet.  Without
            # this branch RecvThread spins on EOF until an unrelated send happens
            # to fail.  Reset the partial-frame buffer before the new session.
            self._reconnect()
            return res
        if data is None:
            return res
        self._recv_buffer += data
        while self._recv_buffer:
            if len(self._recv_buffer) < 4:
                break
            if self._recv_buffer[0] != 2:
                _log("discarding unframed receive byte")
                self._recv_buffer = self._recv_buffer[1:]
                continue
            length = struct.unpack("<H", self._recv_buffer[1:3])[0]
            frame_length = length + 4
            if len(self._recv_buffer) < frame_length:
                break
            frame = self._recv_buffer[:frame_length]
            self._recv_buffer = self._recv_buffer[frame_length:]
            _log_received_frame(frame)
            try:
                r, _ = decoder(frame)
                if r is not None:
                    res.append(r)
            except Exception as e:
                _log(e)
        return res


class RecvThread(Thread):
    def __init__(self, sock: SocketClient):
        super().__init__()
        self._sock = sock
        self._locker = Lock()
        self._running = True

    def terminate(self):
        self._running = False

    def run(self) -> None:
        while self._running:
            res = self._sock.recv()
            for i in res:
                _log('\033[31mrecv:\033[0m')
                _log(display(i))
                self._locker.acquire()
                try:
                    if i is not None:
                        i.do()
                except Exception as e:
                    _log(e)
                self._locker.release()


class HeartBeatThread(Thread):
    def __init__(self):
        super().__init__()
        self._running = True

    def terminate(self):
        self._running = False

    def run(self) -> None:
        super().run()
        time.sleep(30)
        cnt = 0
        while self._running:
            Service.send_msg(HeartbeatParam())
            # The official App refreshes this room-scoped read-only observation
            # independently of the slower full status scan.
            Service.send_msg(AirConInletTempAndHumidityQueryParam())
            cnt += 1
            if cnt == Service.get_scan_interval():
                _log("poll_status")
                cnt = 0
                Service.poll_status()

            time.sleep(60)


class Service:
    _DIAGNOSTICS_POLL_EVERY = 12
    _DEVICE_DISCOVERY_TIMEOUT_SECONDS = 30
    _socket_client = None  # type: SocketClient
    _rooms = None  # type: typing.List[Room]
    _aircons = None  # type: typing.List[AirCon]
    _new_aircons = None  # type: typing.List[AirCon]
    _bathrooms = None  # type: typing.List[AirCon]
    _ventilations = None  # type: typing.List[Ventilation]
    _ready = False  # type: bool
    _none_stat_dev_cnt = 0  # type: int
    _status_hook = []  # type: typing.List[(AirCon, typing.Callable)]
    _sensor_hook = []  # type: typing.List[(str, typing.Callable)]
    _vent_hook = []  # type: typing.List[(Ventilation, typing.Callable)]
    _diagnostics_hook = []  # type: typing.List[typing.Callable]
    _heartbeat_thread = None
    _sensors = []  # type: typing.List[Sensor]
    _scan_interval = 5  # type: int
    _cleaning_info_ready = False  # type: bool
    _cleaning_selected = set()
    _gateway_diagnostics = GatewayDiagnostics()
    _diagnostics_poll_count = 0

    @staticmethod
    def init(host: str, port: int, scan_interval: int):
        if Service._ready:
            return
        Service._scan_interval = scan_interval
        Service._socket_client = SocketClient(host, port)
        Service._socket_client.send(HandShakeParam())
        Service._heartbeat_thread = HeartBeatThread()
        Service._heartbeat_thread.start()
        discovery_deadline = time.monotonic() + Service._DEVICE_DISCOVERY_TIMEOUT_SECONDS
        while Service._rooms is None or Service._aircons is None \
                or Service._new_aircons is None or Service._bathrooms is None:
            if time.monotonic() >= discovery_deadline:
                Service.destroy()
                raise TimeoutError("DS-AIR device discovery timed out")
            time.sleep(1)
        for i in Service._aircons:
            for j in Service._rooms:
                if i.room_id == j.id:
                    i.alias = j.alias
                    if i.unit_id:
                        i.alias += str(i.unit_id)
        for i in Service._new_aircons:
            for j in Service._rooms:
                if i.room_id == j.id:
                    i.alias = j.alias
                    if i.unit_id:
                        i.alias += str(i.unit_id)
        for i in Service._bathrooms:
            for j in Service._rooms:
                if i.room_id == j.id:
                    i.alias = j.alias
                    if i.unit_id:
                        i.alias += str(i.unit_id)
        for i in Service.get_ventilations():
            for j in Service._rooms:
                if i.room_id == j.id:
                    if not i.alias:
                        i.alias = j.alias
                    if i.unit_id and not str(i.alias).endswith(str(i.unit_id)):
                        i.alias += str(i.unit_id)
        Service._cleaning_info_ready = False
        Service.send_msg(AirConCleaningQueryParam())
        # Strictly read-only official App query.  Unsupported gateways leave
        # the new entities unavailable; no fallback value is synthesized.
        Service.send_msg(AirConInletTempAndHumidityQueryParam())
        Service.poll_diagnostics(initial=True)
        deadline = time.time() + 3
        while not Service._cleaning_info_ready and time.time() < deadline:
            time.sleep(0.1)
        Service._ready = True

    @staticmethod
    def destroy():
        if Service._heartbeat_thread is not None:
            Service._heartbeat_thread.terminate()
        if Service._socket_client is not None:
            Service._socket_client.destroy()
        Service._socket_client = None
        Service._rooms = None
        Service._aircons = None
        Service._new_aircons = None
        Service._bathrooms = None
        Service._ventilations = None
        Service._none_stat_dev_cnt = 0
        Service._status_hook = []
        Service._sensor_hook = []
        Service._vent_hook = []
        Service._diagnostics_hook = []
        Service._heartbeat_thread = None
        Service._sensors = []
        Service._cleaning_info_ready = False
        Service._cleaning_selected = set()
        Service._gateway_diagnostics = GatewayDiagnostics()
        Service._diagnostics_poll_count = 0
        Service._ready = False

    @staticmethod
    def get_aircons():
        aircons = []
        if Service._new_aircons is not None:
            aircons += Service._new_aircons
        if Service._aircons is not None:
            aircons += Service._aircons
        if Service._bathrooms is not None:
            aircons += Service._bathrooms
        return aircons

    @staticmethod
    def get_ventilations():
        return Service._ventilations or []

    @staticmethod
    def get_gateway_diagnostics():
        return Service._gateway_diagnostics

    @staticmethod
    def control(aircon: AirCon, status: AirConStatus):
        p = AirConControlParam(aircon, status)
        Service.send_msg(p)

    @staticmethod
    def control_vent(vent: Ventilation, status: VentilationStatus):
        p = VentilationControlParam(vent, status)
        Service.send_msg(p)

    @staticmethod
    def reset_filter_clean_sign(aircon: AirCon):
        """Reset all local filter-clean reminder bits for one indoor room."""
        Service.send_msg(FilterCleanSignResetParam(aircon, 7))

    @staticmethod
    def select_heat_exchange_cleaning(aircon: AirCon, selected: bool):
        if selected and Service.is_heat_exchange_cleaning_joinable(aircon):
            Service._cleaning_selected.add(aircon.unique_id)
        else:
            Service._cleaning_selected.discard(aircon.unique_id)

    @staticmethod
    def is_heat_exchange_cleaning_selected(aircon: AirCon):
        return aircon.unique_id in Service._cleaning_selected

    @staticmethod
    def is_heat_exchange_cleaning_joinable(aircon: AirCon):
        """Match the official work-state/canJoin selection gate."""
        return (
            aircon.heat_exchange_cleaning_allow
            and aircon.heat_exchange_cleaning_work_state == 0
            and aircon.heat_exchange_cleaning_can_join != 1
        )

    @staticmethod
    def start_selected_heat_exchange_cleaning():
        aircons = [
            i for i in Service.get_aircons()
            if Service.is_heat_exchange_cleaning_joinable(i)
            and i.unique_id in Service._cleaning_selected
        ]
        if not aircons:
            return
        Service.send_msg(AirConCleaningControlParam(aircons, 1))

    @staticmethod
    def register_status_hook(device: AirCon, hook: typing.Callable):
        Service._status_hook.append((device, hook))

    @staticmethod
    def register_sensor_hook(unique_id: str, hook: typing.Callable):
        Service._sensor_hook.append((unique_id, hook))

    @staticmethod
    def register_vent_hook(device: Ventilation, hook: typing.Callable):
        Service._vent_hook.append((device, hook))

    @staticmethod
    def register_diagnostics_hook(hook: typing.Callable):
        Service._diagnostics_hook.append(hook)

    # ----split line---- above for component, below for inner call

    @staticmethod
    def is_ready() -> bool:
        return Service._ready

    @staticmethod
    def send_msg(p: Param):
        """send msg to climate gateway"""
        Service._socket_client.send(p)

    @staticmethod
    def get_rooms():
        return Service._rooms

    @staticmethod
    def set_rooms(v: typing.List[Room]):
        Service._rooms = v

    @staticmethod
    def get_sensors():
        return Service._sensors

    @staticmethod
    def set_sensors(sensors):
        Service._sensors = sensors

    @staticmethod
    def set_device(t: EnumDevice, v: typing.List[AirCon]):
        Service._none_stat_dev_cnt += len(v)
        if t == EnumDevice.AIRCON:
            Service._aircons = v
        elif t == EnumDevice.NEWAIRCON:
            Service._new_aircons = v
        elif t == EnumDevice.BATHROOM:
            Service._bathrooms = v
        elif t == EnumDevice.VENTILATION or t == EnumDevice.SMALL_VAM:
            if Service._ventilations is None:
                Service._ventilations = list(v)
            else:
                known = {(i.room_id, i.unit_id, i.is_small_vam) for i in Service._ventilations}
                for item in v:
                    key = (item.room_id, item.unit_id, item.is_small_vam)
                    if key not in known:
                        Service._ventilations.append(item)
                        known.add(key)

    @staticmethod
    def set_aircon_status(target: EnumDevice, room: int, unit: int, status: AirConStatus):
        if Service._ready:
            Service.update_aircon(target, room, unit, status=status)
        else:
            li = []
            if target == EnumDevice.AIRCON:
                li = Service._aircons
            elif target == EnumDevice.NEWAIRCON:
                li = Service._new_aircons
            elif target == EnumDevice.BATHROOM:
                li = Service._bathrooms
            for i in li:
                if i.unit_id == unit and i.room_id == room:
                    i.status = status
                    Service._none_stat_dev_cnt -= 1
                    break

    @staticmethod
    def set_sensors_status(sensors: typing.List[Sensor]):
        for new_sensor in sensors:
            for sensor in Service._sensors:
                if sensor.unique_id == new_sensor.unique_id:
                    for attr in STATUS_ATTR:
                        setattr(sensor, attr, getattr(new_sensor, attr))
                    break
            for item in Service._sensor_hook:
                unique_id, func = item
                if new_sensor.unique_id == unique_id:
                    try:
                        func(new_sensor)
                    except Exception as e:
                        _log(str(e))

    @staticmethod
    def set_ventilation_status(target: EnumDevice, room: int, unit: int, status: VentilationStatus):
        for vent in Service.get_ventilations():
            if vent.unit_id == unit and vent.room_id == room \
                    and get_device_by_vent(vent) == target:
                for attr in (
                    "switch",
                    "mode",
                    "air_flow",
                    "in_door_temp",
                    "out_door_temp",
                    "out_door_humidity",
                    "pm25",
                ):
                    value = getattr(status, attr)
                    if value is not None:
                        setattr(vent.status, attr, value)
                if not Service._ready:
                    Service._none_stat_dev_cnt -= 1
                Service.update_ventilation(target, room, unit, status=vent.status)
                break

    @staticmethod
    def set_ventilation_capability(new_vent: Ventilation):
        """Apply the initial VAM capability reply to the discovered object."""
        target = get_device_by_vent(new_vent)
        for vent in Service.get_ventilations():
            if vent.room_id == new_vent.room_id and vent.unit_id == new_vent.unit_id \
                    and get_device_by_vent(vent) == target:
                vent.capability = new_vent.capability
                break

    @staticmethod
    def set_cleaning_info(items: typing.List[dict]):
        for item in items:
            room = item.get("room")
            for aircon in Service.get_aircons():
                if aircon.room_id == room:
                    for attr in (
                        "heat_exchange_cleaning_capability",
                        "heat_exchange_cleaning_can_join",
                        "heat_exchange_cleaning_work_state",
                        "heat_exchange_cleaning_phase_duration",
                        "heat_exchange_cleaning_v_sleep_value_1",
                        "heat_exchange_cleaning_v_sleep_value_2",
                        "heat_exchange_cleaning_finish",
                        "heat_exchange_cleaning_outdoor_status",
                        "heat_exchange_cleaning_raw_tlvs",
                        "heat_exchange_cleaning_parse_status",
                    ):
                        if attr in item:
                            setattr(aircon, attr, item[attr])
                    if "heat_exchange_cleaning_capability" in item:
                        aircon.heat_exchange_cleaning_allow = item["heat_exchange_cleaning_capability"] == 1
                    if "source_timestamp" in item:
                        aircon.heat_exchange_cleaning_source_timestamp = item["source_timestamp"]
                    if Service._ready:
                        Service.update_aircon(
                            get_device_by_aircon(aircon), room, aircon.unit_id, aircon=aircon
                        )

            vam_raw_tlvs = [
                tlv for tlv in item.get("heat_exchange_cleaning_raw_tlvs", [])
                if tlv.get("key") in (16, 17, 18, 19, 20)
            ]
            vam_fields = {
                key: item[key]
                for key in (
                    "vam_cleaning_tlv_16",
                    "vam_cleaning_tlv_17",
                    "vam_cleaning_tlv_18",
                    "vam_cleaning_tlv_19",
                    "vam_cleaning_tlv_20",
                )
                if key in item
            }
            if vam_raw_tlvs:
                vam_record = {
                    **vam_fields,
                    "raw_tlvs": vam_raw_tlvs,
                    "semantic_status": "unmapped",
                    "parse_status": item.get("heat_exchange_cleaning_parse_status"),
                    "source_timestamp": item.get("source_timestamp"),
                }
                Service._gateway_diagnostics.vam_cleaning_unmapped[str(room)] = vam_record
                for vent in Service.get_ventilations():
                    if vent.room_id != room:
                        continue
                    for attr, value in vam_fields.items():
                        setattr(vent, attr, value)
                    vent.vam_cleaning_semantic_status = "unmapped"
                    vent.vam_cleaning_raw_tlvs = vam_raw_tlvs
                    vent.vam_cleaning_parse_status = item.get(
                        "heat_exchange_cleaning_parse_status"
                    )
                    vent.vam_cleaning_source_timestamp = item.get("source_timestamp")
                Service._notify_diagnostics_hooks()
        Service._cleaning_info_ready = True

    @staticmethod
    def set_aircon_inlet_observations(items: typing.List[dict]):
        """Attach each complete room observation to one representative object."""
        for item in items:
            if item.get("inlet_parse_status") != "complete":
                continue
            room = item.get("room")
            # The wire record has no unit ID.  Use only the first discovered
            # object as storage/hook anchor for the room-level HA entity; never
            # copy the same value into every indoor unit as if independently
            # measured.  sensor.async_setup_entry uses the same discovery order.
            aircon = next(
                (candidate for candidate in Service.get_aircons()
                 if candidate.room_id == room),
                None,
            )
            if aircon is None:
                continue
            aircon.inlet_temperature_c = item.get("inlet_temperature_c")
            aircon.inlet_humidity_percent = item.get("inlet_humidity_percent")
            aircon.inlet_source_timestamp = item.get("source_timestamp")
            # Monotonic receipt time drives freshness so wall-clock
            # corrections cannot resurrect or prematurely expire data.
            aircon.inlet_source_monotonic = time.monotonic()
            aircon.inlet_temperature_quality = item.get(
                "inlet_temperature_quality", "missing"
            )
            aircon.inlet_humidity_quality = item.get(
                "inlet_humidity_quality", "missing"
            )
            aircon.inlet_parse_status = item.get("inlet_parse_status")
            aircon.inlet_raw_tlvs = list(item.get("inlet_raw_tlvs", []))
            if Service._ready:
                Service.update_aircon(
                    get_device_by_aircon(aircon),
                    room,
                    aircon.unit_id,
                    aircon=aircon,
                )

    @staticmethod
    def _notify_diagnostics_hooks():
        for hook in list(Service._diagnostics_hook):
            try:
                hook(Service._gateway_diagnostics)
            except Exception as e:
                _log("diagnostics hook error!!")
                _log(str(e))

    @staticmethod
    def set_gateway_info(gateway_version, wifi_version, gateway_time, source_timestamp):
        diagnostics = Service._gateway_diagnostics
        diagnostics.gateway_version = gateway_version
        diagnostics.wifi_version = wifi_version
        diagnostics.gateway_time = gateway_time
        diagnostics.gateway_info_source_timestamp = source_timestamp
        Service._notify_diagnostics_hooks()

    @staticmethod
    def set_gateway_signal(signal_strength, ping_success_count, network_delay, raw, source_timestamp):
        diagnostics = Service._gateway_diagnostics
        diagnostics.wifi_signal_strength = signal_strength
        diagnostics.wifi_ping_success_count = ping_success_count
        diagnostics.wifi_network_delay = network_delay
        diagnostics.gateway_signal_raw = raw
        diagnostics.gateway_signal_source_timestamp = source_timestamp
        Service._notify_diagnostics_hooks()

    @staticmethod
    def set_error_info(code_raw, code_normalized, device_id, device, room, level, source_timestamp):
        diagnostics = Service._gateway_diagnostics
        diagnostics.last_error_code_raw = code_raw
        diagnostics.last_error_code_normalized = code_normalized
        diagnostics.last_error_device_id = device_id
        diagnostics.last_error_device = device.name if device is not None else None
        diagnostics.last_error_room = room
        diagnostics.last_error_unit = None
        diagnostics.last_error_level = level
        diagnostics.last_error_source_timestamp = source_timestamp
        if device is not None:
            for aircon in Service.get_aircons():
                if aircon.room_id != room or get_device_by_aircon(aircon) != device:
                    continue
                aircon.failure_code_raw = code_raw
                aircon.failure_code_normalized = code_normalized
                aircon.failure_level = level
                aircon.failure_source_timestamp = source_timestamp
                if Service._ready:
                    Service.update_aircon(
                        device, room, aircon.unit_id, aircon=aircon
                    )
        Service._notify_diagnostics_hooks()

    @staticmethod
    def set_filter_clean_sign(device_id, device, room, status, source_timestamp):
        """Attach a local cmd9 filter reminder to the matching indoor unit(s)."""
        if device is None:
            return
        for aircon in Service.get_aircons():
            if aircon.room_id != room or get_device_by_aircon(aircon) != device:
                continue
            aircon.filter_clean_sign_status = status
            aircon.filter_clean_sign_source_timestamp = source_timestamp
            if Service._ready:
                Service.update_aircon(device, room, aircon.unit_id, aircon=aircon)

    @staticmethod
    def set_filter_service_life(items, source_timestamp):
        """Attach cmd10 VAM filter usage to its room without inventing units."""
        for item in items:
            room = item.get("room")
            room_vents = [
                candidate for candidate in Service.get_ventilations()
                if candidate.room_id == room
            ]
            # cmd10 has no unit or VAM subtype byte.  Do not copy one
            # room-scoped observation into multiple physical devices.
            if len(room_vents) != 1:
                continue
            vent = room_vents[0]
            used_percent = item.get("used_percent")
            if used_percent is not None and not 0 <= used_percent <= 100:
                used_percent = None
            vent.filter_used_percent = used_percent
            vent.filter_service_life_source_timestamp = source_timestamp
            if Service._ready:
                Service.update_ventilation(
                    get_device_by_vent(vent),
                    vent.room_id,
                    vent.unit_id,
                    vent=vent,
                )

    @staticmethod
    def set_feature_support(feature, source_timestamp):
        diagnostics = Service._gateway_diagnostics
        if feature == "filter_service_life":
            diagnostics.filter_service_life_supported = True
            diagnostics.filter_service_life_source_timestamp = source_timestamp
        elif feature == "daikin_care_exponent":
            diagnostics.daikin_care_exponent_supported = True
            diagnostics.daikin_care_exponent_source_timestamp = source_timestamp
        else:
            return
        Service._notify_diagnostics_hooks()

    @staticmethod
    def poll_diagnostics(initial: bool = False):
        """Poll non-sensitive link diagnostics at startup and then at low frequency."""
        Service.send_msg(GetGWInfoParam())
        Service.send_msg(GatewaySignalQueryParam())
        if initial:
            Service.send_msg(FilterServiceLifeQueryParam())
            Service.send_msg(DaikinCareExponentQueryParam())

    @staticmethod
    def poll_status():
        for target, aircons in (
            (EnumDevice.NEWAIRCON, Service._new_aircons),
            (EnumDevice.AIRCON, Service._aircons),
            (EnumDevice.BATHROOM, Service._bathrooms),
        ):
            for i in aircons or []:
                p = AirConQueryStatusParam()
                p.target = target
                p.device = i
                Service.send_msg(p)
        p = Sensor2InfoParam()
        Service.send_msg(p)
        Service.send_msg(AirConCleaningQueryParam())
        for i in Service.get_ventilations():
            p = VentilationQueryStatusParam()
            p.target = get_device_by_vent(i)
            p.device = i
            Service.send_msg(p)
        Service._diagnostics_poll_count += 1
        if Service._diagnostics_poll_count >= Service._DIAGNOSTICS_POLL_EVERY:
            Service._diagnostics_poll_count = 0
            Service.poll_diagnostics()

    @staticmethod
    def update_aircon(target: EnumDevice, room: int, unit: int, **kwargs):
        li = Service._status_hook
        for item in li:
            i, func = item
            if i.unit_id == unit and i.room_id == room and get_device_by_aircon(i) == target:
                try:
                    func(**kwargs)
                except Exception as e:
                    _log('hook error!!')
                    _log(str(e))

    @staticmethod
    def update_ventilation(target: EnumDevice, room: int, unit: int, **kwargs):
        for item in Service._vent_hook:
            i, func = item
            if i.unit_id == unit and i.room_id == room and get_device_by_vent(i) == target:
                try:
                    func(**kwargs)
                except Exception as e:
                    _log('vent hook error!!')
                    _log(str(e))

    @staticmethod
    def get_scan_interval():
        return Service._scan_interval

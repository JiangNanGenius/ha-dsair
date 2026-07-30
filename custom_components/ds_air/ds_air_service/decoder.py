import struct
import time
import typing

from .base_bean import BaseBean
from .config import Config
from .ctrl_enum import EnumDevice, EnumCmdType, EnumFanDirection, EnumOutDoorRunCond, EnumFanVolume, EnumControl, \
    EnumSensor, FreshAirHumidification, ThreeDFresh
from .dao import Room, AirCon, Geothermic, Ventilation, HD, Device, AirConStatus, get_device_by_aircon, Sensor, \
    UNINITIALIZED_VALUE, VentilationStatus, get_device_by_vent
from .param import GetRoomInfoParam, AirConRecommendedIndoorTempParam, AirConCapabilityQueryParam, \
    AirConQueryStatusParam, Sensor2InfoParam, VentilationCapabilityQueryParam, VentilationQueryStatusParam, \
    AirConCleaningQueryParam, OfficialSystemCmd


def decoder(b):
    if b[0] != 2:
        return None, None

    length = struct.unpack('<H', b[1:3])[0]
    if length == 0 or len(b) - 4 < length or struct.unpack('<B', b[length + 3:length + 4])[0] != 3:
        if length == 0:
            return HeartbeatResult(), None
        else:
            return None, None

    return result_factory(struct.unpack('<BHBBBBIBIBH' + str(length - 16) + 'sB', b[:length + 4])), b[length + 4:]


def result_factory(data):
    r1, length, r2, r3, subbody_ver, r4, cnt, dev_type, dev_id, need_ack, cmd_type, subbody, r5 = data
    if dev_id == EnumDevice.SYSTEM.value[1]:
        if cmd_type == EnumCmdType.SYS_ACK.value:
            result = AckResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_CMD_RSP.value:
            result = CmdRspResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_TIME_SYNC.value:
            result = TimeSyncResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_ERR_CODE.value:
            result = ErrCodeResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_FILTER_CLEAN_SIGN.value:
            result = FilterCleanSignResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_FILTER_SERVICE_LIFE.value:
            result = FilterServiceLifeResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_GET_WEATHER.value:
            result = GetWeatherResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_LOGIN.value:
            result = LoginResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_CHANGE_PW.value:
            result = ChangePWResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_GET_ROOM_INFO.value:
            result = GetRoomInfoResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_QUERY_SCHEDULE_SETTING.value:
            result = QueryScheduleSettingResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_QUERY_SCHEDULE_ID.value:
            result = QueryScheduleIDResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_HAND_SHAKE.value:
            result = HandShakeResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_GET_GW_INFO.value:
            result = GetGWInfoResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_CMD_TRANSFER.value:
            result = CmdTransferResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_QUERY_SCHEDULE_FINISH.value:
            result = QueryScheduleFinish(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.AIR_CON_CLEANING_AND_V_SLEEP_QUERY.value:
            result = AirConCleaningQueryResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.AIR_CON_CLEANING_AND_V_SLEEP_SETTING.value:
            result = AirConCleaningControlResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_DAIKIN_CARE_EXPONENT.value:
            result = DaikinCareExponentFeatureResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_GATEWAY_SIGNAL_CHECK.value:
            result = GatewaySignalResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == OfficialSystemCmd.AIR_CON_INLET_TEMP_AND_HUMIDITY_INFO_QUERY.value:
            result = AirConInletTempAndHumidityQueryResult(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SYS_SCHEDULE_QUERY_VERSION_V3:
            result = ScheduleQueryVersionV3Result(cnt, EnumDevice.SYSTEM)
        elif cmd_type == EnumCmdType.SENSOR2_INFO:
            result = Sensor2InfoResult(cnt, EnumDevice.SYSTEM)
        else:
            result = UnknownResult(cnt, EnumDevice.SYSTEM, cmd_type)
    elif dev_id == EnumDevice.NEWAIRCON.value[1] or dev_id == EnumDevice.AIRCON.value[1] \
            or dev_id == EnumDevice.BATHROOM.value[1] or dev_id == EnumDevice.SENSOR.value[1]:
        device = EnumDevice((8, dev_id))
        if cmd_type == EnumCmdType.STATUS_CHANGED.value:
            result = AirConStatusChangedResult(cnt, device)
        elif cmd_type == EnumCmdType.QUERY_STATUS.value:
            result = AirConQueryStatusResult(cnt, device)
        elif cmd_type == EnumCmdType.AIR_RECOMMENDED_INDOOR_TEMP.value:
            result = AirConRecommendedIndoorTempResult(cnt, device)
        elif cmd_type == EnumCmdType.AIR_CAPABILITY_QUERY.value:
            result = AirConCapabilityQueryResult(cnt, device)
        elif cmd_type == EnumCmdType.QUERY_SCENARIO_SETTING.value:
            result = AirConQueryScenarioSettingResult(cnt, device)
        elif cmd_type == EnumCmdType.SENSOR2_INFO.value:
            result = Sensor2InfoResult(cnt, device)
        else:
            result = UnknownResult(cnt, device, cmd_type)
    elif dev_id == EnumDevice.VENTILATION.value[1] or dev_id == EnumDevice.SMALL_VAM.value[1]:
        device = EnumDevice((8, dev_id))
        if cmd_type == EnumCmdType.STATUS_CHANGED.value:
            result = VentilationStatusChangedResult(cnt, device)
        elif cmd_type == EnumCmdType.QUERY_STATUS.value:
            result = VentilationQueryStatusResult(cnt, device)
        elif cmd_type == EnumCmdType.VENT_QUERY_CAPABILITY.value:
            result = VentilationCapabilityQueryResult(cnt, device)
        elif cmd_type == EnumCmdType.SMALL_VAM_QUERY_COMPOSITE_SITUATION.value:
            result = VentilationQueryCompositeSituationResult(cnt, device)
        else:
            result = UnknownResult(cnt, device, cmd_type)
    else:
        """ignore other device"""
        result = UnknownResult(cnt, EnumDevice.SYSTEM, cmd_type)

    result.subbody_ver = subbody_ver
    result.load_bytes(subbody)

    return result


class Decode:
    def __init__(self, b):
        self._b = b
        self._pos = 0

    def read1(self):
        if self.remaining < 1:
            raise ValueError("not enough bytes for u8")
        pos = self._pos
        s = struct.unpack('<B', self._b[pos:pos + 1])[0]
        pos += 1
        self._pos = pos
        return s

    def read2(self):
        if self.remaining < 2:
            raise ValueError("not enough bytes for u16")
        pos = self._pos
        s = struct.unpack('<H', self._b[pos:pos + 2])[0]
        pos += 2
        self._pos = pos
        return s

    def read4(self):
        if self.remaining < 4:
            raise ValueError("not enough bytes for u32")
        pos = self._pos
        s = struct.unpack('<I', self._b[pos:pos + 4])[0]
        pos += 4
        self._pos = pos
        return s

    def read(self, l):
        if l < 0 or self.remaining < l:
            raise ValueError("not enough bytes")
        pos = self._pos
        s = self._b[pos:pos + l]
        pos += l
        self._pos = pos
        return s

    def read_utf(self, l):
        if l < 0 or self.remaining < l:
            raise ValueError("not enough bytes for text")
        pos = self._pos
        try:
            s = self._b[pos:pos + l].decode('utf-8')
        except UnicodeDecodeError:
            s = None
        pos += l
        self._pos = pos
        return s

    @property
    def remaining(self):
        return len(self._b) - self._pos


class BaseResult(BaseBean):
    def __init__(self, cmd_id: int, targe: EnumDevice, cmd_type: EnumCmdType):
        BaseBean.__init__(self, cmd_id, targe, cmd_type)

    def load_bytes(self, b):
        """do nothing"""

    def do(self):
        """do nothing"""


class HeartbeatResult(BaseResult):
    def __init__(self):
        BaseResult.__init__(self, 0, EnumDevice.SYSTEM, EnumCmdType.SYS_ACK)


class AckResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_ACK)

    def load_bytes(self, b):
        # D611 uses an explicitly verified, immutable profile.  Legacy B/C
        # entries may learn this one compatibility bit from their first ACK,
        # but unrelated later ACKs must never change the parser layout.
        if b:
            Config.observe_protocol_ack(b[0])


class ScheduleQueryVersionV3Result(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_ACK)


class Sensor2InfoResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SENSOR2_INFO)
        self._count = 0
        self._mode = 0
        self._room_id = 0
        self._sensor_type = 0
        self._sensors: typing.List[Sensor] = []

    def load_bytes(self, b):
        data = Decode(b)
        self._mode = data.read1()
        count = data.read1()
        self._count = count
        while count > 0:
            self._room_id = data.read1()
            d = Decode(data.read(data.read1()))
            self._sensor_type = d.read1()
            unit_id = d.read1()
            sensor = Sensor()
            sensor.mac = d.read(6).hex()
            sensor.room_id = self._room_id
            sensor.unit_id = unit_id
            length = d.read1()
            sensor.alias = d.read_utf(length)
            sensor.name = sensor.alias
            sensor.type1 = d.read1()
            sensor.type2 = d.read1()
            humidity = UNINITIALIZED_VALUE
            hcho = UNINITIALIZED_VALUE
            temp = UNINITIALIZED_VALUE
            if (sensor.type1 & 1) == 1:
                temp = d.read2()
            if ((sensor.type1 >> 1) & 1) == 1:
                humidity = d.read2()
            pm25 = UNINITIALIZED_VALUE
            if (sensor.type1 >> 2) & 1 == 1:
                pm25 = d.read2()
            co2 = UNINITIALIZED_VALUE
            if (sensor.type1 >> 3) & 1 == 1:
                co2 = d.read2()
            voc = EnumSensor.Voc.STEP_UNUSE
            if (sensor.type1 >> 4) & 1 == 1:
                f = d.read1()
                voc = EnumSensor.Voc(f)
            tvoc = UNINITIALIZED_VALUE
            if (sensor.type1 >> 5) & 1 == 1:
                tvoc = d.read2()
            if (sensor.type1 >> 6) & 1 == 1:
                hcho = d.read2()
            switch_on_off = d.read1() == 1
            temp_upper = d.read2()
            temp_lower = d.read2()
            humidity_upper = d.read2()
            humidity_lower = d.read2()
            pm25_upper = d.read2()
            pm25_lower = d.read2()
            co2_upper = d.read2()
            co2_lower = d.read2()
            voc_lower = d.read1()
            tvoc_upper = d.read2()
            hcho_upper = d.read2()
            connected = d.read1() == 1
            sleep_mode_count = d.read1()
            sleep_mode_enable = False
            if sleep_mode_count > 0:
                sleep_mode_enable = d.read1() == 1
            sensor.sensor_type = self._sensor_type
            sensor.temp = temp
            sensor.humidity = humidity
            sensor.pm25 = pm25
            sensor.co2 = co2
            sensor.voc = voc
            if self._sensor_type == 3:
                sensor.tvoc = tvoc
                sensor.hcho = hcho
                sensor.tvoc_upper = tvoc_upper
                sensor.hcho_upper = hcho_upper
            sensor.switch_on_off = switch_on_off
            sensor.temp_upper = temp_upper
            sensor.temp_lower = temp_lower
            sensor.humidity_upper = humidity_upper
            sensor.humidity_lower = humidity_lower
            sensor.pm25_upper = pm25_upper
            sensor.pm25_lower = pm25_lower
            sensor.co2_upper = co2_upper
            sensor.co2_lower = co2_lower
            sensor.voc_lower = voc_lower
            sensor.connected = connected
            sensor.sleep_mode_count = sleep_mode_count
            self._sensors.append(sensor)
            count = count - 1

    def do(self):
        from .service import Service
        Service.set_sensors_status(self._sensors)

    @property
    def count(self):
        return self._count

    @property
    def mode(self):
        return self._mode

    @property
    def room_id(self):
        return self._room_id

    @property
    def sensor_type(self):
        return self._sensor_type

    @property
    def sensors(self):
        return self._sensors


class CmdRspResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_CMD_RSP)
        self._cmdId = None
        self._code = None

    def load_bytes(self, b):
        self._cmdId, self._code = struct.unpack('<IB', b)

    @property
    def cmd_id(self):
        return self._cmdId

    @property
    def code(self):
        return self._code


class TimeSyncResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_TIME_SYNC)
        self._time = None

    def load_bytes(self, b):
        self._time = struct.unpack('<I', b)[0]

    @property
    def time(self):
        return self._time


class ErrCodeResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_ERR_CODE)
        self._code = None
        self._normalized_code = None
        self._device = None
        self._device_id = None
        self._room = None
        self._level = None
        self._valid = False
        self._source_timestamp = None

    def load_bytes(self, b):
        try:
            d = Decode(b)
            self._device_id = struct.unpack("<i", d.read(4))[0]
            try:
                self._device = EnumDevice((8, self._device_id))
            except ValueError:
                self._device = None
            self._room = d.read1()
            d.read1()  # Reserved by the official decoder.
            level_data = d.read(d.read1())
            self._level = level_data[0] if len(level_data) == 1 else 1
            d.read(d.read1())  # Source description is intentionally not exposed.
            self._code = d.read(d.read1()).decode("ascii")
            self._normalized_code = "00" if self._code in ("AF", "U4") else self._code
            self._source_timestamp = time.time()
            self._valid = True
        except (UnicodeDecodeError, ValueError, struct.error):
            self._valid = False

    def do(self):
        if not self._valid:
            return
        from .service import Service
        Service.set_error_info(
            code_raw=self._code,
            code_normalized=self._normalized_code,
            device_id=self._device_id,
            device=self._device,
            room=self._room,
            level=self._level,
            source_timestamp=self._source_timestamp,
        )

    @property
    def code(self):
        return self._code

    @property
    def normalized_code(self):
        return self._normalized_code

    @property
    def device(self):
        return self._device

    @property
    def device_id(self):
        return self._device_id

    @property
    def room(self):
        return self._room

    @property
    def level(self):
        return self._level

    @property
    def unit(self):
        """Backward-compatible alias for the formerly misnamed level byte."""
        return self._level

    @property
    def valid(self):
        return self._valid


class GetWeatherResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_GET_WEATHER)
        self._condition = None
        self._humidity = None
        self._temp = None
        self._wind_dire = None
        self._wind_speed = None

    def load_bytes(self, b):
        self._condition, self._humidity, self._temp, self._wind_dire, self._wind_speed \
            = struct.unpack('<BBHBB', b)

    @property
    def condition(self):
        return self._condition

    @property
    def humidity(self):
        return self._humidity

    @property
    def temp(self):
        return self._temp

    @property
    def wind_dire(self):
        return self._wind_dire

    @property
    def wind_speed(self):
        return self._wind_speed


class LoginResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_LOGIN)
        self._status = None

    def load_bytes(self, b):
        self._status = struct.unpack('<BB', b)[1]

    @property
    def status(self):
        return self._status


class ChangePWResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_CHANGE_PW)
        self._status = None

    def load_bytes(self, b):
        self._status = struct.unpack('<B', b)[0]

    @property
    def status(self):
        return self._status


class GetRoomInfoResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_GET_ROOM_INFO)
        self._count: int = 0
        self._hds: typing.List[HD] = []
        self._sensors: typing.List[Sensor] = []
        self._rooms: typing.List[Room] = []

    def load_bytes(self, b):
        ver_flag = 1
        d = Decode(b)
        self._count = d.read2()
        room_count = d.read1()
        for i in range(room_count):
            room = Room()
            room.id = d.read2()
            if self.subbody_ver == 1:
                ver_flag = d.read1()
            if ver_flag != 2:
                length = d.read1()
                room.name = d.read_utf(length)
                length = d.read1()
                room.alias = d.read_utf(length)
                length = d.read1()
                room.icon = d.read_utf(length)
            unit_count = d.read2()
            for j in range(unit_count):
                device = EnumDevice((8, d.read4()))
                device_count = d.read2()
                for unit_id in range(device_count):
                    if EnumDevice.AIRCON == device or EnumDevice.NEWAIRCON == device or EnumDevice.BATHROOM == device:
                        dev = AirCon()
                        room.air_con = dev
                        dev.new_air_con = EnumDevice.NEWAIRCON == device
                        dev.bath_room = EnumDevice.BATHROOM == device
                    elif EnumDevice.GEOTHERMIC == device:
                        dev = Geothermic()
                        room.geothermic = dev
                    elif EnumDevice.HD == device:
                        dev = HD()
                        self.hds.append(dev)
                        room.hd_room = True
                        room.hd = dev
                    elif EnumDevice.SENSOR == device:
                        dev = Sensor()
                        self.sensors.append(dev)
                        room.sensor_room = True
                    elif EnumDevice.VENTILATION == device or EnumDevice.SMALL_VAM == device:
                        dev = Ventilation()
                        room.ventilation = dev
                        room.ventilations.append(dev)
                        dev.is_small_vam = EnumDevice.SMALL_VAM == device
                    else:
                        dev = Device()
                    dev.room_id = room.id
                    dev.unit_id = unit_id
                    if ver_flag > 2:
                        length = d.read1()
                        dev.name = d.read_utf(length)
                        length = d.read1()
                        dev.alias = d.read_utf(length)
                        if dev.alias is None:
                            dev.alias = room.alias
            self.rooms.append(room)

    def do(self):
        from .service import Service
        Service.set_rooms(self.rooms)
        Service.send_msg(AirConRecommendedIndoorTempParam())
        Service.set_sensors(self.sensors)

        aircons = []
        new_aircons = []
        bathrooms = []
        vents = []
        small_vams = []
        for room in Service.get_rooms():
            if room.air_con is not None:
                room.air_con.alias = room.alias
                if room.air_con.new_air_con:
                    new_aircons.append(room.air_con)
                elif room.air_con.bath_room:
                    bathrooms.append(room.air_con)
                else:
                    aircons.append(room.air_con)
            for ventilation in room.ventilations:
                ventilation.alias = room.alias
                if ventilation.is_small_vam:
                    small_vams.append(ventilation)
                else:
                    vents.append(ventilation)

        p = AirConCapabilityQueryParam()
        p.aircons = aircons
        p.target = EnumDevice.AIRCON
        Service.send_msg(p)
        p = AirConCapabilityQueryParam()
        p.aircons = new_aircons
        p.target = EnumDevice.NEWAIRCON
        Service.send_msg(p)
        p = AirConCapabilityQueryParam()
        p.aircons = bathrooms
        p.target = EnumDevice.BATHROOM
        Service.send_msg(p)
        Service.set_device(EnumDevice.VENTILATION, vents)
        Service.set_device(EnumDevice.SMALL_VAM, small_vams)
        if vents:
            p = VentilationCapabilityQueryParam()
            p.vents = vents
            p.target = EnumDevice.VENTILATION
            Service.send_msg(p)
        if small_vams:
            p = VentilationCapabilityQueryParam()
            p.vents = small_vams
            p.target = EnumDevice.SMALL_VAM
            Service.send_msg(p)
        for vent in vents + small_vams:
            p = VentilationQueryStatusParam()
            p.target = get_device_by_vent(vent)
            p.device = vent
            Service.send_msg(p)

    @property
    def count(self):
        return self._count

    @property
    def hds(self):
        return self._hds

    @property
    def rooms(self):
        return self._rooms

    @property
    def sensors(self):
        return self._sensors


class QueryScheduleSettingResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_QUERY_SCHEDULE_SETTING)

    def load_bytes(self, b):
        """todo"""


class QueryScheduleIDResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_QUERY_SCHEDULE_ID)

    def load_bytes(self, b):
        """todo"""


class HandShakeResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_HAND_SHAKE)
        self._time: str = ''

    def load_bytes(self, b):
        d = Decode(b)
        self._time = d.read_utf(14)

    def do(self):
        p = GetRoomInfoParam()
        p.room_ids.append(0xffff)
        from .service import Service
        Service.send_msg(p)
        Service.send_msg(Sensor2InfoParam())


class GetGWInfoResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_GET_GW_INFO)
        self.gateway_version = None
        self.wifi_version = None
        self.gateway_time = None
        self.source_timestamp = None
        self.valid = False

    def load_bytes(self, b):
        try:
            d = Decode(b)

            def read_sized_bytes():
                return d.read(d.read1())

            self.gateway_version = read_sized_bytes().decode("ascii")
            d.read1()  # DHCP mode; not needed for the diagnostic entity.
            d.read(6)  # MAC address is deliberately discarded.
            for _ in range(5):
                read_sized_bytes()  # IP/mask/gateway/DNS values are discarded.

            gateway_time = d.read(d.read1())
            if len(gateway_time) >= 7:
                year = gateway_time[0] | gateway_time[1] << 8
                self.gateway_time = (
                    f"{year:04d}-{gateway_time[2]:02d}-{gateway_time[3]:02d} "
                    f"{gateway_time[4]:02d}:{gateway_time[5]:02d}:{gateway_time[6]:02d}"
                )

            for _ in range(3):
                read_sized_bytes()  # Area/distributor fields are sensitive and discarded.

            if d.remaining:
                self.wifi_version = read_sized_bytes().decode("ascii")
            self.source_timestamp = time.time()
            self.valid = True
        except (UnicodeDecodeError, ValueError, struct.error):
            self.valid = False

    def do(self):
        if not self.valid:
            return
        from .service import Service
        Service.set_gateway_info(
            gateway_version=self.gateway_version,
            wifi_version=self.wifi_version,
            gateway_time=self.gateway_time,
            source_timestamp=self.source_timestamp,
        )


class GatewaySignalResult(BaseResult):
    """Non-sensitive Wi-Fi signal result for system command 234."""

    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_GATEWAY_SIGNAL_CHECK)
        self.signal_strength = None
        self.ping_success_count = None
        self.network_delay = None
        self.raw = None
        self.source_timestamp = None
        self.valid = False

    def load_bytes(self, b):
        if len(b) != 4:
            return
        signal_strength, ping_success_count, network_delay = struct.unpack("<bbH", b)
        self.raw = b.hex()
        self.signal_strength = None if signal_strength == 127 else signal_strength
        self.ping_success_count = ping_success_count
        self.network_delay = None if network_delay == 32767 else network_delay
        self.source_timestamp = time.time()
        self.valid = True

    def do(self):
        if not self.valid:
            return
        from .service import Service
        Service.set_gateway_signal(
            signal_strength=self.signal_strength,
            ping_success_count=self.ping_success_count,
            network_delay=self.network_delay,
            raw=self.raw,
            source_timestamp=self.source_timestamp,
        )


class FilterServiceLifeResult(BaseResult):
    """Decode the official local cmd10 VAM filter-used percentages."""

    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_FILTER_SERVICE_LIFE)
        self.has_data = False
        self.valid = False
        self.items = []
        self.source_timestamp = None

    def load_bytes(self, b):
        try:
            d = Decode(b)
            count = d.read1()
            for _ in range(count):
                reserved_before_room = d.read1()
                room = d.read1()
                reserved_before_percent = d.read1()
                used_percent_raw = d.read1()
                self.items.append({
                    "room": room,
                    "used_percent": (
                        None if used_percent_raw == 0xFF else used_percent_raw
                    ),
                    "used_percent_raw": used_percent_raw,
                    "reserved_before_room": reserved_before_room,
                    "reserved_before_percent": reserved_before_percent,
                })
            if d.remaining != 0:
                return
            self.valid = True
            self.has_data = count > 0
            self.source_timestamp = time.time()
        except ValueError:
            self.valid = False

    def do(self):
        if self.valid:
            from .service import Service
            Service.set_filter_service_life(
                self.items, source_timestamp=self.source_timestamp
            )
            Service.set_feature_support(
                "filter_service_life", source_timestamp=self.source_timestamp
            )


class FilterCleanSignResult(BaseResult):
    """Decode the official local cmd9 filter-clean reminder notification."""

    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_FILTER_CLEAN_SIGN)
        self.device_id = None
        self.device = None
        self.room = None
        self.status = None
        self.source_timestamp = None
        self.valid = False

    def load_bytes(self, b):
        try:
            d = Decode(b)
            self.device_id = struct.unpack("<i", d.read(4))[0]
            try:
                self.device = EnumDevice((8, self.device_id))
            except ValueError:
                self.device = None
            self.room = d.read1()
            d.read1()  # Reserved by the official decoder.
            self.status = d.read1()
            if d.remaining != 0:
                return
            self.source_timestamp = time.time()
            self.valid = True
        except (ValueError, struct.error):
            self.valid = False

    def do(self):
        if not self.valid:
            return
        from .service import Service
        Service.set_filter_clean_sign(
            device_id=self.device_id,
            device=self.device,
            room=self.room,
            status=self.status,
            source_timestamp=self.source_timestamp,
        )


class DaikinCareExponentFeatureResult(BaseResult):
    """Validate command 220 for feature detection only."""

    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_DAIKIN_CARE_EXPONENT)
        self.has_data = False
        self.valid = False
        self.source_timestamp = None

    def load_bytes(self, b):
        try:
            d = Decode(b)
            d.read1()  # Unmapped global flag; intentionally not exposed.
            d.read1()  # Global Air View switch; no entity is created here.
            room_count = d.read1()
            for _ in range(room_count):
                d.read1()
                d.read(4)
                d.read1()
                terminated = False
                while d.remaining:
                    key = d.read1()
                    if key == 0:
                        terminated = True
                        break
                    d.read(d.read1())
                if not terminated:
                    return
            if d.remaining != 0:
                return
            self.valid = True
            self.has_data = room_count > 0
            self.source_timestamp = time.time()
        except ValueError:
            self.valid = False

    def do(self):
        if self.valid:
            from .service import Service
            Service.set_feature_support(
                "daikin_care_exponent", source_timestamp=self.source_timestamp
            )


class CmdTransferResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_CMD_TRANSFER)

    def load_bytes(self, b):
        """todo"""


class AirConInletTempAndHumidityQueryResult(BaseResult):
    """Decode official App cmd243 without naming unproven TLV keys."""

    _TEMPERATURE_REASONABLE_RANGE_C = (-40.0, 85.0)
    _HUMIDITY_REASONABLE_RANGE_PERCENT = (0.0, 100.0)

    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(
            self,
            cmd_id,
            target,
            OfficialSystemCmd.AIR_CON_INLET_TEMP_AND_HUMIDITY_INFO_QUERY,
        )
        self._items = []

    def load_bytes(self, b):
        d = Decode(b)
        if d.remaining < 1:
            return

        count = d.read1()
        for _ in range(count):
            if d.remaining < 1:
                break

            item = {
                "room": d.read1(),
                "inlet_raw_tlvs": [],
                "inlet_parse_status": "complete",
                "source_timestamp": time.time(),
            }
            terminated = False
            while d.remaining:
                key = d.read1()
                if key == 0:
                    terminated = True
                    break
                if d.remaining < 1:
                    item["inlet_parse_status"] = "missing_length"
                    break
                length = d.read1()
                if length > d.remaining:
                    raw = d.read(d.remaining)
                    item["inlet_parse_status"] = "truncated"
                else:
                    raw = d.read(length)
                item["inlet_raw_tlvs"].append(
                    {"key": key, "length": length, "raw": raw.hex()}
                )

                if len(raw) == length:
                    if key == 1 and length == 2:
                        value = struct.unpack("<h", raw)[0] / 10.0
                        item["inlet_temperature_c"] = value
                        low, high = self._TEMPERATURE_REASONABLE_RANGE_C
                        item["inlet_temperature_quality"] = (
                            "valid" if low <= value <= high else "out_of_range"
                        )
                    elif key == 2 and length == 2:
                        value = struct.unpack("<h", raw)[0] / 10.0
                        item["inlet_humidity_percent"] = value
                        low, high = self._HUMIDITY_REASONABLE_RANGE_PERCENT
                        item["inlet_humidity_quality"] = (
                            "valid" if low <= value <= high else "out_of_range"
                        )

                if len(raw) < length:
                    break

            if not terminated and item["inlet_parse_status"] == "complete":
                item["inlet_parse_status"] = "missing_terminator"

            # Malformed records remain visible as raw evidence, but their
            # semantic values must never replace last confirmed observations.
            if item["inlet_parse_status"] != "complete":
                item.pop("inlet_temperature_c", None)
                item.pop("inlet_humidity_percent", None)
                item.pop("inlet_temperature_quality", None)
                item.pop("inlet_humidity_quality", None)
            else:
                item.setdefault("inlet_temperature_quality", "missing")
                item.setdefault("inlet_humidity_quality", "missing")

            self._items.append(item)

    def do(self):
        complete_items = [
            item for item in self._items
            if item.get("inlet_parse_status") == "complete"
        ]
        if complete_items:
            from .service import Service

            Service.set_aircon_inlet_observations(complete_items)

    @property
    def items(self):
        return self._items


class AirConCleaningQueryResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.AIR_CON_CLEANING_AND_V_SLEEP_QUERY)
        self._items = []

    def load_bytes(self, b):
        d = Decode(b)
        if d.remaining < 1:
            return

        count = d.read1()
        if count == 255:
            return

        for _ in range(count):
            if d.remaining < 3:
                break

            item = {
                "room": d.read1(),
                "protocol_header_raw": d.read(2).hex(),
                "heat_exchange_cleaning_raw_tlvs": [],
                "heat_exchange_cleaning_parse_status": "complete",
                "source_timestamp": time.time(),
            }

            terminated = False
            while d.remaining > 0:
                key = d.read1()
                if key == 0:
                    terminated = True
                    break
                if d.remaining < 1:
                    item["heat_exchange_cleaning_parse_status"] = "missing_length"
                    break
                length = d.read1()
                if length > d.remaining:
                    raw = d.read(d.remaining)
                    item["heat_exchange_cleaning_parse_status"] = "truncated"
                else:
                    raw = d.read(length)
                item["heat_exchange_cleaning_raw_tlvs"].append(
                    {"key": key, "length": length, "raw": raw.hex()}
                )

                if len(raw) == length:
                    if key == 4 and length == 1:
                        item["heat_exchange_cleaning_capability"] = raw[0]
                    elif key == 5 and length == 1:
                        item["heat_exchange_cleaning_can_join"] = raw[0]
                    elif key == 6 and length == 1:
                        item["heat_exchange_cleaning_work_state"] = raw[0]
                    elif key == 7 and length == 2:
                        item["heat_exchange_cleaning_phase_duration"] = int.from_bytes(raw, "little")
                    elif key == 8 and length == 2:
                        item["heat_exchange_cleaning_v_sleep_value_1"] = raw[0]
                        item["heat_exchange_cleaning_v_sleep_value_2"] = raw[1]
                    elif key == 14 and length == 1:
                        item["heat_exchange_cleaning_finish"] = raw[0]
                    elif key == 15 and length == 1:
                        item["heat_exchange_cleaning_outdoor_status"] = raw[0]
                    elif key in (16, 17, 18, 19, 20):
                        expected_length = 2 if key == 19 else 1
                        if length == expected_length:
                            if key == 18:
                                low_nibble = raw[0] & 0x0F
                                value = 1 if raw[0] & 0x80 and low_nibble == 0 else low_nibble
                            else:
                                value = int.from_bytes(raw, "little")
                            item[f"vam_cleaning_tlv_{key}"] = value
                            item["vam_cleaning_semantic_status"] = "unmapped"

                if length > len(raw):
                    break

            if not terminated and item["heat_exchange_cleaning_parse_status"] == "complete":
                item["heat_exchange_cleaning_parse_status"] = "missing_terminator"

            if item["heat_exchange_cleaning_parse_status"] != "complete":
                evidence_keys = {
                    "room",
                    "protocol_header_raw",
                    "heat_exchange_cleaning_raw_tlvs",
                    "heat_exchange_cleaning_parse_status",
                    "source_timestamp",
                }
                for field in list(item):
                    if field not in evidence_keys:
                        del item[field]

            self._items.append(item)

    def do(self):
        from .service import Service
        Service.set_cleaning_info(self._items)

    @property
    def items(self):
        return self._items


class AirConCleaningControlResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.AIR_CON_CLEANING_AND_V_SLEEP_SETTING)
        self.success = None
        self.code = None

    def load_bytes(self, b):
        if len(b) < 2:
            return
        d = Decode(b)
        self.success = d.read1() == 0
        self.code = d.read1()

    def do(self):
        # Query authoritative state only after the gateway accepted cmd36.
        if self.success:
            from .service import Service
            Service.send_msg(AirConCleaningQueryParam())


class QueryScheduleFinish(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SYS_QUERY_SCHEDULE_FINISH)

    def load_bytes(self, b):
        """todo"""


class AirConStatusChangedResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.STATUS_CHANGED)
        self._room = 0  # type: int
        self._unit = 0  # type: int
        self._status = AirConStatus()  # type: AirConStatus

    def load_bytes(self, b):
        d = Decode(b)
        self._room = d.read1()
        self._unit = d.read1()
        status = self._status
        flag = d.read1()
        if flag & EnumControl.Type.SWITCH:
            status.switch = EnumControl.Switch(d.read1())
        if flag & EnumControl.Type.MODE:
            status.mode = EnumControl.Mode(d.read1())
        if flag & EnumControl.Type.AIR_FLOW:
            status.air_flow = EnumControl.AirFlow(d.read1())
        if flag & EnumControl.Type.CURRENT_TEMP:
            # Official AirConStatusChangeDTO (cmd2), like cmd3, defines bit 3
            # as one reserved byte.  Never publish it as a temperature.
            d.read1()
        if flag & EnumControl.Type.SETTED_TEMP:
            status.setted_temp = d.read2()
        if Config.is_new_version:
            if flag & EnumControl.Type.FAN_DIRECTION:
                direction = d.read1()
                status.fan_direction1 = EnumControl.FanDirection(direction & 0xF)
                status.fan_direction2 = EnumControl.FanDirection((direction >> 4) & 0xF)
            if flag & EnumControl.Type.HUMIDITY:
                status.humidity = EnumControl.Humidity(d.read1())
            if flag & EnumControl.Type.BREATHE:
                status.breathe = EnumControl.Breathe(d.read1())

    def do(self):
        from .service import Service
        Service.update_aircon(self.target, self._room, self._unit, status=self._status)


class AirConQueryStatusResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.QUERY_STATUS)
        self.unit = 0
        self.room = 0
        # QUERY_STATUS is a bitmask-based partial response.  Keep every
        # optional field unknown until its flag is actually present; using
        # protocol-looking defaults here fabricates OFF/AUTO/0 updates and can
        # overwrite the last real state when a device sends a partial packet.
        self.current_temp = None
        self.setted_temp = None
        self.switch = None
        self.air_flow = None
        self.breathe = None
        self.fan_direction1 = None
        self.fan_direction2 = None
        self.humidity = None
        self.mode = None
        self.hum_allow = None
        self.fresh_air_allow = None
        self.fresh_air_humidification = None
        self.three_d_fresh = None

    def load_bytes(self, b):
        d = Decode(b)
        self.room = d.read1()
        self.unit = d.read1()
        flag = d.read1()
        if flag & 1:
            self.switch = EnumControl.Switch(d.read1())
        if flag >> 1 & 1:
            self.mode = EnumControl.Mode(d.read1())
        if flag >> 2 & 1:
            self.air_flow = EnumControl.AirFlow(d.read1())
        if Config.is_c611:
            if flag >> 3 & 1:
                bt = d.read1()
                self.hum_allow = bt & 8 == 8
                self.fresh_air_allow = bt & 4 == 4
                self.fresh_air_humidification = FreshAirHumidification(bt & 3)

            if flag >> 4 & 1:
                self.setted_temp = d.read2()
            if Config.is_new_version:
                if flag >> 5 & 1:
                    b = d.read1()
                    self.fan_direction1 = EnumControl.FanDirection(b & 0xf)
                    self.fan_direction2 = EnumControl.FanDirection(b >> 4 & 0xf)
                if flag >> 6 & 1:
                    self.humidity = EnumControl.Humidity(d.read1())
                if self.target == EnumDevice.BATHROOM:
                    if flag >> 7 & 1:
                        self.breathe = EnumControl.Breathe(d.read1())
                elif self.target == EnumDevice.AIRCON:
                    if flag >> 7 & 1 == 1:
                        self.three_d_fresh = ThreeDFresh(d.read1())
        else:
            if flag >> 3 & 1:
                # In the official AirConStatusQueryDTO used by DTA117D611,
                # bit 3 is one reserved byte.  It is not a temperature.  The
                # former two-byte read both fabricated a value and shifted
                # every following field by one byte.
                d.read1()
            if flag >> 4 & 1:
                self.setted_temp = d.read2()
            if Config.is_new_version:
                if flag >> 5 & 1:
                    b = d.read1()
                    self.fan_direction1 = EnumControl.FanDirection(b & 0xf)
                    self.fan_direction2 = EnumControl.FanDirection(b >> 4 & 0xf)
                if self.target == EnumDevice.NEWAIRCON:
                    if flag >> 6 & 1:
                        self.humidity = EnumControl.Humidity(d.read1())
                else:
                    if flag >> 7 & 1:
                        self.breathe = EnumControl.Breathe(d.read1())

    def do(self):
        from .service import Service
        status = AirConStatus(self.current_temp, self.setted_temp, self.switch, self.air_flow, self.breathe,
                              self.fan_direction1, self.fan_direction2, self.humidity, self.mode)
        Service.set_aircon_status(self.target, self.room, self.unit, status)


class AirConRecommendedIndoorTempResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.AIR_RECOMMENDED_INDOOR_TEMP)
        self._temp: int = 0
        self._outdoor_temp: int = 0

    def load_bytes(self, b):
        d = Decode(b)
        self._temp = d.read2()
        self._outdoor_temp = d.read2()

    @property
    def temp(self):
        return self._temp

    @property
    def outdoor_temp(self):
        return self._outdoor_temp


class AirConCapabilityQueryResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.AIR_CAPABILITY_QUERY)
        self._air_cons: typing.List[AirCon] = []

    def load_bytes(self, b):
        d = Decode(b)
        room_size = d.read1()
        for i in range(room_size):
            room_id = d.read1()
            unit_size = d.read1()
            for j in range(unit_size):
                aircon = AirCon()
                aircon.unit_id = d.read1()
                aircon.room_id = room_id
                aircon.new_air_con = self.target == EnumDevice.NEWAIRCON
                aircon.bath_room = self.target == EnumDevice.BATHROOM
                flag = d.read1()
                aircon.fan_volume = EnumFanVolume(flag >> 5 & 0x7)
                aircon.dry_mode = flag >> 4 & 1
                aircon.auto_mode = flag >> 3 & 1
                aircon.heat_mode = flag >> 2 & 1
                aircon.cool_mode = flag >> 1 & 1
                aircon.ventilation_mode = flag & 1
                if Config.is_new_version:
                    flag = d.read1()
                    if flag & 1:
                        aircon.fan_direction1 = EnumFanDirection.STEP_5
                    else:
                        aircon.fan_direction1 = EnumFanDirection.FIX

                    if flag >> 1 & 1:
                        aircon.fan_direction2 = EnumFanDirection.STEP_5
                    else:
                        aircon.fan_direction2 = EnumFanDirection.FIX

                    aircon.fan_dire_auto = flag >> 2 & 1
                    aircon.fan_volume_auto = flag >> 3 & 1
                    aircon.temp_set = flag >> 4 & 1
                    aircon.hum_fresh_air_allow = (flag >> 5 & 1) & (flag >> 6 & 1)
                    aircon.three_d_fresh_allow = flag >> 7 & 1

                    flag = d.read1()
                    aircon.out_door_run_cond = EnumOutDoorRunCond(flag >> 6 & 3)
                    aircon.fan_volume_mute = bool(flag >> 5 & 1)
                    aircon.more_dry_mode = flag >> 4 & 1
                    aircon.pre_heat_mode = flag >> 3 & 1
                    aircon.sleep_mode = flag >> 2 & 1
                    aircon.relax_mode = flag >> 1 & 1
                    aircon.auto_dry_mode = flag & 1
                else:
                    d.read1()
                self._air_cons.append(aircon)

    def do(self):
        from .service import Service
        if Service.is_ready():
            if len(self._air_cons):
                for i in self._air_cons:
                    Service.update_aircon(get_device_by_aircon(i), i.room_id, i.unit_id, aircon=i)
        else:
            for i in self._air_cons:
                p = AirConQueryStatusParam()
                p.target = self.target
                p.device = i
                from .service import Service
                Service.send_msg(p)
            Service.set_device(self.target, self._air_cons)

    @property
    def aircons(self):
        return self._air_cons


class AirConQueryScenarioSettingResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.QUERY_SCENARIO_SETTING)

    def load_bytes(self, b):
        """todo"""


class VentilationStatusChangedResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.STATUS_CHANGED)
        self._room = 0
        self._unit = 0
        self._status = VentilationStatus()

    def load_bytes(self, b):
        d = Decode(b)
        self._room = d.read1()
        self._unit = d.read1()
        status = self._status
        flag = d.read1()
        if flag & EnumControl.Type.SWITCH:
            status.switch = EnumControl.Switch(d.read1())
        if flag & EnumControl.Type.MODE:
            status.mode = EnumControl.Mode(d.read1())
        if flag & EnumControl.Type.AIR_FLOW:
            status.air_flow = EnumControl.AirFlow(d.read1())

    def do(self):
        from .service import Service
        Service.update_ventilation(self.target, self._room, self._unit, status=self._status)


class VentilationCapabilityQueryResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.VENT_QUERY_CAPABILITY)
        self._vents = []

    def load_bytes(self, b):
        d = Decode(b)
        room_size = d.read1()
        for _i in range(room_size):
            room_id = d.read1()
            unit_size = d.read1()
            for _j in range(unit_size):
                vent = Ventilation()
                vent.room_id = room_id
                vent.unit_id = d.read1()
                vent.is_small_vam = self.target == EnumDevice.SMALL_VAM
                vent.capability = d.read1()
                self._vents.append(vent)

    def do(self):
        from .service import Service
        for i in self._vents:
            Service.set_ventilation_capability(i)
            if Service.is_ready():
                Service.update_ventilation(get_device_by_vent(i), i.room_id, i.unit_id, vent=i)


class VentilationQueryStatusResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.QUERY_STATUS)
        self._room = 0
        self._unit = 0
        self._status = VentilationStatus()

    def load_bytes(self, b):
        d = Decode(b)
        self._room = d.read1()
        self._unit = d.read1()
        status = self._status
        flag = d.read1()
        if flag & EnumControl.Type.SWITCH:
            status.switch = EnumControl.Switch(d.read1())
        if flag & EnumControl.Type.MODE:
            status.mode = EnumControl.Mode(d.read1())
        if flag & EnumControl.Type.AIR_FLOW:
            status.air_flow = EnumControl.AirFlow(d.read1())

    def do(self):
        from .service import Service
        Service.set_ventilation_status(self.target, self._room, self._unit, self._status)


class VentilationQueryCompositeSituationResult(BaseResult):
    """Preserve cmd52 evidence without publishing unverified sensor semantics.

    The official MiniVAM decoder has a seven-byte header after room/reserved
    and treats key 0 as a one-byte terminator.  Only TLV key 5 is currently
    proven to be a signed temperature in tenths; keys 1-4 are intentionally
    left unnamed.  This result is not polled and ``do`` is deliberately a
    no-op so a partial or misunderstood response cannot overwrite live VAM
    state.
    """

    def __init__(self, cmd_id: int, target: EnumDevice):
        BaseResult.__init__(self, cmd_id, target, EnumCmdType.SMALL_VAM_QUERY_COMPOSITE_SITUATION)
        self._room = 0
        self._reserved = 0
        self._service_code_raw = ""
        self._header_raw = ""
        self._raw_tlvs = []
        self._temperature = None
        self._trailing_raw = ""
        self._parse_status = "unknown"

    def load_bytes(self, b):
        d = Decode(b)
        if d.remaining < 9:
            self._parse_status = "truncated_header"
            self._trailing_raw = d.read(d.remaining).hex()
            return

        self._room = d.read1()
        self._reserved = d.read1()
        self._service_code_raw = d.read(4).hex()
        self._header_raw = d.read(3).hex()

        while d.remaining:
            status_type = d.read1()
            if status_type == 0:
                self._parse_status = "complete"
                self._trailing_raw = d.read(d.remaining).hex()
                return
            if d.remaining < 1:
                self._parse_status = "truncated_tlv_length"
                return
            status_size = d.read1()
            if status_size > d.remaining:
                raw = d.read(d.remaining)
                self._raw_tlvs.append(
                    {"key": status_type, "length": status_size, "raw": raw.hex()}
                )
                self._parse_status = "truncated_tlv_value"
                return

            raw = d.read(status_size)
            self._raw_tlvs.append(
                {"key": status_type, "length": status_size, "raw": raw.hex()}
            )
            if status_type == 5 and status_size == 2:
                self._temperature = struct.unpack("<h", raw)[0] / 10

        self._parse_status = "missing_terminator"

    def do(self):
        return None


class UnknownResult(BaseResult):
    def __init__(self, cmd_id: int, target: EnumDevice, cmd_type: EnumCmdType):
        BaseResult.__init__(self, cmd_id, target, cmd_type)
        self._subbody = ''

    def load_bytes(self, b):
        self._subbody = struct.pack('<' + str(len(b)) + 's', b).hex()

    @property
    def subbody(self):
        return self._subbody

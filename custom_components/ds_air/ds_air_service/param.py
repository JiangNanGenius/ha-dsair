import struct
import typing
from enum import IntEnum
from typing import Optional

from .config import Config
from .dao import AirCon, Device, get_device_by_aircon, AirConStatus, Ventilation, VentilationStatus, get_device_by_vent
from .base_bean import BaseBean
from .ctrl_enum import EnumCmdType, EnumDevice, EnumControl, EnumFanDirection, EnumFanVolume


class OfficialSystemCmd(IntEnum):
    """Official-app system commands absent from the legacy integration enum."""

    AIR_CON_INLET_TEMP_AND_HUMIDITY_INFO_QUERY = 243


class Encode:
    def __init__(self):
        self._fmt = '<'
        self._len = 0
        self._list = []

    def write1(self, d):
        self._fmt += 'B'
        self._len += 1
        self._list.append(d)

    def write2(self, d):
        self._fmt += 'H'
        self._len += 2
        self._list.append(d)

    def write4(self, d):
        self._fmt += 'I'
        self._len += 4
        self._list.append(d)

    def writes(self, d):
        self._fmt += str(len(d)) + 's'
        self._len += len(d)

    def pack(self, rewrite_length: bool = True):
        if rewrite_length:
            self._list[1] = self._len - 4
        return struct.pack(self._fmt, *self._list)

    @property
    def len(self):
        return self._len


class Param(BaseBean):
    cnt = 0

    def __init__(self, device_type: EnumDevice, cmd_type: EnumCmdType, has_result: bool):
        Param.cnt += 1
        BaseBean.__init__(self, Param.cnt, device_type, cmd_type)
        self._has_result = has_result

    def generate_subbody(self, s):
        return

    def to_string(self):
        s = Encode()
        s.write1(2)  # 0 保留字
        s.write2(16)  # 1~2 长度，不含首尾保留字及长度本身
        s.write1(13)  # 3 保留字
        s.write1(0)  # 4 保留字
        s.write1(self.subbody_ver)  # 5 子体版本
        s.write1(0)  # 6 保留字
        s.write4(self.cmd_id)  # 7~10 自增命令ID
        s.write1(self.target.value[0])  # 11 设备类型
        s.write4(self.target.value[1])  # 12~15 设备类型id
        s.write1(self.need_ack)  # 16 是否需要ack
        s.write2(self.cmd_type.value)  # 17~18 命令类型id
        self.generate_subbody(s)
        s.write1(3)  # 最后一位 保留字
        return s.pack()

    @property
    def has_result(self):
        return self._has_result


class HeartbeatParam(Param):
    def __init__(self):
        super().__init__(EnumDevice.SYSTEM, EnumCmdType.SYS_ACK, False)

    def to_string(self):
        s = Encode()
        s.write1(2)
        s.write2(0)
        s.write1(3)
        return s.pack()


class SystemParam(Param):
    def __init__(self, cmd_type, has_result):
        Param.__init__(self, EnumDevice.SYSTEM, cmd_type, has_result)


class HandShakeParam(SystemParam):
    def __init__(self):
        SystemParam.__init__(self, EnumCmdType.SYS_HAND_SHAKE, True)


class GetGWInfoParam(SystemParam):
    def __init__(self):
        SystemParam.__init__(self, EnumCmdType.SYS_GET_GW_INFO, True)


class GatewaySignalQueryParam(SystemParam):
    """Request gateway Wi-Fi link diagnostics (command 234)."""

    def __init__(self, target: int = 0):
        SystemParam.__init__(self, EnumCmdType.SYS_GATEWAY_SIGNAL_CHECK, True)
        self._signal_target = target

    def generate_subbody(self, s):
        s.write1(self._signal_target)


class FilterServiceLifeQueryParam(SystemParam):
    """Feature-detection query for command 10; no values are synthesized."""

    def __init__(self):
        SystemParam.__init__(self, EnumCmdType.SYS_FILTER_SERVICE_LIFE, True)


class FilterCleanSignResetParam(SystemParam):
    """Reset local filter-clean reminder bits for one room (official cmd21)."""

    def __init__(self, device: AirCon, filter_status: int = 7):
        SystemParam.__init__(
            self, EnumCmdType.SYS_FILTER_CLEAN_SIGN_RESET, True
        )
        self._device = device
        # Official App accepts individual 1/2/4 flags and uses 7 for reset-all.
        self._filter_status = filter_status if filter_status in (1, 2, 4) else 7

    def generate_subbody(self, s):
        s.write4(get_device_by_aircon(self._device).value[1])
        s.write1(int(self._device.room_id))
        s.write1(0)  # Reserved by the official DTO.
        s.write1(self._filter_status)


class DaikinCareExponentQueryParam(SystemParam):
    """Feature-detection query for command 220."""

    def __init__(self):
        SystemParam.__init__(self, EnumCmdType.SYS_DAIKIN_CARE_EXPONENT, True)

    def generate_subbody(self, s):
        s.write1(255)


class AirConInletTempAndHumidityQueryParam(SystemParam):
    """Read room-scoped inlet temperature and humidity (official cmd243)."""

    def __init__(self):
        SystemParam.__init__(
            self,
            OfficialSystemCmd.AIR_CON_INLET_TEMP_AND_HUMIDITY_INFO_QUERY,
            True,
        )
        # The official 大金空气 App leaves BaseDTO's subbody version at zero
        # for cmd243.  The legacy integration default is one, so pin this
        # command explicitly instead of inheriting the incompatible default.
        self.subbody_ver = 0

    def generate_subbody(self, s):
        # The official 大金空气 App sends unsigned 0xFF to query all rooms.
        s.write1(255)


class AirConCleaningQueryParam(SystemParam):
    def __init__(self):
        SystemParam.__init__(self, EnumCmdType.AIR_CON_CLEANING_AND_V_SLEEP_QUERY, True)
        self._room_ids: typing.List[int] = []

    def generate_subbody(self, s):
        if not self._room_ids:
            s.write1(255)
            return
        s.write1(len(self._room_ids))
        for room_id in self._room_ids:
            s.write1(room_id)
            s.write1(1)
            s.write1(0)

    @property
    def room_ids(self):
        return self._room_ids


class AirConCleaningControlParam(SystemParam):
    def __init__(self, aircons: typing.List[AirCon], switch_status: int = 1):
        SystemParam.__init__(self, EnumCmdType.AIR_CON_CLEANING_AND_V_SLEEP_SETTING, True)
        self._aircons = aircons
        self._switch_status = switch_status

    def generate_subbody(self, s):
        # cmd36 is room-scoped.  The official request record is
        # index, room, reserved, type, cleaning TLV, record terminator.
        room_ids = list(dict.fromkeys(aircon.room_id for aircon in self._aircons))
        s.write1(len(room_ids))
        for record_index, room_id in enumerate(room_ids):
            s.write1(record_index)
            s.write1(room_id)
            s.write1(0)
            s.write1(2)
            s.write1(4)
            s.write1(1)
            s.write1(1)
            s.write1(self._switch_status)
            s.write1(0)
            s.write1(0)


class GetRoomInfoParam(SystemParam):
    def __init__(self):
        SystemParam.__init__(self, EnumCmdType.SYS_GET_ROOM_INFO, True)
        self._room_ids: typing.List[int] = []
        self.type: int = 1
        self.subbody_ver: int = 1

    def generate_subbody(self, s):
        s.write1(len(self.room_ids))
        for r in self.room_ids:
            s.write2(r)
            if self.subbody_ver == 1 and r != 65535:
                s.write1(self.type)

    @property
    def room_ids(self):
        return self._room_ids


class Sensor2InfoParam(Param):
    def __init__(self):
        # todo: 未兼容固件低于02.04.00的网关
        Param.__init__(self, EnumDevice.SENSOR, EnumCmdType.SENSOR2_INFO, True)
        # self._sensor_type: int = 1

    def generate_subbody(self, s):
        s.write1(255)


class AirconParam(Param):
    def __init__(self, cmd_cype, has_result):
        Param.__init__(self, EnumDevice.AIRCON, cmd_cype, has_result)


class AirConCapabilityQueryParam(AirconParam):
    def __init__(self):
        AirconParam.__init__(self, EnumCmdType.AIR_CAPABILITY_QUERY, True)
        self._aircons: typing.List[AirCon] = []

    def generate_subbody(self, s):
        s.write1(len(self._aircons))
        for i in self._aircons:
            s.write1(i.room_id)
            s.write1(1)
            s.write1(0)

    @property
    def aircons(self):
        return self._aircons

    @aircons.setter
    def aircons(self, value):
        self._aircons = value


class AirConRecommendedIndoorTempParam(AirconParam):
    def __init__(self):
        super().__init__(EnumCmdType.AIR_RECOMMENDED_INDOOR_TEMP, True)


class AirConQueryStatusParam(AirconParam):
    def __init__(self):
        super().__init__(EnumCmdType.QUERY_STATUS, True)
        self._device = None  # type: Optional[AirCon]

    def generate_subbody(self, s):
        s.write1(self._device.room_id)
        s.write1(self._device.unit_id)
        t = EnumControl.Type
        flag = t.SWITCH | t.MODE | t.SETTED_TEMP
        dev = self.device
        if dev is not None:
            if dev.fan_volume != EnumFanVolume.NO:
                flag = flag | t.AIR_FLOW
            if Config.is_new_version:
                if dev.fan_direction1 != EnumFanDirection.FIX or dev.fan_direction2 != EnumFanDirection.FIX:
                    flag = flag | t.FAN_DIRECTION
                if dev.bath_room:
                    flag = flag | t.BREATHE
                elif dev.three_d_fresh_allow:
                    flag = flag | t.BREATHE
                flag = flag | t.HUMIDITY
            if dev.hum_fresh_air_allow:
                flag = flag | t.FRESH_AIR_HUMIDIFICATION
        s.write1(flag)

    @property
    def device(self):
        return self._device

    @device.setter
    def device(self, v: AirCon):
        self._device = v


class AirConControlParam(AirconParam):
    def __init__(self, aircon: AirCon, new_status: AirConStatus):
        super().__init__(EnumCmdType.CONTROL, False)
        self.target = get_device_by_aircon(aircon)
        self._aircon = aircon
        self._new_status = new_status

    def generate_subbody(self, s):
        aircon = self._aircon
        status = self._new_status
        s.write1(aircon.room_id)
        s.write1(aircon.unit_id)
        li = []
        flag = 0
        if status.switch is not None:
            flag = flag | EnumControl.Type.SWITCH
            li.append((1, status.switch.value))
        if status.mode is not None:
            flag = flag | EnumControl.Type.MODE
            li.append((1, status.mode.value))
        if status.air_flow is not None:
            flag = flag | EnumControl.Type.AIR_FLOW
            li.append((1, status.air_flow.value))
        if status.current_temp is not None:
            flag = flag | EnumControl.Type.CURRENT_TEMP
            li.append((2, status.current_temp))
        if status.setted_temp is not None:
            flag = flag | EnumControl.Type.SETTED_TEMP
            li.append((2, status.setted_temp))
        if Config.is_new_version:
            if status.fan_direction1 is not None:
                flag = flag | EnumControl.Type.FAN_DIRECTION
                fan_direction2 = status.fan_direction2
                if fan_direction2 is None:
                    fan_direction2 = aircon.status.fan_direction2
                li.append((1, status.fan_direction1 | fan_direction2 << 4))

            if self.target == EnumDevice.NEWAIRCON:
                if status.humidity is not None:
                    flag = flag | EnumControl.Type.HUMIDITY
                    li.append((1, status.humidity.value))
            if self.target == EnumDevice.BATHROOM:
                if status.breathe is not None:
                    flag = flag | EnumControl.Type.BREATHE
                    li.append((1, status.breathe.value))
        s.write1(flag)
        for bit, val in li:
            if bit == 1:
                s.write1(val)
            elif bit == 2:
                s.write2(val)


class VentilationParam(Param):
    def __init__(self, cmd_type, has_result):
        Param.__init__(self, EnumDevice.VENTILATION, cmd_type, has_result)


class VentilationCapabilityQueryParam(VentilationParam):
    def __init__(self):
        VentilationParam.__init__(self, EnumCmdType.VENT_QUERY_CAPABILITY, True)
        self._vents = []  # type: typing.List[Ventilation]

    def generate_subbody(self, s):
        s.write1(len(self._vents))
        for i in self._vents:
            s.write1(i.room_id)
            s.write1(1)
            s.write1(0)

    @property
    def vents(self):
        return self._vents

    @vents.setter
    def vents(self, value):
        self._vents = value


class VentilationQueryStatusParam(VentilationParam):
    def __init__(self):
        VentilationParam.__init__(self, EnumCmdType.QUERY_STATUS, True)
        self._device = None  # type: Optional[Ventilation]

    def generate_subbody(self, s):
        s.write1(self._device.room_id)
        s.write1(self._device.unit_id)
        s.write1(EnumControl.Type.SWITCH | EnumControl.Type.MODE | EnumControl.Type.AIR_FLOW)

    @property
    def device(self):
        return self._device

    @device.setter
    def device(self, v: Ventilation):
        self._device = v


class VentilationControlParam(VentilationParam):
    def __init__(self, vent: Ventilation, new_status: VentilationStatus):
        VentilationParam.__init__(self, EnumCmdType.CONTROL, False)
        self.target = get_device_by_vent(vent)
        self._vent = vent
        self._new_status = new_status

    def generate_subbody(self, s):
        vent = self._vent
        status = self._new_status
        s.write1(vent.room_id)
        s.write1(vent.unit_id)
        li = []
        flag = 0
        if status.switch is not None:
            flag = flag | EnumControl.Type.SWITCH
            li.append((1, status.switch.value))
        if status.mode is not None:
            flag = flag | EnumControl.Type.MODE
            li.append((1, status.mode.value))
        if status.air_flow is not None:
            flag = flag | EnumControl.Type.AIR_FLOW
            li.append((1, status.air_flow.value))

        s.write1(flag)
        for bit, val in li:
            if bit == 1:
                s.write1(val)
            elif bit == 2:
                s.write2(val)


class VentilationQueryCompositeSituationParam(VentilationParam):
    def __init__(self):
        VentilationParam.__init__(self, EnumCmdType.SMALL_VAM_QUERY_COMPOSITE_SITUATION, True)
        self._device = None  # type: Optional[Ventilation]

    def generate_subbody(self, s):
        s.write1(self._device.room_id)
        # The official MiniVAM request uses a reserved zero byte, not unit_id.
        s.write1(0)

    @property
    def device(self):
        return self._device

    @device.setter
    def device(self, v: Ventilation):
        self._device = v

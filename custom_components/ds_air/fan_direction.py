from typing import Optional

from .ds_air_service.ctrl_enum import EnumControl, EnumFanDirection
from .ds_air_service.dao import AirCon, AirConStatus

AXIS_VERTICAL = "vertical"
AXIS_HORIZONTAL = "horizontal"

_VERTICAL_OPTIONS = {
    "最上": EnumControl.FanDirection.P0,
    "上": EnumControl.FanDirection.P1,
    "中": EnumControl.FanDirection.P2,
    "下": EnumControl.FanDirection.P3,
    "最下": EnumControl.FanDirection.P4,
    "自动": EnumControl.FanDirection.AUTO,
    "摆动": EnumControl.FanDirection.SWING,
}

_HORIZONTAL_OPTIONS = {
    "最右": EnumControl.FanDirection.P0,
    "右": EnumControl.FanDirection.P1,
    "中": EnumControl.FanDirection.P2,
    "左": EnumControl.FanDirection.P3,
    "最左": EnumControl.FanDirection.P4,
    "自动": EnumControl.FanDirection.AUTO,
    "摆动": EnumControl.FanDirection.SWING,
}

_INVALID_DIRECTIONS = {None, EnumControl.FanDirection.INVALID}


def direction_supported(aircon: AirCon, axis: str) -> bool:
    if axis == AXIS_VERTICAL:
        return aircon.fan_direction1 != EnumFanDirection.FIX
    if axis == AXIS_HORIZONTAL:
        return aircon.fan_direction2 != EnumFanDirection.FIX
    return False


def direction_options(axis: str) -> list[str]:
    return list(_option_map(axis).keys())


def direction_to_option(
    axis: str, direction: Optional[EnumControl.FanDirection]
) -> Optional[str]:
    if direction in _INVALID_DIRECTIONS:
        return None
    for option, enum_value in _option_map(axis).items():
        if enum_value == direction:
            return option
    return None


def option_to_direction(axis: str, option: str) -> EnumControl.FanDirection:
    return _option_map(axis)[option]


def primary_direction(aircon: AirCon) -> Optional[EnumControl.FanDirection]:
    if direction_supported(aircon, AXIS_VERTICAL):
        return aircon.status.fan_direction1
    if direction_supported(aircon, AXIS_HORIZONTAL):
        return aircon.status.fan_direction2
    return None


def status_for_single_swing(
    aircon: AirCon, direction: EnumControl.FanDirection
) -> Optional[AirConStatus]:
    supports_vertical = direction_supported(aircon, AXIS_VERTICAL)
    supports_horizontal = direction_supported(aircon, AXIS_HORIZONTAL)
    if not supports_vertical and not supports_horizontal:
        return None

    status = AirConStatus()
    status.fan_direction1 = direction if supports_vertical else aircon.status.fan_direction1
    status.fan_direction2 = direction if supports_horizontal else aircon.status.fan_direction2
    return status


def status_for_axis_direction(
    aircon: AirCon, axis: str, direction: EnumControl.FanDirection
) -> Optional[AirConStatus]:
    supports_vertical = direction_supported(aircon, AXIS_VERTICAL)
    supports_horizontal = direction_supported(aircon, AXIS_HORIZONTAL)
    if not supports_vertical and not supports_horizontal:
        return None

    current_vertical = aircon.status.fan_direction1
    current_horizontal = aircon.status.fan_direction2
    status = AirConStatus()

    if supports_vertical and not supports_horizontal:
        status.fan_direction1 = direction
        status.fan_direction2 = current_horizontal
        return status

    if supports_horizontal and not supports_vertical:
        status.fan_direction1 = current_vertical
        status.fan_direction2 = direction
        return status

    if direction == EnumControl.FanDirection.AUTO:
        status.fan_direction1 = direction
        status.fan_direction2 = direction
        return status

    if axis == AXIS_VERTICAL:
        status.fan_direction1 = direction
        status.fan_direction2 = (
            direction
            if current_horizontal in _INVALID_DIRECTIONS
            or current_horizontal == EnumControl.FanDirection.AUTO
            else current_horizontal
        )
    else:
        status.fan_direction1 = (
            direction
            if current_vertical in _INVALID_DIRECTIONS
            or current_vertical == EnumControl.FanDirection.AUTO
            else current_vertical
        )
        status.fan_direction2 = direction

    return status


def _option_map(axis: str) -> dict[str, EnumControl.FanDirection]:
    return _VERTICAL_OPTIONS if axis == AXIS_VERTICAL else _HORIZONTAL_OPTIONS

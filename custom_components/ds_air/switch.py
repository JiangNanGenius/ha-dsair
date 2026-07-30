"""Switch entities for DS-AIR self-cleaning selection."""

from typing import Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cleaning_device import cleaning_device_info
from .ds_air_service.dao import AirCon


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up DS-AIR self-cleaning selection switches."""
    from .ds_air_service.service import Service

    async_add_entities(
        [
            DsAirHeatExchangeCleaningSwitch(aircon)
            for aircon in Service.get_aircons()
            if aircon.heat_exchange_cleaning_allow
        ]
    )


class DsAirHeatExchangeCleaningSwitch(SwitchEntity):
    """Selection switch for one air conditioner in a self-cleaning batch."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, aircon: AirCon):
        self._device_info = aircon
        self._attr_unique_id = f"{aircon.unique_id}_heat_exchange_cleaning_selected"
        self._attr_name = f"{aircon.alias} 加入自清洁"
        self._attr_icon = "mdi:checkbox-marked-circle-outline"

        from .ds_air_service.service import Service

        Service.register_status_hook(aircon, self._status_change_hook)

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        from .ds_air_service.service import Service

        return Service.is_heat_exchange_cleaning_joinable(self._device_info)

    @property
    def is_on(self):
        from .ds_air_service.service import Service

        return Service.is_heat_exchange_cleaning_selected(self._device_info)

    def turn_on(self, **kwargs):
        from .ds_air_service.service import Service

        Service.select_heat_exchange_cleaning(self._device_info, True)
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        from .ds_air_service.service import Service

        Service.select_heat_exchange_cleaning(self._device_info, False)
        self.schedule_update_ha_state()

    def _status_change_hook(self, **kwargs):
        if kwargs.get("aircon") is not None:
            aircon: AirCon = kwargs["aircon"]
            aircon.status = self._device_info.status
            self._device_info = aircon
        self.schedule_update_ha_state()

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return cleaning_device_info()

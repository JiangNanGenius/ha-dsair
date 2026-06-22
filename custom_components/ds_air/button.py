"""Button entities for DS-AIR self-cleaning."""

from typing import Optional

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cleaning_device import cleaning_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up DS-AIR self-cleaning start button."""
    async_add_entities([DsAirStartHeatExchangeCleaningButton()])


class DsAirStartHeatExchangeCleaningButton(ButtonEntity):
    """Start self-cleaning for the currently selected air conditioners."""

    _attr_unique_id = "ds_air_start_heat_exchange_cleaning"
    _attr_name = "开始自清洁"
    _attr_icon = "mdi:air-filter"

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        from .ds_air_service.service import Service

        return any(i.heat_exchange_cleaning_allow for i in Service.get_aircons())

    @property
    def extra_state_attributes(self):
        from .ds_air_service.service import Service

        supported = [i for i in Service.get_aircons() if i.heat_exchange_cleaning_allow]
        selected = [
            i for i in supported
            if Service.is_heat_exchange_cleaning_selected(i)
        ]
        return {
            "supported_count": len(supported),
            "selected_count": len(selected),
        }

    def press(self) -> None:
        from .ds_air_service.service import Service

        Service.start_selected_heat_exchange_cleaning()
        self.schedule_update_ha_state()

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return cleaning_device_info()

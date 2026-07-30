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
    from .ds_air_service.service import Service

    async_add_entities([
        DsAirStartHeatExchangeCleaningButton(),
        *(DsAirResetFilterCleanSignButton(aircon)
          for aircon in Service.get_aircons()),
    ])


class DsAirStartHeatExchangeCleaningButton(ButtonEntity):
    """Start self-cleaning for the currently selected air conditioners."""

    _attr_entity_registry_enabled_default = False
    _attr_unique_id = "ds_air_start_heat_exchange_cleaning"
    _attr_name = "开始自清洁"
    _attr_icon = "mdi:air-filter"

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        from .ds_air_service.service import Service

        return any(
            Service.is_heat_exchange_cleaning_joinable(i)
            for i in Service.get_aircons()
        )

    @property
    def extra_state_attributes(self):
        from .ds_air_service.service import Service

        supported = [i for i in Service.get_aircons() if i.heat_exchange_cleaning_allow]
        joinable = [i for i in supported if Service.is_heat_exchange_cleaning_joinable(i)]
        selected = [
            i for i in joinable
            if Service.is_heat_exchange_cleaning_selected(i)
        ]
        return {
            "supported_count": len(supported),
            "joinable_count": len(joinable),
            "selected_count": len(selected),
        }

    def press(self) -> None:
        from .ds_air_service.service import Service

        Service.start_selected_heat_exchange_cleaning()
        self.schedule_update_ha_state()

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return cleaning_device_info()


class DsAirResetFilterCleanSignButton(ButtonEntity):
    """Reset the gateway's local filter-clean reminder for one indoor room."""

    _attr_icon = "mdi:air-filter-remove"

    def __init__(self, aircon):
        self._device_info = aircon
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{aircon.unique_id}_reset_filter_clean_sign"
        self._attr_name = "复位滤网清洗提醒"

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        from .ds_air_service.service import Service
        return Service.is_ready()

    @property
    def extra_state_attributes(self):
        return {
            "command": "daikin_official_local_cmd21",
            "scope": "room",
            "room_id": self._device_info.room_id,
            "effect": "reset_all_filter_clean_sign_bits",
            "does_not_fabricate_lifetime": True,
        }

    def press(self) -> None:
        from .ds_air_service.service import Service
        Service.reset_filter_clean_sign(self._device_info)
        self.schedule_update_ha_state()

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {("ds_air", self._device_info.unique_id)},
            "name": "空调%s" % self._device_info.alias,
            "manufacturer": "Daikin Industries, Ltd.",
        }

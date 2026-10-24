"""Binary sensor platform for Votronic."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VotronicConfigEntry
from .entity import VotronicEntity, async_add_entities_per_frame

BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="charging",
        translation_key="charging",
        icon="mdi:battery-charging",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="discharging",
        translation_key="discharging",
        icon="mdi:power-plug",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="controller_active",
        translation_key="controller_active",
        icon="mdi:power",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="current_reduction",
        translation_key="current_reduction",
        icon="mdi:car-speed-limiter",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="aes_active",
        translation_key="aes_active",
        icon="mdi:export",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VotronicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Votronic binary sensors."""

    entry.async_on_unload(
        async_add_entities_per_frame(
            entry.runtime_data, BINARY_SENSORS, VotronicBinarySensor, async_add_entities
        )
    )


class VotronicBinarySensor(VotronicEntity, BinarySensorEntity):
    """Representation of a Votronic binary sensor."""

    def __init__(self, device, description: BinarySensorEntityDescription) -> None:
        """Initialize the binary sensor."""

        super().__init__(device, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""

        return self._device.get_value(self._key)

"""Sensor platform for Votronic."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VotronicConfigEntry
from .entity import VotronicEntity, async_add_entities_per_frame

UNIT_AMPERE_HOURS = "Ah"


@dataclass(frozen=True, kw_only=True)
class VotronicSensorEntityDescription(SensorEntityDescription):
    """Description of a Votronic numeric sensor."""


SENSORS: tuple[VotronicSensorEntityDescription, ...] = (
    VotronicSensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    VotronicSensorEntityDescription(
        key="secondary_battery_voltage",
        translation_key="secondary_battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    VotronicSensorEntityDescription(
        key="battery_capacity_remaining",
        translation_key="battery_capacity_remaining",
        native_unit_of_measurement=UNIT_AMPERE_HOURS,
        icon="mdi:battery-50",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    VotronicSensorEntityDescription(
        key="state_of_charge",
        translation_key="state_of_charge",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:battery-50",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    VotronicSensorEntityDescription(
        key="current",
        translation_key="current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
    ),
    VotronicSensorEntityDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    VotronicSensorEntityDescription(
        key="battery_nominal_capacity",
        translation_key="battery_nominal_capacity",
        native_unit_of_measurement=UNIT_AMPERE_HOURS,
        icon="mdi:battery",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    VotronicSensorEntityDescription(
        key="pv_voltage",
        translation_key="pv_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    VotronicSensorEntityDescription(
        key="pv_current",
        translation_key="pv_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    VotronicSensorEntityDescription(
        key="pv_controller_temperature",
        translation_key="pv_controller_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    VotronicSensorEntityDescription(
        key="pv_power",
        translation_key="pv_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    VotronicSensorEntityDescription(
        key="battery_status_bitmask",
        translation_key="battery_status_bitmask",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    VotronicSensorEntityDescription(
        key="battery_status",
        translation_key="battery_status",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VotronicSensorEntityDescription(
        key="pv_controller_status_bitmask",
        translation_key="pv_controller_status_bitmask",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    VotronicSensorEntityDescription(
        key="pv_controller_status",
        translation_key="pv_controller_status",
        icon="mdi:heart-pulse",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VotronicSensorEntityDescription(
        key="charged_capacity",
        translation_key="charged_capacity",
        native_unit_of_measurement=UNIT_AMPERE_HOURS,
        icon="mdi:battery-charging",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
    ),
    VotronicSensorEntityDescription(
        key="charged_energy",
        translation_key="charged_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VotronicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Votronic sensors."""

    entry.async_on_unload(
        async_add_entities_per_frame(
            entry.runtime_data, SENSORS, VotronicSensor, async_add_entities
        )
    )


class VotronicSensor(VotronicEntity, SensorEntity):
    """Representation of a Votronic sensor."""

    entity_description: VotronicSensorEntityDescription

    def __init__(
        self,
        device,
        description: VotronicSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(device, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        """Return the sensor value."""

        return self._device.get_value(self._key)

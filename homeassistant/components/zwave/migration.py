"""Handle migration from legacy Z-Wave to OpenZWave and Z-Wave JS."""
from __future__ import annotations

import logging
from typing import cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get as async_get_entity_registry,
)
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store

from .const import DATA_ENTITY_VALUES, DOMAIN
from .util import compute_value_unique_id, node_device_id_and_name

_LOGGER = logging.getLogger(__name__)

LEGACY_ZWAVE_MIGRATION = f"{DOMAIN}_legacy_zwave_migration"
STORAGE_WRITE_DELAY = 30
STORAGE_KEY = f"{DOMAIN}.legacy_zwave_migration"
STORAGE_VERSION = 1


@callback
def async_is_ozw_migrated(hass):
    """Return True if migration to ozw is done."""
    ozw_config_entries = hass.config_entries.async_entries("ozw")
    if not ozw_config_entries:
        return False

    ozw_config_entry = ozw_config_entries[0]  # only one ozw entry is allowed
    migrated = bool(ozw_config_entry.data.get("migrated"))
    return migrated


@callback
def async_generate_migration_data(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Generate Z-Wave migration data."""
    migration_handler = get_legacy_zwave_migration(hass)
    migration_handler.generate_data(config_entry)


@callback
def async_get_migration_data(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, dict[str, int | str | None]]:
    """Return Z-Wave migration data."""
    migration_handler = get_legacy_zwave_migration(hass)
    return migration_handler.get_data(config_entry)


@singleton(LEGACY_ZWAVE_MIGRATION)
@callback
def get_legacy_zwave_migration(hass: HomeAssistant) -> LegacyZWaveMigration:
    """Return legacy Z-Wave migration handler."""
    return LegacyZWaveMigration(hass)


class LegacyZWaveMigration:
    """Handle the migration from zwave to ozw and zwave_js."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Set up migration instance."""
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, dict[str, dict[str, int | str | None]]] = {}

    async def load_data(self) -> None:
        """Load Z-Wave migration data."""
        stored = cast(dict, await self._store.async_load())
        if stored:
            self._data = stored

    @callback
    def save_data(
        self, data: dict[str, dict[str, dict[str, int | str | None]]]
    ) -> None:
        """Save Z-Wave migration data."""
        self._data.update(data)
        self._store.async_delay_save(self._data_to_save, STORAGE_WRITE_DELAY)

    @callback
    def _data_to_save(self) -> dict[str, dict[str, dict[str, int | str | None]]]:
        """Return data to save."""
        return self._data

    @callback
    def generate_data(self, config_entry: ConfigEntry) -> None:
        """Create Z-Wave side migration data for a config entry."""
        data: dict[str, dict[str, int | str | None]] = {}
        ent_reg = async_get_entity_registry(self._hass)
        entity_entries = async_entries_for_config_entry(ent_reg, config_entry.entry_id)
        unique_entries = {entry.unique_id: entry for entry in entity_entries}
        dev_reg = async_get_device_registry(self._hass)

        for entity_values in self._hass.data[DATA_ENTITY_VALUES]:
            node = entity_values.primary.node
            unique_id = compute_value_unique_id(node, entity_values.primary)
            if unique_id not in unique_entries:
                continue
            entity_entry = unique_entries[unique_id]
            device_identifier, _ = node_device_id_and_name(
                node, entity_values.primary.instance
            )
            device_entry = dev_reg.async_get_device({device_identifier}, set())
            data[unique_id] = {
                "node_id": node.node_id,
                "node_instance": entity_values.primary.instance,
                "command_class": entity_values.primary.command_class,
                "command_class_label": entity_values.primary.label,
                "value_index": entity_values.primary.index,
                "device_id": device_entry.id,
                "domain": entity_entry.domain,
                "entity_id": entity_entry.entity_id,
                "unique_id": unique_id,
                "unit_of_measurement": entity_entry.unit_of_measurement,
            }

        _LOGGER.debug("Collected migration data: %s", data)

        self.save_data({config_entry.entry_id: data})

    async def get_data(
        self, config_entry: ConfigEntry
    ) -> dict[str, dict[str, int | str | None]]:
        """Return Z-Wave migration data."""
        await self.load_data()
        data = self._data.get(config_entry.entry_id)
        return data or {}

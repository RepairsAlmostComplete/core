"""Handle migration from legacy Z-Wave to OpenZWave and Z-Wave JS."""
import json
import logging
from pathlib import Path

from homeassistant.core import callback
from homeassistant.helpers.device_registry import (
    async_get_registry as async_get_device_registry,
)
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get_registry as async_get_entity_registry,
)

from .const import DATA_ENTITY_VALUES, DATA_ZWAVE_CONFIG_YAML_PRESENT, DOMAIN
from .util import compute_value_unique_id, node_device_id_and_name

_LOGGER = logging.getLogger(__name__)


async def async_get_ozw_migration_data(hass):
    """Return dict with info for migration to ozw integration."""
    data_to_migrate = {}

    zwave_config_entries = hass.config_entries.async_entries(DOMAIN)
    if not zwave_config_entries:
        _LOGGER.error("Config entry not set up")
        return data_to_migrate

    if hass.data.get(DATA_ZWAVE_CONFIG_YAML_PRESENT):
        _LOGGER.warning(
            "Remove %s from configuration.yaml "
            "to avoid setting up this integration on restart "
            "after completing migration to ozw",
            DOMAIN,
        )

    config_entry = zwave_config_entries[0]  # zwave only has a single config entry
    ent_reg = await async_get_entity_registry(hass)
    entity_entries = async_entries_for_config_entry(ent_reg, config_entry.entry_id)
    unique_entries = {entry.unique_id: entry for entry in entity_entries}
    dev_reg = await async_get_device_registry(hass)

    for entity_values in hass.data[DATA_ENTITY_VALUES]:
        node = entity_values.primary.node
        unique_id = compute_value_unique_id(node, entity_values.primary)
        if unique_id not in unique_entries:
            continue
        entity_entry = unique_entries[unique_id]
        device_identifier, _ = node_device_id_and_name(
            node, entity_values.primary.instance
        )
        device_entry = dev_reg.async_get_device({device_identifier}, set())
        data_to_migrate[unique_id] = {
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

    save_path = Path(hass.config.path("zwave_migration_data.json"))
    await hass.async_add_executor_job(
        save_path.write_text, json.dumps(data_to_migrate, indent=2)
    )

    _LOGGER.debug("Collected migration data: %s", data_to_migrate)

    return data_to_migrate


@callback
def async_is_ozw_migrated(hass):
    """Return True if migration to ozw is done."""
    ozw_config_entries = hass.config_entries.async_entries("ozw")
    if not ozw_config_entries:
        return False

    ozw_config_entry = ozw_config_entries[0]  # only one ozw entry is allowed
    migrated = bool(ozw_config_entry.data.get("migrated"))
    return migrated

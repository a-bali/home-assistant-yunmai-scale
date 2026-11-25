"""Minimal stand-in for homeassistant.helpers.entity_registry."""


class _Registry:
    def async_remove(self, entity_id):
        return None


def async_get(hass):
    return _Registry()


def async_entries_for_config_entry(registry, entry_id):
    return []

"""Minimal stand-in for homeassistant.config_entries."""
import asyncio


class ConfigEntry:
    def __init__(self, entry_id="test", data=None, options=None):
        self.entry_id = entry_id
        self.data = data or {}
        self.options = options or {}
        self.version = 3

    def async_create_background_task(self, hass, target, name=None):
        task = asyncio.get_running_loop().create_task(target, name=name)
        return task

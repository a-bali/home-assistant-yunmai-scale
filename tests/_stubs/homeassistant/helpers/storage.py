"""Minimal stand-in for homeassistant.helpers.storage."""


class Store:
    def __init__(self, hass, version, key):
        self.hass = hass
        self.version = version
        self.key = key
        self.data = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data

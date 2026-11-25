"""Minimal stand-in for homeassistant.helpers.dispatcher."""

SENT = []


def async_dispatcher_send(hass, signal, *args):
    SENT.append((signal, args))

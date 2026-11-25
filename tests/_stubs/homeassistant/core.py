"""Minimal stand-in for homeassistant.core."""


class HomeAssistant:
    data = None


def callback(func):
    return func

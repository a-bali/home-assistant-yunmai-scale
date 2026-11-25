"""Tests for recovering a weigh-in that began before the link was ready.

The scale streams live weight frames that the integration uses to recognise a
profile. When a weigh-in starts while the persistent connection is still
connecting (a proxy connection can take 8-10 s), those frames arrive before the
session reaches ``ready`` and recognition never sees them. Before this change
the entire cycle was dropped, so the weight was lost while the session status
went back to ``ready`` and nothing was logged above DEBUG.

The recovery path attributes the measurement from the user ID the scale echoes
in its final frame, and only when the final weight still agrees with that
profile's reference weight. These tests pin both halves: the recovery itself,
and the guarantee that a stale or foreign ID cannot write a measurement to the
wrong user.
"""

from __future__ import annotations

import asyncio
import unittest

import conftest  # noqa: F401  (installs the Home Assistant stubs)

from custom_components.yunmai_scale.manager import YunmaiScaleManager
from custom_components.yunmai_scale.models import ParsedFrame, YunmaiProfile


def make_profile(
    name: str = "Andras",
    uid: int = 4097,
    reference_weight: float = 82.0,
) -> YunmaiProfile:
    return YunmaiProfile(
        name=name,
        uid=uid,
        height_cm=180,
        sex="male",
        birth_year=1981,
        reference_weight=reference_weight,
        activity=False,
    )


def make_manager(profiles: list[YunmaiProfile] | None = None) -> YunmaiScaleManager:
    from homeassistant.config_entries import ConfigEntry

    hass = object()
    entry = ConfigEntry(
        entry_id="test",
        data={"address": "64:CF:D9:0F:CC:CB", "profiles": []},
        options={"profiles": []},
    )
    manager = YunmaiScaleManager(
        hass=hass,
        entry=entry,
        address="64:CF:D9:0F:CC:CB",
        device_name="Yunmai Scale",
        profiles=profiles if profiles is not None else [make_profile()],
    )
    # The store is only used for persistence; keep the tests off disk.
    manager._store = _NullStore()  # noqa: SLF001
    return manager


class _NullStore:
    async def async_load(self):
        return None

    async def async_save(self, data):
        return None


def final_frame(weight_kg: float, user_id: int | None) -> ParsedFrame:
    return ParsedFrame(
        kind="measured",
        weight_kg=weight_kg,
        user_id=user_id,
        impedance_raw=520,
        fat_percent=None,
    )


class PreReadyAttributionTests(unittest.TestCase):
    """The pre-ready cycle is attributed from the scale's final frame."""

    def test_matching_user_id_and_weight_recovers_the_measurement(self):
        manager = make_manager()
        profile = manager._attribute_pre_ready_frame(  # noqa: SLF001
            final_frame(81.89, 4097)
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.uid, 4097)

    def test_recovery_is_stored_for_the_attributed_profile(self):
        async def run() -> YunmaiScaleManager:
            manager = make_manager()
            profile = manager._attribute_pre_ready_frame(  # noqa: SLF001
                final_frame(81.89, 4097)
            )
            assert profile is not None
            await manager._async_save_measurement(  # noqa: SLF001
                profile, final_frame(81.89, 4097)
            )
            return manager

        manager = asyncio.run(run())
        self.assertEqual(len(manager.measurements), 1)
        self.assertEqual(manager.last_user_uid, 4097)
        stored = manager.get_measurement(4097)
        assert stored is not None
        self.assertAlmostEqual(stored.weight_kg, 81.89)
        # The recovered weight becomes the next recognition reference, exactly
        # as a normally recognised weigh-in would.
        self.assertAlmostEqual(
            manager.get_reference_weight(manager.profiles[0]), 81.89
        )

    def test_unknown_user_id_is_not_attributed(self):
        manager = make_manager()
        self.assertIsNone(
            manager._attribute_pre_ready_frame(  # noqa: SLF001
                final_frame(81.89, 0x2002)
            )
        )

    def test_missing_user_id_is_not_attributed(self):
        manager = make_manager()
        self.assertIsNone(
            manager._attribute_pre_ready_frame(  # noqa: SLF001
                final_frame(81.89, None)
            )
        )

    def test_weight_outside_the_recognition_window_is_not_attributed(self):
        """A stale ID must not write someone else's weight to this profile."""
        manager = make_manager()
        # 82.0 kg reference, 10% window => 73.8 .. 90.2 kg.
        self.assertIsNone(
            manager._attribute_pre_ready_frame(  # noqa: SLF001
                final_frame(57.13, 4097)
            )
        )
        self.assertIsNone(
            manager._attribute_pre_ready_frame(  # noqa: SLF001
                final_frame(103.5, 4097)
            )
        )

    def test_window_boundary_is_respected(self):
        manager = make_manager()
        # 82.0 kg reference, 10% window => 73.8 .. 90.2 kg. The comparison
        # mirrors _choose_profile, so probe just inside and just outside
        # rather than on the boundary itself (an exact 90.2 differs from
        # 82.0 * 1.1 by ~1e-15 in binary floating point).
        self.assertIsNotNone(
            manager._attribute_pre_ready_frame(  # noqa: SLF001
                final_frame(90.1, 4097)
            )
        )
        self.assertIsNone(
            manager._attribute_pre_ready_frame(  # noqa: SLF001
                final_frame(90.3, 4097)
            )
        )

    def test_attribution_uses_the_echoed_id_not_nearest_weight(self):
        """With two configured users the scale's own ID decides."""
        andras = make_profile(name="Andras", uid=4097, reference_weight=82.0)
        csilla = make_profile(name="Csilla", uid=8193, reference_weight=64.0)
        manager = make_manager([andras, csilla])

        attributed = manager._attribute_pre_ready_frame(  # noqa: SLF001
            final_frame(81.5, 4097)
        )
        assert attributed is not None
        self.assertEqual(attributed.name, "Andras")

        attributed = manager._attribute_pre_ready_frame(  # noqa: SLF001
            final_frame(64.5, 8193)
        )
        assert attributed is not None
        self.assertEqual(attributed.name, "Csilla")


class IgnoredCycleReportingTests(unittest.TestCase):
    """A dropped cycle must be visible without enabling debug logging."""

    def test_ignored_cycle_is_counted_and_reasoned(self):
        manager = make_manager()
        self.assertEqual(manager.ignored_cycle_count, 0)
        self.assertIsNone(manager.last_ignored_reason)

        manager._note_ignored_cycle("no final frame", None)  # noqa: SLF001
        self.assertEqual(manager.ignored_cycle_count, 1)
        self.assertEqual(manager.last_ignored_reason, "no final frame")

        manager._note_ignored_cycle("unknown profile", 71.2)  # noqa: SLF001
        self.assertEqual(manager.ignored_cycle_count, 2)
        self.assertEqual(manager.last_ignored_reason, "unknown profile")

    def test_ignored_cycle_is_logged_at_warning(self):
        manager = make_manager()
        with self.assertLogs(
            "custom_components.yunmai_scale.manager", level="WARNING"
        ) as captured:
            manager._note_ignored_cycle(  # noqa: SLF001
                "the weigh-in started before the connection was ready",
                71.2,
            )
        self.assertTrue(
            any("71.20 kg" in line for line in captured.output),
            captured.output,
        )

    def test_counts_reach_diagnostics_and_status_attributes(self):
        manager = make_manager()
        manager._note_ignored_cycle("unknown profile", 71.2)  # noqa: SLF001
        diagnostics = manager.diagnostics
        self.assertEqual(diagnostics["ignored_cycle_count"], 1)
        self.assertEqual(diagnostics["last_ignored_reason"], "unknown profile")


if __name__ == "__main__":
    unittest.main()

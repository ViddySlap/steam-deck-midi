"""Tests for SteamInputLayerTrackerEngine."""

from __future__ import annotations

import unittest

from windows.engines.steam_input_layer_tracker import (
    LAYER_CHASER,
    LAYER_FLASH,
    SteamInputLayerTrackerEngine,
)
from windows.midi import DryRunMidiOut


class FakeOscClient:
    def __init__(self) -> None:
        self.sends: list[tuple[str, object]] = []
        self.closed = False

    def send(self, address: str, value) -> None:
        self.sends.append((address, value))

    def close(self) -> None:
        self.closed = True


def _tracker(**overrides) -> tuple[SteamInputLayerTrackerEngine, FakeOscClient]:
    cfg = {
        "name": "Tracker",
        "type": "steam_input_layer_tracker",
        "channel": 1,
        "default_layer": LAYER_CHASER,
        "chaser_notes": [64, 65, 66, 67],
        "flash_notes": [68, 69, 70, 71],
        "select_note": 72,
        "chaser_ccs": [],
        "flash_ccs": [],
        "select_cc": None,
        "emit_osc": False,
        "osc": {"host": "127.0.0.1", "port": 7000},
    }
    cfg.update(overrides)
    osc = FakeOscClient()
    midi = DryRunMidiOut()
    engine = SteamInputLayerTrackerEngine(
        cfg["name"], cfg, midi, osc_client=osc
    )
    return engine, osc


class SteamInputLayerTrackerInitTests(unittest.TestCase):
    def test_default_layer_is_chaser(self) -> None:
        engine, _ = _tracker()
        self.assertEqual(engine.current_layer, LAYER_CHASER)

    def test_invalid_default_layer_falls_back(self) -> None:
        engine, _ = _tracker(default_layer="bogus")
        self.assertEqual(engine.current_layer, LAYER_CHASER)

    def test_default_layer_flash_honored(self) -> None:
        engine, _ = _tracker(default_layer=LAYER_FLASH)
        self.assertEqual(engine.current_layer, LAYER_FLASH)


class SteamInputLayerTrackerNoteTests(unittest.TestCase):
    def test_chaser_note_sets_chaser_layer(self) -> None:
        engine, _ = _tracker(default_layer=LAYER_FLASH)
        engine.on_note_in(channel=1, note=64, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_CHASER)

    def test_flash_note_sets_flash_layer(self) -> None:
        engine, _ = _tracker(default_layer=LAYER_CHASER)
        engine.on_note_in(channel=1, note=68, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_FLASH)

    def test_select_note_toggles_layer(self) -> None:
        engine, _ = _tracker()
        self.assertEqual(engine.current_layer, LAYER_CHASER)
        engine.on_note_in(channel=1, note=72, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_FLASH)
        engine.on_note_in(channel=1, note=72, velocity=127, now=0.1)
        self.assertEqual(engine.current_layer, LAYER_CHASER)

    def test_note_off_velocity_zero_is_ignored(self) -> None:
        engine, _ = _tracker()
        engine.on_note_in(channel=1, note=68, velocity=0, now=0.0)
        # Note Off should not change the layer.
        self.assertEqual(engine.current_layer, LAYER_CHASER)

    def test_wrong_channel_is_ignored(self) -> None:
        engine, _ = _tracker(channel=1)
        engine.on_note_in(channel=2, note=68, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_CHASER)

    def test_unmapped_note_is_ignored(self) -> None:
        engine, _ = _tracker()
        engine.on_note_in(channel=1, note=42, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_CHASER)

    def test_channel_none_accepts_any_channel(self) -> None:
        engine, _ = _tracker(channel=None)
        engine.on_note_in(channel=7, note=68, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_FLASH)


class SteamInputLayerTrackerCcFallbackTests(unittest.TestCase):
    def test_chaser_cc_sets_chaser_layer(self) -> None:
        engine, _ = _tracker(
            default_layer=LAYER_FLASH,
            chaser_ccs=[20, 21],
            flash_ccs=[24, 25],
        )
        engine.on_midi_in(channel=1, cc=20, value=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_CHASER)

    def test_flash_cc_sets_flash_layer(self) -> None:
        engine, _ = _tracker(chaser_ccs=[20], flash_ccs=[24])
        engine.on_midi_in(channel=1, cc=24, value=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_FLASH)

    def test_select_cc_toggles_layer(self) -> None:
        engine, _ = _tracker(select_cc=30)
        engine.on_midi_in(channel=1, cc=30, value=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_FLASH)

    def test_zero_value_cc_does_not_trigger(self) -> None:
        engine, _ = _tracker(chaser_ccs=[20], flash_ccs=[24])
        engine.on_midi_in(channel=1, cc=24, value=0, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_CHASER)

    def test_no_cc_config_means_cc_input_ignored(self) -> None:
        engine, _ = _tracker()
        # Engine has no chaser_ccs/flash_ccs/select_cc — the on_midi_in
        # path is a no-op even for CC values.
        engine.on_midi_in(channel=1, cc=20, value=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_CHASER)


class SteamInputLayerTrackerObserverTests(unittest.TestCase):
    def test_observer_fires_on_layer_change(self) -> None:
        engine, _ = _tracker()
        seen: list[str] = []
        engine.add_observer(lambda layer: seen.append(layer))
        engine.on_note_in(channel=1, note=68, velocity=127, now=0.0)
        self.assertEqual(seen, [LAYER_FLASH])
        engine.on_note_in(channel=1, note=64, velocity=127, now=0.1)
        self.assertEqual(seen, [LAYER_FLASH, LAYER_CHASER])

    def test_observer_does_not_fire_on_noop_change(self) -> None:
        engine, _ = _tracker()
        seen: list[str] = []
        engine.add_observer(lambda layer: seen.append(layer))
        # Already on chaser; chaser-note shouldn't fire observer.
        engine.on_note_in(channel=1, note=64, velocity=127, now=0.0)
        self.assertEqual(seen, [])

    def test_observer_exception_does_not_break_engine(self) -> None:
        engine, _ = _tracker()
        def bad_observer(layer: str) -> None:
            raise RuntimeError("boom")
        seen: list[str] = []
        engine.add_observer(bad_observer)
        engine.add_observer(lambda layer: seen.append(layer))
        engine.on_note_in(channel=1, note=68, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_FLASH)
        # Second observer (sane) still fires.
        self.assertEqual(seen, [LAYER_FLASH])


class SteamInputLayerTrackerOscEmitTests(unittest.TestCase):
    def test_osc_emit_broadcasts_layer_string(self) -> None:
        engine, osc = _tracker(emit_osc=True)
        engine.on_note_in(channel=1, note=68, velocity=127, now=0.0)
        # First send is the layer string.
        layer_sends = [s for s in osc.sends if s[0] == "/bridge/steaminput/currentlayer"]
        self.assertEqual(layer_sends, [("/bridge/steaminput/currentlayer", LAYER_FLASH)])

    def test_osc_disabled_does_not_send(self) -> None:
        engine, osc = _tracker(emit_osc=False)
        engine.on_note_in(channel=1, note=68, velocity=127, now=0.0)
        self.assertEqual(osc.sends, [])

    def test_shutdown_closes_osc(self) -> None:
        engine, osc = _tracker(emit_osc=True)
        engine.shutdown()
        self.assertTrue(osc.closed)


class SteamInputLayerTrackerStatusTests(unittest.TestCase):
    def test_status_reports_state(self) -> None:
        engine, _ = _tracker()
        status = engine.status()
        self.assertEqual(status["current_layer"], LAYER_CHASER)
        self.assertEqual(status["chaser_notes"], [64, 65, 66, 67])
        self.assertEqual(status["flash_notes"], [68, 69, 70, 71])
        self.assertEqual(status["select_note"], 72)

    def test_status_after_change_reports_new_layer(self) -> None:
        engine, _ = _tracker()
        engine.on_note_in(channel=1, note=68, velocity=127, now=1.5)
        status = engine.status()
        self.assertEqual(status["current_layer"], LAYER_FLASH)
        self.assertEqual(status["layer_change_count"], 1)
        self.assertEqual(status["last_change_at"], 1.5)


if __name__ == "__main__":
    unittest.main()

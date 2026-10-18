from pathlib import Path
from types import SimpleNamespace

from procbox.platforms.activity import ActivityMonitor, ActivitySnapshot
from procbox.ui.effects import Effect
from procbox.ui.presence import ActivityEffectDirector


def monitor() -> ActivityMonitor:
    return ActivityMonitor(helper_path=Path("/missing/procbox-activity"))


def test_helper_payload_maps_camera_to_frontmost_and_audio_pids() -> None:
    activity = monitor()
    activity._consume_helper_payload(
        {"frontmost": 12, "camera": True, "audio_in": [3], "audio_out": ["4"]}
    )
    snapshot = activity.snapshot()
    assert snapshot.frontmost_pid == 12
    assert snapshot.camera_active
    assert snapshot.camera_pid == 12
    assert snapshot.audio_input_pids == {3}
    assert snapshot.audio_output_pids == {4}

    activity._consume_helper_payload({"frontmost": 13, "camera": False})
    assert not activity.snapshot().camera_active
    assert activity.snapshot().camera_pid is None


def test_typing_payload_and_permission_warning() -> None:
    activity = monitor()
    activity._consume_helper_payload({"typing": "12"})
    assert activity.snapshot().typing_pids == {12}

    activity._consume_helper_payload({"error": "input_monitoring_permission"})
    assert "input_monitoring_permission" in activity.snapshot().warnings


def test_nettop_rate_detects_busy_process() -> None:
    activity = monitor()
    activity._consume_nettop("header\nSafari.123,0,0,\n")
    assert activity.snapshot().network_pids == set()

    activity._consume_nettop("header\nSafari.123,10000,2000,\n")
    assert activity.snapshot().network_pids == {123}


def test_effect_priority_and_pid_matching() -> None:
    sprite = SimpleNamespace(app=SimpleNamespace(pids=(7,)), is_alive=True)
    snapshot = ActivitySnapshot(
        typing_pids={7},
        network_pids={7},
        audio_output_pids={7},
        camera_pid=7,
    )
    assert ActivityEffectDirector._effect_for(sprite, snapshot) is Effect.TYPING

    snapshot.typing_pids.clear()
    assert ActivityEffectDirector._effect_for(sprite, snapshot) is Effect.CAMERA

    snapshot.camera_pid = None
    assert ActivityEffectDirector._effect_for(sprite, snapshot) is Effect.AUDIO

    snapshot.audio_output_pids.clear()
    assert ActivityEffectDirector._effect_for(sprite, snapshot) is Effect.NETWORK

    assert ActivityEffectDirector._effect_for(sprite, ActivitySnapshot()) is None


def test_audio_output_falls_back_to_frontmost_but_input_does_not() -> None:
    sprite = SimpleNamespace(app=SimpleNamespace(pids=(7,)), is_alive=True)
    snapshot = ActivitySnapshot(audio_output_pids={99}, frontmost_pid=7)

    assert ActivityEffectDirector._effect_for(sprite, snapshot) is None
    assert ActivityEffectDirector._effect_for(sprite, snapshot, {99}) is Effect.AUDIO

    snapshot.audio_output_pids = set()
    snapshot.audio_input_pids = {99}
    assert ActivityEffectDirector._effect_for(sprite, snapshot, set()) is None


def test_camera_falls_back_to_frontmost_when_owner_is_unknown() -> None:
    sprite = SimpleNamespace(app=SimpleNamespace(pids=(7,)), is_alive=True)
    snapshot = ActivitySnapshot(camera_active=True, camera_pid=None, frontmost_pid=7)

    assert ActivityEffectDirector._effect_for(sprite, snapshot) is None
    assert (
        ActivityEffectDirector._effect_for(sprite, snapshot, camera_fallback=True) is Effect.CAMERA
    )

    snapshot.camera_pid = 7
    assert ActivityEffectDirector._effect_for(sprite, snapshot) is Effect.CAMERA

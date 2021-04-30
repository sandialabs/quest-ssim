"""Tests for :py:mod:`ssim.reliability`."""
from ssim import reliability


def test_Event_to_json_from_json():
    event = reliability.Event(reliability.EventType.FAIL,
                              reliability.Mode.OPEN,
                              "device-foo")
    assert event == reliability.Event.from_json(event.to_json())
    event = reliability.Event(reliability.EventType.RESTORE,
                              reliability.Mode.CURRENT,
                              "device-bar",
                              data={"foo": 1})
    assert event == reliability.Event.from_json(event.to_json())

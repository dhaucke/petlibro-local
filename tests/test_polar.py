"""Polar Wet Food Feeder (PLAF109), payloads as in the 2026-10-11 capture
(run: .venv/bin/python -m pytest -q -p no:aiohttp tests)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "addon" / "app"))

import asyncio  # noqa: E402

import devices  # noqa: E402
import ha_mqtt  # noqa: E402
import storage  # noqa: E402


class _Client:
    def __init__(self):
        self.sent = {}

    async def publish(self, topic, payload, retain=False):
        self.sent[topic] = payload


def test_polar_commands_match_the_app(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    sent = []

    async def fake_send(serial, payload):
        sent.append(payload)
        return True

    monkeypatch.setattr(devices, "send_command", fake_send)
    storage.save_device("AF05TEST", {"device_type": "polar", "model": "AF05"})
    devices.register_device("AF05TEST", "AF05", "polar")
    devices._state["AF05TEST"] = {"platePosition": 2, "lightAgingType": 1}

    async def run():
        assert await devices.polar_command("AF05TEST", {"_feed_now": True})
        plan = sent[-1]["plans"][0]
        assert sent[-1]["cmd"] == "WET_GRAIN_FEEDING_PLAN_SERVICE"
        assert plan["planId"] == 666666666 and plan["feedNowState"] is True and plan["plate"] == 2
        assert plan["feedingDuration"] == 240 and len(plan["executionTime"]) == 5
        assert await devices.polar_command("AF05TEST", {"_stop_feeding": True})
        assert sent[-1] == {"cmd": "WET_FOOD_FEED_STOP_SERVICE", "planId": 666666666}
        assert await devices.polar_command("AF05TEST", {"_plate_position": "3"})
        assert sent[-1] == {"cmd": "SET_PLATE_POS_SERVICE", "platePosition": 3}
        assert await devices.polar_command("AF05TEST", {"_plate_position": 4}) is False
        assert await devices.polar_command("AF05TEST", {"_light": False})
        assert sent[-1] == {"lightSwitch": False, "lightAgingType": 1}
        assert await devices.polar_command("AF05TEST", {"_sound": True})
        assert sent[-1] == {"soundSwitch": True, "soundAgingType": 1}
        # Not a Polar command, other code handles it
        assert await devices.polar_command("AF05TEST", {"volume": 3}) is None

    asyncio.run(run())

    devices._handle_wet_feed_step("AF05TEST", {"execStep": "OPEN_DOOR", "finished": False, "plate": 2})
    assert devices._state["AF05TEST"]["feeding"] is True
    for _ in range(2):  # sent twice by the feeder, logged once
        devices._handle_wet_feed_step("AF05TEST", {"execStep": "GRAIN_END", "finished": True, "plate": 2,
                                                   "planId": 666666666, "execTime": 1791744410255})
    assert devices._state["AF05TEST"]["feeding"] is False
    log = storage.get_feeder_log("AF05TEST")
    assert len(log) == 1
    assert log[0]["type"] == "food_dispensed" and log[0]["source"] == "manual" and log[0]["plate"] == 2
    assert storage.get_devices()["AF05TEST"]["last_fed_ts"]
    devices.unregister_device("AF05TEST")


def test_polar_home_assistant_entities(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    cfg = {"device_type": "polar", "name": "Nassfutter"}
    keys = {key for _, key, _ in ha_mqtt._entity_configs("AF05TEST", cfg, {})}
    assert {"temperature", "plate", "feeding", "feed_now", "stop_feeding", "light", "sound"} <= keys
    assert ha_mqtt.parse_command("petlibro_local/AF05TEST/plate/set", "2", "polar") == {"_plate_position": "2"}
    assert ha_mqtt.parse_command("petlibro_local/AF05TEST/light/set", "ON", "polar") == {"_light": True}
    assert ha_mqtt.parse_command("petlibro_local/AF05TEST/stop_feeding/set", "PRESS", "polar") == {"_stop_feeding": True}
    assert ha_mqtt.parse_command("petlibro_local/AF05TEST/feed_now/set", "PRESS", "polar") == {"_feed_now": True}
    client = _Client()
    asyncio.run(ha_mqtt.publish_state(client, "AF05TEST", cfg,
                                      {"temperature": 20.58, "platePosition": 3, "feeding": True, "lightSwitch": True}))
    assert client.sent[ha_mqtt.state_topic("AF05TEST", "temperature")] == "20.58"
    assert client.sent[ha_mqtt.state_topic("AF05TEST", "plate")] == "3"
    assert client.sent[ha_mqtt.state_topic("AF05TEST", "feeding")] == "ON"
    assert client.sent[ha_mqtt.state_topic("AF05TEST", "light")] == "ON"

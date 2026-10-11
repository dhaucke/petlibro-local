"""Checks for the cloud relay (run: .venv/bin/python -m pytest -q -p no:aiohttp tests)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "addon" / "app"))

import asyncio  # noqa: E402

import pytest  # noqa: E402
import relay  # noqa: E402
import storage  # noqa: E402


def test_cloud_address_refuses_local_answer():
    async def run():
        with pytest.raises(RuntimeError, match="local address"):
            await relay._cloud_address("127.0.0.1")
        with pytest.raises(RuntimeError, match="local address"):
            await relay._cloud_address("10.0.0.10")
        assert await relay._cloud_address("8.8.8.8") == "8.8.8.8"

    asyncio.run(run())


def test_passive_only_while_relay_enabled_and_running(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    sent = []

    async def fake_run(serial, model, queue, local_publish, answer_locally):
        while True:
            sent.append(await queue.get())

    monkeypatch.setattr(relay, "_run", fake_run)

    async def run():
        storage.save_device("AF01TEST", {"mqtt_user": "u", "mqtt_pass": "p"})
        relay.forward("AF01TEST", "PLAF103", "dl/PLAF103/AF01TEST/device/heartbeat/post", b"{}", None, None)
        assert not relay.is_passive("AF01TEST")  # relay off: add-on answers itself

        storage.save_device("AF01TEST", {"cloud_relay": True})
        relay.forward("AF01TEST", "PLAF103", "dl/PLAF103/AF01TEST/device/heartbeat/post", b"{}", None, None)
        await asyncio.sleep(0)
        assert relay.is_passive("AF01TEST")
        assert sent == [("dl/PLAF103/AF01TEST/device/heartbeat/post", b"{}")]

        relay._status["AF01TEST"] = "down"  # cloud unreachable: add-on takes over
        assert not relay.is_passive("AF01TEST")

        relay.stop("AF01TEST")
        assert relay.status("AF01TEST") == "off"

    asyncio.run(run())


def test_refused_reads_paho_reason_codes():
    from paho.mqtt.packettypes import PacketTypes
    from paho.mqtt.reasoncodes import ReasonCode
    assert not relay._refused([ReasonCode(PacketTypes.SUBACK, identifier=0)])
    assert relay._refused([ReasonCode(PacketTypes.SUBACK, identifier=128)])
    assert relay._refused((0, 128)) and not relay._refused((1,))


def test_failed_cloud_connection_hands_requests_back(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    monkeypatch.setattr(relay, "RETRY_SECS", 3600)
    answered = []

    async def answer_locally(serial, topic, payload):
        answered.append(topic)

    async def run():
        # No credentials: the connection attempt fails before reaching the cloud
        storage.save_device("AF01TEST", {"cloud_relay": True})
        relay.forward("AF01TEST", "PLAF103", "dl/PLAF103/AF01TEST/device/ntp/post", b"{}", None, answer_locally)
        assert relay.is_passive("AF01TEST")
        for _ in range(5):
            await asyncio.sleep(0)
        assert relay.status("AF01TEST") == "down" and not relay.is_passive("AF01TEST")
        assert answered == ["dl/PLAF103/AF01TEST/device/ntp/post"]
        # While down nothing is queued, so nothing is replayed to the cloud later
        relay.forward("AF01TEST", "PLAF103", "dl/PLAF103/AF01TEST/device/ntp/post", b"{}", None, answer_locally)
        assert relay._queues["AF01TEST"].empty()
        relay.stop("AF01TEST")

    asyncio.run(run())


def test_reply_matching():
    req = ("dl/PLAF103/AF01TEST/device/event/post", b"", "DEVICE_START_EVENT", 0.0)
    assert relay._answers(req, "dl/PLAF103/AF01TEST/device/event/sub", b'{"cmd": "DEVICE_START_EVENT"}')
    assert not relay._answers(req, "dl/PLAF103/AF01TEST/device/event/sub", b'{"cmd": "GRAIN_OUTPUT_EVENT"}')
    assert not relay._answers(req, "dl/PLAF103/AF01TEST/device/service/sub", b'{"cmd": "DEVICE_START_EVENT"}')
    ntp = ("dl/PLAF103/AF01TEST/device/ntp/post", b"", "NTP", 0.0)
    assert relay._answers(ntp, "dl/PLAF103/AF01TEST/device/ntp/sub", b'{"ts": 1}')
    grain = ("dl/PLAF103/AF01TEST/device/event/post", b'{"cmd": "GRAIN_OUTPUT_EVENT", "msgId": "a"}', "GRAIN_OUTPUT_EVENT", 0.0)
    assert relay._answers(grain, "dl/PLAF103/AF01TEST/device/event/sub", b'{"cmd": "GRAIN_OUTPUT_EVENT", "msgId": "a"}')
    assert not relay._answers(grain, "dl/PLAF103/AF01TEST/device/event/sub", b'{"cmd": "GRAIN_OUTPUT_EVENT", "msgId": "b"}')

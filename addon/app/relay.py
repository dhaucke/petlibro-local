"""Cloud relay: keeps the official Petlibro app working.

A device redirected to the local broker drops its Petlibro cloud connection, so
the app shows it offline. For a device with cloud_relay on, this module opens a
connection to the real Petlibro broker with the device's own client id and
credentials and passes messages through:

  device  --.../post-->  local Mosquitto  --(this module)-->  cloud
  device  <--.../sub---  local Mosquitto  <--(this module)--  cloud

While that cloud connection is up (or being set up) the cloud is in charge:
devices.py stops answering time, schedule and boot requests itself (see
is_passive), so the device never gets two different answers. When the cloud
cannot be reached the add-on answers locally again, as without the relay.
"""

import asyncio
import ipaddress
import json
import logging
import socket

import aiomqtt

import storage

_LOGGER = logging.getLogger(__name__)

CLOUD_PORT = 1883
RETRY_SECS = 30
QUEUE_MAX = 200
REPLY_TIMEOUT_SECS = 15
# Device requests that need an answer (the add-on's local handlers answer the same ones)
_REQUESTS = ("NTP", "GET_FEEDING_PLAN_EVENT", "DEVICE_START_EVENT", "GRAIN_OUTPUT_EVENT")

_tasks: dict[str, asyncio.Task] = {}
_queues: dict[str, asyncio.Queue] = {}
_awaiting: dict[str, list] = {}  # serial -> requests sent to the cloud, not answered yet
_answerers: dict[str, object] = {}  # serial -> answer_locally callback
_status: dict[str, str] = {}   # serial -> "connecting" | "up" | "down"


def enabled(serial: str) -> bool:
    return bool(storage.get_devices().get(serial, {}).get("cloud_relay"))


def is_passive(serial: str) -> bool:
    """True while the cloud answers this device instead of the add-on."""
    return _status.get(serial) in ("connecting", "up") and enabled(serial)


def status(serial: str) -> str:
    return _status.get(serial, "off") if enabled(serial) else "off"


async def _cloud_address(host: str) -> str:
    """Resolve the cloud host, refusing a local answer.

    A DNS rewrite of the broker name to Home Assistant would make the relay
    connect to itself, so a private, loopback or link-local address is an error.
    """
    infos = await asyncio.get_running_loop().getaddrinfo(host, CLOUD_PORT, type=socket.SOCK_STREAM)
    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise RuntimeError(
                f"{host} resolves to the local address {addr} (DNS rewrite?). "
                "Enter the broker's public IP as Cloud MQTT host in Settings.")
        return addr
    raise RuntimeError(f"{host} did not resolve")


def forward(serial: str, model: str, topic: str, payload: bytes, local_publish, answer_locally) -> None:
    """Queue a device message for the cloud, starting the relay if needed.

    answer_locally(serial, topic, payload) gets back every message still queued
    when the cloud connection fails, so the add-on answers it instead."""
    if not enabled(serial):
        return
    task = _tasks.get(serial)
    if task is None or task.done():
        _queues[serial] = asyncio.Queue(maxsize=QUEUE_MAX)
        _status[serial] = "connecting"
        _awaiting[serial] = []
        _answerers[serial] = answer_locally
        _tasks[serial] = asyncio.ensure_future(
            _run(serial, model, _queues[serial], local_publish, answer_locally))
    if _status.get(serial) == "down":
        return  # the add-on answers this one itself; replaying it later would answer twice
    queue = _queues[serial]
    if queue.full():
        # Drop the oldest rather than block the local loop; if it was a request,
        # the add-on answers it instead
        old_topic, old_payload = queue.get_nowait()
        if _cmd(old_payload) in _REQUESTS:
            asyncio.ensure_future(answer_locally(serial, old_topic, old_payload))
    queue.put_nowait((topic, payload))


def stop(serial: str, hand_back: bool = False) -> None:
    """End the relay. hand_back=True (relay switched off) lets the add-on answer
    requests that were left to the cloud; for an offline device nobody listens."""
    task = _tasks.pop(serial, None)
    if task and not task.done():
        task.cancel()
    queue = _queues.pop(serial, None)
    awaiting = _awaiting.pop(serial, [])
    answer_locally = _answerers.pop(serial, None)
    if hand_back and answer_locally:
        pending = [(r[0], r[1]) for r in awaiting]
        while queue is not None and not queue.empty():
            pending.append(queue.get_nowait())
        for topic, payload in pending:
            if _cmd(payload) in _REQUESTS:
                asyncio.ensure_future(answer_locally(serial, topic, payload))
    _status.pop(serial, None)


def stop_all() -> None:
    for serial in list(_tasks):
        stop(serial)


def _field(payload, name: str):
    try:
        return json.loads(payload).get(name)
    except Exception:
        return None


def _cmd(payload) -> str | None:
    return _field(payload, "cmd")


def _answers(request: tuple, topic: str, payload) -> bool:
    """True if a cloud message is the reply to an awaited request: it arrives on
    the request's .../sub topic, carries the same cmd (NTP replies carry none)
    and, when both carry one, the same msgId."""
    req_topic, req_payload, req_cmd = request[0], request[1], request[2]
    if topic != req_topic[: -len("/post")] + "/sub":
        return False
    if _cmd(payload) not in (req_cmd, None):
        return False
    req_id, reply_id = _field(req_payload, "msgId"), _field(payload, "msgId")
    return not (req_id and reply_id and req_id != reply_id)


def _refused(granted) -> bool:
    """True if the broker refused a subscription (SUBACK 0x80 or higher)."""
    # aiomqtt 2.x returns paho ReasonCode objects, which do not convert with int()
    return any(g.is_failure if hasattr(g, "is_failure") else g >= 128 for g in granted)


async def _run(serial: str, model: str, queue: asyncio.Queue, local_publish, answer_locally) -> None:
    prefix = f"dl/{model}/{serial}/"
    awaiting = _awaiting[serial]  # (topic, payload, cmd, sent_at): requests the cloud has not answered yet
    taken_over: list = [] # same shape: answered locally after a timeout, a late cloud reply is dropped
    loop = asyncio.get_running_loop()
    while True:
        cfg = storage.get_devices().get(serial, {})
        host = storage.get_settings().get("cloud_mqtt_host") or "mqtt.us.petlibro.com"
        try:
            if not cfg.get("mqtt_user") or not cfg.get("mqtt_pass"):
                raise RuntimeError("device has no captured MQTT credentials")
            addr = await _cloud_address(host)
            async with aiomqtt.Client(
                hostname=addr,
                port=CLOUD_PORT,
                identifier=cfg.get("mqtt_client_id") or serial,
                username=cfg["mqtt_user"],
                password=cfg["mqtt_pass"],
                keepalive=60,
            ) as cloud:
                granted = await cloud.subscribe(prefix + "#")
                if _refused(granted):
                    # Cloud ACL may refuse wildcards: fall back to the channels seen so far
                    _LOGGER.warning("Relay %s...: wildcard subscribe refused, using known channels", serial[:6])
                    for channel in ("service", "event", "ntp"):
                        if _refused(await cloud.subscribe(f"{prefix}device/{channel}/sub")):
                            raise RuntimeError(f"cloud refused the {channel} subscription")
                _status[serial] = "up"
                _LOGGER.info("Relay %s...: connected to Petlibro cloud (%s)", serial[:6], host)

                async def _pump_out():
                    while True:
                        topic, payload = await queue.get()
                        cmd = _cmd(payload)
                        if cmd in _REQUESTS:
                            # Registered before publishing, so a reply that beats the
                            # publish call still counts; a failed publish leaves it
                            # here for the local answer below.
                            awaiting.append((topic, payload, cmd, loop.time()))
                        await cloud.publish(topic, payload)

                async def _pump_in():
                    async for message in cloud.messages:
                        topic = str(message.topic)
                        # Our own .../post forwards come back on the # subscription;
                        # sending them to the local broker would loop them forever.
                        if topic.endswith("/post"):
                            continue
                        # An open request gets the reply first; only a reply nothing open
                        # is waiting for counts as a late one for a timed-out request.
                        current = next((r for r in awaiting if _answers(r, topic, message.payload)), None)
                        if current:
                            awaiting.remove(current)
                        else:
                            late = next((r for r in taken_over if _answers(r, topic, message.payload)), None)
                            if late:
                                taken_over.remove(late)
                                continue  # the device already got the local answer
                        await local_publish(topic, message.payload)

                async def _expire():
                    # A request the cloud leaves unanswered gets the local answer
                    while True:
                        await asyncio.sleep(REPLY_TIMEOUT_SECS / 3)
                        now = loop.time()
                        taken_over[:] = [r for r in taken_over if now - r[3] < 4 * REPLY_TIMEOUT_SECS]
                        for request in [r for r in awaiting if now - r[3] > REPLY_TIMEOUT_SECS]:
                            awaiting.remove(request)
                            taken_over.append(request)
                            _LOGGER.info("Relay %s...: no cloud reply to %s, answering locally", serial[:6], request[2])
                            asyncio.ensure_future(answer_locally(serial, request[0], request[1]))

                # Either direction failing ends this connection, so a dead forward
                # path can't leave the add-on silent while the status still says up.
                pumps = [asyncio.ensure_future(_pump_out()), asyncio.ensure_future(_pump_in()),
                         asyncio.ensure_future(_expire())]
                try:
                    done, _ = await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                    raise RuntimeError("cloud connection closed")
                finally:
                    for task in pumps:
                        task.cancel()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _status[serial] = "down"
            # Requests still waiting for the cloud were left unanswered locally
            pending = [(r[0], r[1]) for r in awaiting]
            awaiting.clear()
            while not queue.empty():
                pending.append(queue.get_nowait())
            for topic, payload in pending:
                asyncio.ensure_future(answer_locally(serial, topic, payload))
            _LOGGER.warning("Relay %s...: cloud not reachable (%s), retrying in %ds — "
                            "the add-on answers the device locally meanwhile",
                            serial[:6], err, RETRY_SECS)
        await asyncio.sleep(RETRY_SECS)

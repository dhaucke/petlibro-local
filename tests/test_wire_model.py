"""Commands go to the model a device uses in its own topics (run: .venv/bin/python -m pytest -q -p no:aiohttp tests)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "addon" / "app"))

import devices  # noqa: E402
import storage  # noqa: E402


def test_commands_follow_the_devices_own_model(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    storage.save_device("WF01TEST", {"device_type": "dockstream2", "model": "WF01"})
    devices.register_device("WF01TEST", "WF01", "dockstream2")
    assert devices._service_sub_topic("dockstream2", "WF01TEST") == "dl/PLWF106/WF01TEST/device/service/sub"

    devices._note_wire_model("WF01TEST", "PLWF105")
    assert devices._service_sub_topic("dockstream2", "WF01TEST") == "dl/PLWF105/WF01TEST/device/service/sub"

    # Remembered across a restart of the add-on
    devices._wire_models.clear()
    devices.register_device("WF01TEST", "WF01", "dockstream2")
    assert devices._ntp_sub_topic("dockstream2", "WF01TEST") == "dl/PLWF105/WF01TEST/device/ntp/sub"
    devices.unregister_device("WF01TEST")

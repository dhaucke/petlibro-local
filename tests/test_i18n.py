"""Checks for the German translation (run: .venv/bin/python -m pytest -q -p no:aiohttp tests)."""

import json
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "addon" / "app"
sys.path.insert(0, str(APP))

import device_types  # noqa: E402
import i18n  # noqa: E402
import storage  # noqa: E402


def _placeholders(text):
    return set(re.findall(r"\{\w+\}", text))


def test_ui_locale_complete():
    en = json.loads((APP / "locales" / "en.json").read_text())
    de = json.loads((APP / "locales" / "de.json").read_text())
    assert en.keys() == de.keys()
    for key in en:
        assert _placeholders(en[key]) == _placeholders(de[key]), key


def test_every_alert_message_has_german_text(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    for text in device_types.all_alert_messages().values():
        assert text in i18n._DE, text
    for en_text, de_text in i18n._DE.items():
        assert _placeholders(en_text) == _placeholders(de_text), en_text
    storage.save_settings({"language": "de"})
    assert i18n.tr("{pet} has not eaten in {hours} hours.", pet="Kaya", hours="12.0") == \
        "Kaya hat seit 12.0 Stunden nicht gefressen."
    storage.save_settings({"language": "en"})
    assert i18n.tr("Device is offline.") == "Device is offline."

"""Notification texts in the add-on's language.

Texts are written in English with {placeholders}; tr() swaps in the German
version when Settings > Language is German. An English text without an entry
here stays English.
"""

import storage

_DE = {
    # Alert messages (device_types/*.py ALERT_MESSAGES)
    "Device is offline.": "Gerät ist offline.",
    "Backup battery is low.": "Pufferakku ist schwach.",
    "Food bowl needs cleaning.": "Futternapf muss gereinigt werden.",
    "Cleaning is overdue.": "Reinigung ist überfällig.",
    "Desiccant needs replacing.": "Trockenmittel muss gewechselt werden.",
    "Food door is jammed, likely something is blocking it from closing.":
        "Futterklappe klemmt, vermutlich blockiert etwas das Schließen.",
    "Filter replacement is due soon.": "Filterwechsel ist bald fällig.",
    "Food hopper is empty or running low.": "Futterbehälter ist leer oder fast leer.",
    "Food tank hasn't been refilled in a while, may be running low.":
        "Futterbehälter wurde länger nicht aufgefüllt und wird womöglich knapp.",
    "Feeder housing needs cleaning.": "Gehäuse des Futterautomaten muss gereinigt werden.",
    "Running on battery power (AC lost).": "Läuft auf Akku (Netzstrom weg).",
    "Water level is low.": "Wasserstand ist niedrig.",
    # Other notifications (devices.py)
    "Device is back online.": "Gerät ist wieder online.",
    "AC power restored.": "Netzstrom ist wieder da.",
    "Power lost at {lost}, restored at {back} ({duration}).":
        "Strom weg um {lost}, wieder da um {back} ({duration}).",
    "{pet} ate for {duration} at {device}": "{pet} hat {duration} an {device} gefressen",
    "{pet} drank {ml}mL at {device}": "{pet} hat {ml} ml an {device} getrunken",
    "Your pet": "Dein Haustier",
    "Food dispensed": "Futter ausgegeben",
    "Manual": "Manuell",
    "Scheduled": "Nach Zeitplan",
    "Food dispensed - {source} - {portions} at {device}": "Futter ausgegeben – {source} – {portions} an {device}",
    "{n} portion": "{n} Portion",
    "{n} portions": "{n} Portionen",
    "Scheduled feed skipped": "Geplante Fütterung ausgelassen",
    "{device}'s clock was {minutes} min slow and has now been corrected. The {when} scheduled feed "
    "was skipped by the correction. No food was added to make up for it, feed manually if you want to.":
        "Die Uhr von {device} ging {minutes} Min. nach und wurde korrigiert. Die geplante Fütterung um {when} "
        "wurde dadurch übersprungen. Es wurde kein Futter nachgegeben, füttere bei Bedarf von Hand.",
    "Scheduled feed missed": "Geplante Fütterung verpasst",
    "The {when} scheduled feed on {device} did not dispense (nothing recorded within {minutes} minutes).":
        "Die geplante Fütterung um {when} an {device} hat nichts ausgegeben (innerhalb von {minutes} Minuten nichts erfasst).",
    "{pet} has not eaten in {hours} hours.": "{pet} hat seit {hours} Stunden nicht gefressen.",
}


def tr(text: str, **values) -> str:
    if storage.get_settings().get("language") == "de":
        text = _DE.get(text, text)
    return text.format(**values) if values else text

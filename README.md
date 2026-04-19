# 🧹 Cleanliness Tracker

Per-Room Cleanliness Scoring für Home Assistant — basierend auf Präsenz-/Bewegungsmeldern.

> Status: **v0.1.0 — MVP-Release.** Funktional komplett (Score-Tracking, Sensoren, Services, Blueprint). Roadmap siehe unten.

## ✨ Features

- 🏠 Beliebig viele Räume parallel tracken (HA-Areas)
- 📈 Score 0–100 % pro Raum, abgeleitet aus kumulierter Präsenzzeit
- 🚦 Binary-Sensor `*_due` schaltet ein, sobald der Schwellwert überschritten wird
- 🤖 Mitgelieferter Blueprint schickt deinen Saugroboter (`vacuum.clean_area`, HA 2026.3+) automatisch in alle „fälligen" Räume
- 🛠️ Services: `mark_cleaned`, `reset`, `set_score`

## 📦 Installation

### Via HACS (empfohlen)

1. HACS → Integrationen → ⋮ → Custom Repositories
2. Repo: `https://github.com/TheRealSimon42/ha-cleanliness-tracker`, Kategorie: Integration
3. Installieren → HA neu starten
4. Einstellungen → Geräte & Dienste → Integration hinzufügen → „Cleanliness Tracker"

### Manuell

1. Inhalt von `custom_components/cleanliness_tracker/` nach `<config>/custom_components/cleanliness_tracker/` kopieren
2. HA neu starten
3. Wie oben einrichten

## ⚙️ Konfiguration

Pro Raum:

- **Area** (HA-Area-Selector)
- **Presence-Entity** (`binary_sensor` mit Domain `presence` / `motion` / `occupancy`)
- **Threshold** (Default 80 %)
- **Weight per minute** (optional, Default 0.5)

## 📊 Erzeugte Entities

| Entity | Typ | Beschreibung |
|---|---|---|
| `sensor.cleanliness_<room>_score` | Sensor | 0–100 %, steigt mit Anwesenheitszeit |
| `sensor.cleanliness_<room>_last_cleaned` | Sensor (datetime) | Zeitpunkt des letzten `mark_cleaned` |
| `binary_sensor.cleanliness_<room>_due` | Binary-Sensor | `on` wenn `score >= threshold` |

## 🎯 Services

| Service | Zweck |
|---|---|
| `cleanliness_tracker.mark_cleaned` | Score → 0, `last_cleaned` → jetzt (einzelner Raum oder alle) |
| `cleanliness_tracker.reset` | Score → 0 |
| `cleanliness_tracker.set_score` | Score auf gewünschten Wert setzen (Override) |

## 🤖 Blueprint: Overdue Rooms automatisch saugen

Importiere den mitgelieferten Blueprint mit einem Klick:

[![Open Your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTheRealSimon42%2Fha-cleanliness-tracker%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fcleanliness_tracker%2Fvacuum_overdue_rooms.yaml)

Inputs:

- **Vacuum Entity** (`vacuum.*`)
- **Tageszeit** (Default: 09:00)
- **Notification-Service** (optional)

Aktion: ruft `vacuum.clean_area` für alle Areas auf, deren `binary_sensor.cleanliness_<room>_due` gerade `on` ist.

## 🛠️ Beispiel-Automation (manuell)

```yaml
alias: Wohnzimmer saugen wenn fällig
trigger:
  - platform: state
    entity_id: binary_sensor.cleanliness_wohnzimmer_due
    to: "on"
    for: "01:00:00"
action:
  - action: vacuum.clean_area
    target:
      entity_id: vacuum.saugroboter
    data:
      area_id: wohnzimmer
  - action: cleanliness_tracker.mark_cleaned
    data:
      room: wohnzimmer
```

## 🏗️ Architektur (Kurz)

- **Event-driven** via `async_track_state_change_event` (kein DataUpdateCoordinator)
- Periodischer Tick (5 min) für noch laufende Präsenz-Sessions
- Pure-Logic-Modul `soil_calculator.py` ohne HA-Imports — 100 % Test-Coverage
- Pro `ConfigEntry` ein `Store`

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/SCORE_MODEL.md`](docs/SCORE_MODEL.md).

## 🤝 Contributing

Siehe [`CONTRIBUTING.md`](CONTRIBUTING.md) und [`AGENTS.md`](AGENTS.md).

## 📋 Roadmap

- **v0.1.0** (MVP): Score-Tracking, Sensoren, Services, Blueprint
- **v0.2.0**: konfigurierbare Score-Decay-Funktion
- **v0.3.0**: Optionen-Flow zum nachträglichen Editieren von Räumen
- **v0.4.0**: Auto-Reset durch Vacuum-State (`vacuum.cleaned`)

## 📄 Lizenz

[CC BY-NC-SA 4.0](LICENSE) — frei für private, nicht-kommerzielle Nutzung.
Kommerzielle Lizenz: <https://www.simon42.com/contact/>

## 🙏 Credits

- HA-Team für die [`vacuum.clean_area`](https://www.home-assistant.io/integrations/vacuum/)-Action ab 2026.3
- Entstanden im Workflow von [simon42](https://www.simon42.com)

# Changelog

Alle relevanten Änderungen werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

## [0.1.0] - 2026-04-19

### Added

- **Erstes MVP-Release.** Eine HACS-kompatible Custom Integration, die pro Wohnraum einen Sauberkeits-Score (0–100 %) aus Präsenz-/Bewegungsmeldern führt.
- **Pure-Logic-Modul** `soil_calculator.py` (ohne HA-Imports, 100 % Coverage): `compute_score_delta(presence_seconds, weight_per_minute)` und `apply_delta(current_score, delta, cap=100)`.
- **`RoomTracker`** kapselt den Lifecycle pro Raum: Idempotenter `on_presence_start`, deltabasierter `on_presence_end`, periodischer Tick (alle 5 min) für laufende Sessions, `mark_cleaned`, `reset`, `set_score`. Update-Listener-Pattern für Sensor-Re-Renders.
- **`CleanlinessStore`** (eigener Store pro `ConfigEntry`, JSON via `homeassistant.helpers.storage`): hält pro Raum `current_score`, `presence_started_at`, `last_cleaned_at`, `last_scored_at` (Datetimes als ISO-8601 mit Timezone).
- **Config Flow + Subentries**: User-Step für den Integration-Namen plus pro Raum ein Subentry mit Area-Selector, Presence-Entity-Selector, Threshold-Number (Default 80) und Weight-Number (Default 0.5). Reconfigure mit Pre-Fill.
- **Drei Entities pro Raum**: `sensor.*_score` (0–100 % MEASUREMENT), `sensor.*_last_cleaned` (TIMESTAMP), `binary_sensor.*_due` (PROBLEM, exposes `area_id` als Attribute).
- **Domain-Services** `cleanliness_tracker.mark_cleaned`, `cleanliness_tracker.reset`, `cleanliness_tracker.set_score` mit Entity-Selectors.
- **Blueprint** `blueprints/automation/cleanliness_tracker/vacuum_overdue_rooms.yaml`: täglicher Time-Trigger ruft `vacuum.clean_area` (HA 2026.3+) für jede `_due`-Area, optionaler Notification-Service.
- **Translations** Deutsch + Englisch für Config-Flow, Subentries, Entity-Names und Service-Felder.
- **CI**: 5 GitHub-Workflows (validate via Hassfest + HACS, lint via Ruff + Mypy --strict, pytest auf Python 3.13, tag-based release mit Auto-Generated Release-Notes, stale-bot).
- **Quality-Gates**: 111 Tests, ruff + mypy --strict + Hassfest grün auf jedem PR. `soil_calculator`, `tracker`, `storage`, `models`, `const`, `config_flow` jeweils 100 % Line+Branch Coverage.

[Unreleased]: https://github.com/TheRealSimon42/ha-cleanliness-tracker/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/TheRealSimon42/ha-cleanliness-tracker/releases/tag/v0.1.0

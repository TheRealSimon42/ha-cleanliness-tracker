# ha-cleanliness-tracker — Agent Entry Point

> Einziger Einstiegspunkt für KI-Coding-Agents (Claude Code, Codex, Cursor, …).
> Wenn du ein Agent bist: **Lies diese Datei zuerst vollständig**, dann
> schau in `docs/ARCHITECTURE.md` und `docs/SCORE_MODEL.md` für Details.

---

## Projekt in einem Satz

Eine Home-Assistant-Custom-Integration (HACS-kompatibel), die pro Wohnraum einen
**Sauberkeits-Score** (0–100) führt — basierend auf Präsenz- oder Bewegungsmeldern.
Score steigt mit kumulierter Anwesenheitszeit; ab Threshold ist der Raum „due".

## Zielgruppe

HA-User mit Saugroboter, die **zeitbasiert statt intervallbasiert** saugen wollen
(z. B. „Wohnzimmer wurde 4 h genutzt → saugen", statt „immer mittwochs").

## Scope

### Drin

- Config Flow: mehrere Räume (HA-Areas) auswählen, pro Raum Presence-Entity + Threshold + optional Weight
- Pro Raum Entities:
  - `sensor.cleanliness_<room>_score` (0–100, unit %)
  - `sensor.cleanliness_<room>_last_cleaned` (datetime)
  - `binary_sensor.cleanliness_<room>_due` (on wenn `score >= threshold`)
- Services:
  - `cleanliness_tracker.mark_cleaned` (einzelner Raum oder alle)
  - `cleanliness_tracker.reset` (Score → 0)
  - `cleanliness_tracker.set_score` (manueller Override)
- Blueprint: `vacuum_overdue_rooms.yaml` → `vacuum.clean_area` für alle Räume mit `_due == on` (HA 2026.3+)

### Draußen

- Eigene Vacuum-Steuerung (das macht HA-Core ab 2026.3)
- Herstellerspezifische Hacks
- Map-Integration
- Automatischer Reset durch Vacuum-State (kommt frühestens v0.4)

---

## Architektur in 30 Sekunden

```
Presence-Entity State-Change ─┐
                              ├─► RoomTracker.on_presence_start/end ─► Store (per ConfigEntry)
async_track_time_interval(5m)─┘                                   │
                                                                  ▼
                                                  sensor / binary_sensor (event-driven)
```

- **Kein DataUpdateCoordinator.** Reines Event-Modell auf State-Changes plus Time-Tick.
- Pro Raum ein `RoomTracker` mit Store-Persistence.
- Pure-Logic-Modul `soil_calculator.py` ohne HA-Imports — 100 % Coverage.

Details: `docs/ARCHITECTURE.md` und `docs/SCORE_MODEL.md`.

## Score-Formel (MVP)

```
delta_score = presence_minutes × presence_weight_per_minute
new_score   = min(current_score + delta_score, 100)
```

Defaults: `presence_weight_per_minute = 0.5`, `threshold = 80`.
Konfigurierbar pro Raum.

---

## Hard Rules

Diese Punkte sind nicht verhandelbar.

1. **Keine HA-Imports in `soil_calculator.py`.** Pure logic. Niemals.
2. **Kein `DataUpdateCoordinator`.** Wir sind event-driven (`async_track_state_change_event` + `async_track_time_interval`).
3. **Keine naiven `datetime`.** `homeassistant.util.dt` strikt nutzen.
4. **Pro `ConfigEntry` ein `Store`.** Persistenz via `homeassistant.helpers.storage.Store`.
5. **Kein `device_id`.** Nur `entity_id` referenzieren.
6. **Alle User-Facing-Strings via Translations.** Source: `strings.json`, Spiegel: `translations/de.json` + `translations/en.json`. Kein hardcoded Deutsch im Code (Logger ausgenommen).
7. **TDD für Pure-Logic.** `soil_calculator.py` und `tracker.py` werden test-first entwickelt, 100 % Line+Branch Coverage für `soil_calculator.py`.
8. **HA-Floor 2026.3** konsistent in `manifest.json`, `hacs.json`, `pyproject.toml` (wegen `vacuum.clean_area`-Action).

---

## Coding Standards (kurz)

Volle Details in `docs/STANDARDS.md`.

- **Formatter:** `ruff format` (Line-Length 88)
- **Linter:** `ruff check` (Regeln in `pyproject.toml`)
- **Type-Checker:** `mypy --strict` auf `custom_components/cleanliness_tracker/`
- **Docstrings:** Google-Style für alle öffentlichen Klassen + Funktionen
- **Imports:** stdlib → third-party → homeassistant → first-party
- **Editor:** `.editorconfig` (UTF-8, LF, 4 Spaces Python, 2 Spaces YAML/JSON)
- **Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
- **PRs:** mindestens ein Test für neue Logik, `CHANGELOG.md`-Eintrag, grüne CI

## Sprache

- UI-Strings: **Deutsch** (Source `strings.json`)
- Code-Kommentare + Docstrings: **Englisch**
- Commits + PR-Titel: **Englisch**

---

## Workflow für Pure-Logic (TDD)

`soil_calculator.py` und `tracker.py` immer in dieser Reihenfolge:

1. Failing Test schreiben in `tests/test_<module>.py`
2. Minimum-Implementation in `custom_components/cleanliness_tracker/<module>.py`
3. `make test` → grün
4. Refactor mit grünen Tests
5. Coverage prüfen: `make cov` → für `soil_calculator.py` müssen 100 % Line+Branch erreicht werden

## Workflow pro Phase-1-Schritt

1. Feature-Branch (`feat/<scope>`)
2. Implementieren + Tests
3. `make all` lokal grün
4. PR öffnen → CI grün → Squash-Merge
5. STOPP, nächster Schritt

---

## Wo finde ich was?

| Frage | Quelle |
|---|---|
| Was soll die Integration können? | Dieses Dokument + `docs/ARCHITECTURE.md` |
| Wie wird der Score berechnet? | `docs/SCORE_MODEL.md` |
| Wie ist der Code zu formatieren? | `docs/STANDARDS.md` + `pyproject.toml` |
| HA-API-Details | <https://developers.home-assistant.io/> |
| HACS-Requirements | <https://hacs.xyz/docs/publish/integration/> |

## Änderungen an diesem Dokument

`AGENTS.md` ist die „Verfassung" des Projekts. Änderungen nur via PR mit
expliziter Motivation in der PR-Beschreibung.

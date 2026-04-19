# Architecture

## Datenfluss

```
┌──────────────────────────────────────────────────────────────────┐
│ User-Setup via Config Flow                                       │
│  - Integration-Name                                              │
│  - Pro Raum: Area, Presence-Entity, Threshold, Weight            │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
                ┌────────────────────────────┐
                │ ConfigEntry (Subentries)   │
                └─────────────┬──────────────┘
                              │
                ┌─────────────┴──────────────┐
                ▼                            ▼
   ┌──────────────────────────┐   ┌────────────────────────────┐
   │ async_track_state_change │   │ async_track_time_interval  │
   │ (Presence-Entities)      │   │ (alle TICK_INTERVAL_SEC)   │
   └─────────────┬────────────┘   └─────────────┬──────────────┘
                 │                              │
                 ▼                              ▼
            ┌──────────────────────────────────────┐
            │   RoomTracker (pro Raum, in-memory   │
            │   + Store-Persistence)               │
            │   - on_presence_start                │
            │   - on_presence_end                  │
            │   - periodic_update                  │
            │   - mark_cleaned / set_score         │
            └─────────────────┬────────────────────┘
                              │
                              ▼
                ┌────────────────────────────┐
                │  CleanlinessStore          │
                │  pro ConfigEntry           │
                │  { room_id: RoomState }    │
                └─────────────┬──────────────┘
                              │ Snapshot lesen / async_save
                              ▼
            ┌──────────────────────────────────────┐
            │  Entities (event-driven, kein Poll)  │
            │  - sensor.<room>_score               │
            │  - sensor.<room>_last_cleaned        │
            │  - binary_sensor.<room>_due          │
            └──────────────────────────────────────┘
```

## Bewusste Nicht-Architektur

- **Kein `DataUpdateCoordinator`.** Wir aggregieren keine externe Datenquelle, sondern reagieren auf HA-State-Changes. Coordinator wäre Overhead.
- **Kein `device_id`.** Pro Raum gehört eine Presence-Entity dazu, referenziert per `entity_id`.
- **Keine YAML-Config.** Setup via Config Flow + Subentries.

## Komponenten

| Datei | Verantwortung |
|---|---|
| `__init__.py` | `async_setup_entry`, Listener-Wiring (State-Change + Tick), `async_unload_entry`, Service-Registry |
| `config_flow.py` | Config Flow + Subentry pro Raum (Area + Presence + Threshold + Weight) |
| `const.py` | Domain, Storage-Version, Conf-Keys, Defaults |
| `models.py` | TypedDicts: `RoomConfig`, `RoomState`, `EntryData` |
| `soil_calculator.py` | **Pure logic** — `compute_score_delta`, `apply_delta`. Keine HA-Imports. |
| `storage.py` | `CleanlinessStore` — `async_load` / `async_save` pro ConfigEntry |
| `tracker.py` | `RoomTracker` — kapselt State + Lifecycle-Methoden pro Raum |
| `sensor.py` | Score-Sensor + Last-Cleaned-Sensor |
| `binary_sensor.py` | Due-Binary-Sensor |
| `services.yaml` | Service-Schemata |

## Lifecycle

1. **Setup:**
   - Store laden (oder leer initialisieren)
   - Pro Raum aus Subentries einen `RoomTracker` instanziieren (mit geladenem `RoomState`)
   - Listener registrieren: `async_track_state_change_event` + `async_track_time_interval`
   - Sensor- + Binary-Sensor-Plattformen forwarden
2. **Runtime:**
   - State-Change Presence-Entity → `RoomTracker.on_presence_start` / `on_presence_end`
   - Time-Tick → `RoomTracker.periodic_update` für Räume mit aktiver Presence
   - Service-Call `mark_cleaned` → `RoomTracker.mark_cleaned`
3. **Unload:**
   - Listener entfernen
   - Plattformen unloaden
   - State-Save (final) → Store

## Persistence-Schema

`CleanlinessStore` (`Store` mit `STORAGE_VERSION = 1`):

```json
{
  "rooms": {
    "<room_id>": {
      "current_score": 42.5,
      "presence_started_at": "2026-04-19T13:42:00+00:00",
      "last_cleaned_at": "2026-04-18T08:00:00+00:00",
      "last_scored_at": "2026-04-19T13:47:00+00:00"
    }
  }
}
```

Alle Datetimes als ISO-8601 mit Timezone (via `homeassistant.util.dt`).

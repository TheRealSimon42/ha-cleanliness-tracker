# Score-Model

## Formel

```
delta_score = presence_minutes × presence_weight_per_minute
new_score   = min(current_score + delta_score, 100)
```

- `presence_minutes`: vergangene Minuten zwischen `presence_started_at` und „jetzt" bzw. State-Off-Event
- `presence_weight_per_minute`: pro Raum konfigurierbar (Default `0.5`)
- Cap bei `100` (kein Wachstum darüber hinaus)

## Defaults

| Parameter | Wert |
|---|---|
| `DEFAULT_PRESENCE_WEIGHT` | `0.5` |
| `DEFAULT_THRESHOLD` | `80` |
| `TICK_INTERVAL_SECONDS` | `300` (5 min) |

## Beispielrechnungen

### Ruhiger Tag

- Wohnzimmer ist 60 min besetzt
- `delta = 60 × 0.5 = 30` → Score steigt um 30

### Aktiver Sonntag

- Wohnzimmer ist 8 h (480 min) besetzt, Start-Score = 0
- `delta = 480 × 0.5 = 240` → kappt bei 100
- Threshold 80 erreicht nach 160 min (≈ 2 h 40 min)

### Bad mit höherer Gewichtung

- `weight = 2.0` (Bad wird schneller schmutzig pro Anwesenheitsminute)
- 30 min Anwesenheit
- `delta = 30 × 2.0 = 60`

## Wann steigt der Score?

Der Score wird **nur** in zwei Fällen aktualisiert:

1. **Presence-Off-Event:** State-Change `on → off`. Tracker rechnet das Delta von `presence_started_at` bis jetzt und addiert.
2. **Periodischer Tick:** Alle `TICK_INTERVAL_SECONDS`. Für Räume mit noch aktiver Presence: Delta von `last_scored_at` (oder `presence_started_at`) bis jetzt addieren, `last_scored_at = now`.

So wächst der Score auch bei *langen* Anwesenheits-Sessions, ohne dass jede Sekunde ein Event fließt.

## Was setzt den Score zurück?

- `cleanliness_tracker.mark_cleaned` → Score = 0, `last_cleaned_at = now`
- `cleanliness_tracker.reset` → Score = 0 (kein `last_cleaned`-Update)
- `cleanliness_tracker.set_score` → Score = `<Wert>` (Override)

**Nicht** automatisch durch Vacuum-State (kommt frühestens in v0.4).

## Due-Binary-Sensor

`binary_sensor.cleanliness_<room>_due` ist `on` ⇔ `current_score >= threshold`.

Der Sensor wird auf jede Score-Änderung neu evaluiert (event-driven).

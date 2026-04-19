# Cleanliness Tracker

Pro Wohnraum einen "Sauberkeits-Score" (0–100) auf Basis von Präsenz- oder Bewegungsmeldern.

## Was die Integration kann

- Mehrere Räume parallel tracken (HA-Areas)
- Pro Raum Presence-/Motion-Entity zuordnen, Threshold setzen, optional individuelle Gewichtung
- Pro Raum drei Entities: Score-Sensor (0–100 %), Last-Cleaned-Sensor, Due-Binary-Sensor
- Services zum manuellen Markieren als gereinigt, Reset oder Score-Override
- Mitgelieferter Blueprint: Saugroboter automatisch in alle "fälligen" Räume schicken (`vacuum.clean_area`, ab HA 2026.3)

## Einrichtung

Einstellungen → Geräte & Dienste → Integration hinzufügen → "Cleanliness Tracker"

Details in der [README](https://github.com/TheRealSimon42/ha-cleanliness-tracker#readme).

# Contributing

Vielen Dank, dass du beitragen möchtest!

## Setup

```bash
make install   # editable install + dev extras + pre-commit hooks
```

## Workflow

1. Feature-Branch von `main` abzweigen (`feat/...`, `fix/...`, `chore/...`)
2. **TDD**: Tests zuerst, wo sinnvoll (insbesondere `soil_calculator.py`, `tracker.py`)
3. Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
4. PR gegen `main` öffnen
5. Grüne CI (Lint + Test + Validate) ist Pflicht
6. Squash-Merge

## Quality Gates

```bash
make all        # fmt + lint + type + test
pre-commit run --all-files
```

- **Coverage:** mindestens 80 % gesamt, **100 % Line+Branch** für `soil_calculator.py`
- **mypy --strict** muss grün sein
- **ruff check + ruff format --check** müssen grün sein

## Sprache

- UI-Strings: Deutsch (Source `strings.json`, gespiegelt in `translations/de.json` und `translations/en.json`)
- Code-Kommentare und Docstrings: Englisch (Google-Style)
- Commits & PR-Titel: Englisch
- Issues & PR-Beschreibungen: Deutsch ist okay

## Hard Rules

Siehe `AGENTS.md` → "Hard Rules". Kurzfassung:

- **Keine HA-Imports in `soil_calculator.py`** — pure logic, niemals.
- **Kein DataUpdateCoordinator** — wir sind event-driven.
- **Keine naiven `datetime`** — `homeassistant.util.dt` strikt nutzen.
- **Alle User-Facing-Strings via Translations** — kein hardcoded Deutsch im Code (Logger ausgenommen).

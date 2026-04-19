# Standards

Spiegelt die Standards aus
[`ha-hauskosten/docs/STANDARDS.md`](https://github.com/TheRealSimon42/ha-hauskosten/blob/main/docs/STANDARDS.md).
Hier nur die Kurzfassung — die Konfig-Files sind die Source of Truth.

## Tooling

| Tool | Datei | Aufruf |
|---|---|---|
| Formatter | `pyproject.toml` (`[tool.ruff.format]`) | `ruff format custom_components/cleanliness_tracker tests` |
| Linter | `pyproject.toml` (`[tool.ruff.lint]`) | `ruff check custom_components/cleanliness_tracker tests` |
| Type-Checker | `pyproject.toml` (`[tool.mypy]`) | `mypy --strict custom_components/cleanliness_tracker` |
| Tests | `pyproject.toml` (`[tool.pytest.ini_options]`) | `pytest` |
| Pre-Commit | `.pre-commit-config.yaml` | `pre-commit run --all-files` |

Bequem über `make all`.

## Ruff-Regeln (Highlights)

- Line-Length 88
- Selektiert: `E, W, F, I, B, UP, SIM, RUF, C4, N, D, ANN, S, TID, ARG, PTH, PL, PT, RET, TRY`
- Ignoriert: `D203, D213, ANN401, PLR0913, TRY003`
- Tests dürfen ohne Docstrings + Type-Annotations leben

## Mypy

- `strict = true`, alle `disallow_*`-Flags an
- Tests sind etwas lockerer (`disallow_untyped_defs = false`)

## Coverage

- **Gesamt:** 80 % (wird gegen Phase 1 hochgezogen)
- **`soil_calculator.py`:** 100 % Line + Branch (non-negotiable)

## Docstrings

- Google-Style
- Pflicht für alle öffentlichen Klassen + Funktionen
- Bei Pure-Logic (`soil_calculator.py`): `Args:`, `Returns:`, `Raises:` immer angeben

## Imports

ruff/isort-Style mit eigener `homeassistant`-Section:

```
future
standard-library
third-party
homeassistant
first-party (custom_components.cleanliness_tracker)
local-folder
```

## Commits

Conventional Commits:

- `feat: …` — Neues Feature
- `fix: …` — Bugfix
- `refactor: …` — Code-Restrukturierung ohne Verhaltensänderung
- `docs: …` — nur Doku
- `test: …` — nur Tests
- `chore: …` — Build, CI, Konfig
- Optional Scope: `feat(tracker): …`
- Breaking-Change-Footer: `BREAKING CHANGE: …`

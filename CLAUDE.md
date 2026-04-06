# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PACS-to-Orthanc migration tool. Discovers studies on a source PACS via DICOM C-FIND (orchestrated through Orthanc's REST API), migrates them via C-MOVE, and tracks progress in SQLite for resumability.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI commands directly
python -m src.cli run              # Discover + migrate in one step
python -m src.cli discover         # C-FIND studies on source PACS
python -m src.cli discover --skip-echo  # Skip C-ECHO connectivity check
python -m src.cli migrate          # C-MOVE pending studies to destination
python -m src.cli status           # Show migration progress
python -m src.cli verify           # Compare tracked vs actual studies in Orthanc
python -m src.cli retry            # Reset failed studies and re-migrate

# Docker Compose (includes source + destination Orthanc instances)
docker compose up --build                    # Run full stack with default "run" command
docker compose run migrator discover         # Run specific command
docker compose run migrator status

# Seed test data into source Orthanc
python scripts/seed_source.py --count 100
```

No test suite, linter, or formatter is configured.

## Architecture

All DICOM operations go through an existing Orthanc instance's REST API (via pyorthanc) — this tool does **not** speak DICOM directly. Orthanc handles the DICOM protocol; this tool orchestrates via HTTP.

```
Source PACS  <──DICOM──>  Orthanc (dest)  <──REST API──>  Migrator CLI
                                                              │
                                                         SQLite tracker
```

### Key modules

- **`src/cli.py`** — Typer CLI entry point. Configures loguru logging (stderr + rotating file at `data/migration.log`).
- **`src/config.py`** — Pydantic Settings singleton (`settings`), loaded from `.env`. Ignores extra env vars.
- **`src/orthanc_client.py`** — Factory for pyorthanc.Orthanc client. Supports optional auth and configurable timeout.
- **`src/services/discovery.py`** — C-FIND with smart pagination: queries by month, drills down to daily if a month hits the 100-result Orthanc limit.
- **`src/services/migrator.py`** — C-MOVE with exponential backoff retry. Processes studies in batches, verifies arrival after each move.
- **`src/services/tracker.py`** — SQLite database (`data/migration.db`). Tracks study status (`pending` → `in_progress` → `completed`/`failed`). Enables crash-recovery resumability.
- **`src/services/verifier.py`** — Compares tracker state against actual Orthanc contents to find mismatches.

### Configuration

All config flows through `src/config.py` (`Settings` class) loaded from `.env`. See `.env.example` for all available variables. Key settings: `SOURCE_MODALITY`, `ORTHANC_URL`, `ORTHANC_USERNAME/PASSWORD`, `BATCH_SIZE`, `MAX_RETRIES`, `DATE_FROM/DATE_TO`.

### Docker Compose services

- **orthanc-source** (port 8043) — simulates the third-party PACS
- **orthanc-dest** (port 8042) — destination Orthanc instance
- **migrator** — this tool, with `migrator-data` volume for SQLite persistence

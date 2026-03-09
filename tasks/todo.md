# Task: PACS-to-Orthanc Migration Tool

## Overview
CLI tool that migrates all studies from a third-party PACS into an existing Orthanc
instance using C-FIND/C-MOVE, orchestrated via pyorthanc's REST API.

Scale: tens of thousands of studies. Must be resumable, batch-aware, and observable.

## Architecture

```
┌──────────────┐    C-FIND/C-MOVE     ┌───────────────┐
│  Source PACS  │ <─────────────────── │  Orthanc      │
│  (3rd party)  │ ──────────────────>  │  (existing)   │
└──────────────┘    DICOM protocol     └───────┬───────┘
                                               │ REST API
                                       ┌───────┴───────┐
                                       │  Migrator CLI  │
                                       │  (this tool)   │
                                       └───────┬───────┘
                                               │
                                       ┌───────┴───────┐
                                       │  SQLite DB     │
                                       │  (tracking)    │
                                       └───────────────┘
```

Key insight: Orthanc does the actual DICOM networking. The migrator just
orchestrates via REST API (pyorthanc). This avoids pynetdicom entirely.

## Plan

- [x] Step 1: Project scaffolding (config, docker, requirements)
- [x] Step 2: SQLite tracking database (study discovery + migration state)
- [x] Step 3: Discovery phase — C-FIND all studies via Orthanc modality API
- [x] Step 4: Migration phase — C-MOVE studies in batches with retry logic
- [x] Step 5: CLI interface (typer) with progress reporting
- [x] Step 6: Docker Compose for the migrator + test source PACS
- [x] Step 7: Verification — compare study counts source vs destination
- [ ] Step 8: Test with local Docker Compose setup

## Design Decisions

### Why orchestrate through Orthanc (not pynetdicom)?
- Orthanc handles DICOM association, transfer syntax negotiation, storage
- We stay within the MEDMB stack (pyorthanc only)
- Simpler code — REST calls vs raw DICOM networking
- Orthanc's built-in retry and connection pooling

### Why SQLite for tracking?
- Tens of thousands of studies need persistent state
- Resumability: if the process crashes, restart picks up where it left off
- Simple queries for progress reporting
- Single file, no external DB dependency
- Mounts as a Docker volume

### Batch strategy
- C-FIND by date range (monthly chunks) to avoid overwhelming source PACS
- C-MOVE one study at a time with configurable concurrency
- Exponential backoff on failures, mark permanently failed after N retries

## Progress Notes

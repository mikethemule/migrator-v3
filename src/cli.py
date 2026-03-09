import sys

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from src.config import settings
from src.services.discovery import discover_studies
from src.services.migrator import migrate_pending
from src.services.tracker import MigrationTracker
from src.services.verifier import verify_migration

app = typer.Typer(help="PACS-to-Orthanc Migration Tool")
console = Console()

# Configure loguru — remove default, add stderr with timestamp
logger.remove()
logger.add(sys.stderr, format="{time:HH:mm:ss} | {level:<8} | {message}")
logger.add("data/migration.log", rotation="10 MB", retention="30 days")


def _get_tracker() -> MigrationTracker:
    return MigrationTracker(db_path=settings.db_path)


@app.command()
def discover(
    skip_echo: bool = typer.Option(False, "--skip-echo", help="Skip C-ECHO connectivity check"),
):
    """C-FIND all studies on the source PACS and register them for migration."""
    tracker = _get_tracker()
    new_count = discover_studies(tracker, skip_echo=skip_echo)
    _print_status(tracker)
    logger.info(f"Discovery complete. {new_count} new studies registered.")


@app.command()
def migrate():
    """Migrate all pending studies from the source PACS into Orthanc."""
    tracker = _get_tracker()
    counts = tracker.get_counts()
    pending = counts.get("pending", 0)

    if pending == 0:
        logger.info("No pending studies. Run 'discover' first, or 'retry' to reset failed studies.")
        return

    logger.info(f"Starting migration of {pending} pending studies...")
    result = migrate_pending(tracker)
    _print_status(tracker)
    logger.info(f"Migration pass complete. Completed: {result['completed']}, Failed: {result['failed']}")


@app.command()
def run(
    skip_echo: bool = typer.Option(False, "--skip-echo", help="Skip C-ECHO connectivity check"),
):
    """Discover and migrate in one step."""
    tracker = _get_tracker()
    logger.info("Phase 1: Discovery")
    discover_studies(tracker, skip_echo=skip_echo)
    _print_status(tracker)

    logger.info("Phase 2: Migration")
    result = migrate_pending(tracker)
    _print_status(tracker)

    logger.info(f"Done. Completed: {result['completed']}, Failed: {result['failed']}")


@app.command()
def status():
    """Show current migration progress."""
    tracker = _get_tracker()
    _print_status(tracker)


@app.command()
def verify():
    """Compare tracked studies against what exists in Orthanc."""
    tracker = _get_tracker()
    result = verify_migration(tracker)

    table = Table(title="Verification Results")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    for key, value in result.items():
        style = "red" if "missing" in key and value > 0 else ""
        table.add_row(key.replace("_", " ").title(), str(value), style=style)
    console.print(table)


@app.command()
def retry():
    """Reset all failed studies back to pending and re-run migration."""
    tracker = _get_tracker()
    reset_count = tracker.reset_failed()
    logger.info(f"Reset {reset_count} failed studies to pending.")

    if reset_count > 0:
        result = migrate_pending(tracker)
        _print_status(tracker)
        logger.info(f"Retry complete. Completed: {result['completed']}, Failed: {result['failed']}")


def _print_status(tracker: MigrationTracker):
    counts = tracker.get_counts()
    table = Table(title="Migration Status")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    for status in ["pending", "in_progress", "completed", "failed", "total"]:
        style = {
            "pending": "yellow",
            "in_progress": "blue",
            "completed": "green",
            "failed": "red",
            "total": "bold",
        }.get(status, "")
        table.add_row(status.title(), str(counts.get(status, 0)), style=style)
    console.print(table)


if __name__ == "__main__":
    app()

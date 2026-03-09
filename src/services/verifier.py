from loguru import logger
from pyorthanc import find_studies

from src.orthanc_client import get_client
from src.services.tracker import MigrationTracker


def verify_migration(tracker: MigrationTracker) -> dict:
    """Compare tracked studies against what actually exists in Orthanc.

    Returns a summary of matched, missing, and unexpected studies.
    """
    client = get_client()
    counts = tracker.get_counts()

    # Get all study UIDs from Orthanc
    logger.info("Fetching all studies from destination Orthanc...")
    studies = find_studies(client=client, query={"PatientID": "*"})
    orthanc_uids = set()
    for study in studies:
        uid = study.uid
        if uid:
            orthanc_uids.add(uid)

    # Get completed and all UIDs from tracker
    with tracker._conn() as conn:
        rows = conn.execute(
            "SELECT study_instance_uid FROM studies WHERE status = 'completed'"
        ).fetchall()
        tracked_completed = {row["study_instance_uid"] for row in rows}

        rows_all = conn.execute(
            "SELECT study_instance_uid FROM studies"
        ).fetchall()
        tracked_all = {row["study_instance_uid"] for row in rows_all}

    matched = tracked_completed & orthanc_uids
    missing = tracked_completed - orthanc_uids
    extra_in_orthanc = orthanc_uids - tracked_all

    result = {
        "tracker_total": counts.get("total", 0),
        "tracker_completed": counts.get("completed", 0),
        "tracker_failed": counts.get("failed", 0),
        "tracker_pending": counts.get("pending", 0),
        "orthanc_study_count": len(orthanc_uids),
        "verified_present": len(matched),
        "marked_complete_but_missing": len(missing),
        "in_orthanc_not_tracked": len(extra_in_orthanc),
    }

    logger.info("Verification complete:")
    logger.info(f"  Tracked total:    {result['tracker_total']}")
    logger.info(f"  Tracked done:     {result['tracker_completed']}")
    logger.info(f"  Tracked failed:   {result['tracker_failed']}")
    logger.info(f"  Tracked pending:  {result['tracker_pending']}")
    logger.info(f"  In Orthanc:       {result['orthanc_study_count']}")
    logger.info(f"  Verified match:   {result['verified_present']}")
    if missing:
        logger.warning(f"  Completed but missing in Orthanc: {len(missing)}")
    if extra_in_orthanc:
        logger.info(f"  In Orthanc but not tracked: {len(extra_in_orthanc)} (pre-existing studies)")

    return result

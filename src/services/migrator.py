import time

from loguru import logger
from pyorthanc import Modality

from src.config import settings
from src.orthanc_client import get_client
from src.services.tracker import MigrationTracker, StudyStatus


def migrate_pending(tracker: MigrationTracker) -> dict[str, int]:
    """Migrate all pending studies from the source PACS into Orthanc.

    Processes studies in batches. Each study is C-MOVEd individually
    with exponential backoff on failure.

    Returns a summary dict with completed/failed counts.
    """
    client = get_client()
    modality = Modality(client, settings.source_modality)

    completed = 0
    failed = 0

    while True:
        batch = tracker.get_pending(limit=settings.batch_size)
        if not batch:
            break

        for study in batch:
            uid = study["study_instance_uid"]
            success = _migrate_single_study(client, modality, tracker, uid)
            if success:
                completed += 1
            else:
                failed += 1

        counts = tracker.get_counts()
        pending = counts.get(StudyStatus.PENDING, 0)
        logger.info(
            f"Batch complete. Completed: {completed}, Failed: {failed}, Remaining: {pending}"
        )

    return {"completed": completed, "failed": failed}


def _migrate_single_study(
    client,
    modality: Modality,
    tracker: MigrationTracker,
    study_uid: str,
) -> bool:
    """Attempt to C-MOVE a single study with retries."""
    tracker.mark_in_progress(study_uid)

    for attempt in range(1, settings.max_retries + 1):
        try:
            logger.info(f"C-MOVE study {study_uid} (attempt {attempt}/{settings.max_retries})")

            # Query for this specific study to get a query ID for the move
            query_response = modality.query(
                data={
                    "Level": "Study",
                    "Query": {"StudyInstanceUID": study_uid},
                }
            )
            query_id = query_response["ID"]

            # Verify the query returned at least one answer
            answers = client.get_queries_id_answers(id_=query_id)
            if not answers:
                raise RuntimeError(f"Study {study_uid} not found on source PACS")

            # C-MOVE the study into this Orthanc instance
            client.post_queries_id_answers_index_retrieve(
                id_=query_id,
                index="0",
                json=settings.dest_aet,
            )

            # Verify the study arrived
            if _verify_study_arrived(client, study_uid):
                tracker.mark_completed(study_uid)
                logger.info(f"Successfully migrated study {study_uid}")
                return True
            else:
                raise RuntimeError(f"Study {study_uid} not found in Orthanc after C-MOVE")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.warning(f"Attempt {attempt} failed for {study_uid}: {error_msg}")

            if attempt < settings.max_retries:
                backoff = min(
                    settings.retry_backoff_base ** attempt,
                    settings.retry_backoff_max,
                )
                logger.info(f"Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                tracker.mark_failed(study_uid, error_msg)
                logger.error(f"Study {study_uid} failed after {settings.max_retries} attempts")
                return False

    return False


def _verify_study_arrived(client, study_uid: str) -> bool:
    """Check that a study exists in the destination Orthanc by StudyInstanceUID."""
    try:
        result = client.post_tools_find(json={
            "Level": "Study",
            "Query": {"StudyInstanceUID": study_uid},
        })
        return len(result) > 0
    except Exception:
        return False

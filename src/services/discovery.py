from loguru import logger
from pyorthanc import Modality

from src.config import settings
from src.orthanc_client import get_client
from src.services.tracker import MigrationTracker


def discover_studies(tracker: MigrationTracker, skip_echo: bool = False) -> int:
    """C-FIND all studies on the source PACS and register them in the tracker.

    Returns the number of newly discovered studies.
    """
    client = get_client()
    modality = Modality(client, settings.source_modality)

    # Verify connectivity first (optional — some PACS restrict C-ECHO)
    if skip_echo:
        logger.info("Skipping C-ECHO check.")
    else:
        logger.info(f"Testing connection to modality '{settings.source_modality}'...")
        if not modality.echo():
            raise ConnectionError(
                f"C-ECHO failed for modality '{settings.source_modality}'. "
                "Check Orthanc modality configuration, or use --skip-echo."
            )
        logger.info("C-ECHO successful.")

    # Build the C-FIND query
    query: dict = {
        "Level": "Study",
        "Query": {
            "StudyInstanceUID": "",
            "PatientID": "",
            "StudyDate": _build_date_range(),
            "StudyDescription": "",
            "AccessionNumber": "",
            "ModalitiesInStudy": "",
        },
    }

    logger.info(f"Running C-FIND on '{settings.source_modality}'...")
    query_response = modality.query(data=query)
    query_id = query_response["ID"]

    # Retrieve the answers
    answers = _get_query_answers(client, query_id)
    logger.info(f"C-FIND returned {len(answers)} studies.")

    new_count = 0
    for answer in answers:
        study_uid = answer.get("0020,000d", {}).get("Value", "")
        if not study_uid:
            continue

        if tracker.is_study_known(study_uid):
            continue

        tracker.add_study(
            study_instance_uid=study_uid,
            patient_id=answer.get("0010,0020", {}).get("Value", ""),
            study_date=answer.get("0008,0020", {}).get("Value", ""),
            study_description=answer.get("0008,1030", {}).get("Value", ""),
            accession_number=answer.get("0008,0050", {}).get("Value", ""),
            modalities=answer.get("0008,0061", {}).get("Value", ""),
            query_id=query_id,
        )
        new_count += 1

    logger.info(f"Discovered {new_count} new studies ({len(answers) - new_count} already known).")
    return new_count


def _get_query_answers(client, query_id: str) -> list[dict]:
    """Retrieve all answers from a completed C-FIND query."""
    # Get the list of answer indices first
    answer_indices = client.get_queries_id_answers(id_=query_id)
    answers = []
    for index in answer_indices:
        answer = client.get_queries_id_answers_index_content(
            id_=query_id, index=str(index)
        )
        answers.append(answer)
    return answers


def _build_date_range() -> str:
    """Build a DICOM date range string from config."""
    date_from = settings.date_from
    date_to = settings.date_to

    if date_from and date_to:
        return f"{date_from}-{date_to}"
    elif date_from:
        return f"{date_from}-"
    elif date_to:
        return f"-{date_to}"
    return ""

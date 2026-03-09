from datetime import date, datetime, timedelta

from loguru import logger
from pyorthanc import Modality

from src.config import settings
from src.orthanc_client import get_client
from src.services.tracker import MigrationTracker

RESULT_LIMIT = 100


def discover_studies(tracker: MigrationTracker, skip_echo: bool = False) -> int:
    """C-FIND all studies on the source PACS and register them in the tracker.

    Paginates by monthly date ranges to stay within the Orthanc
    LimitFindResults cap (typically 100). If a single month returns
    exactly RESULT_LIMIT results, it subdivides into daily queries
    to ensure nothing is missed.

    Returns the number of newly discovered studies.
    """
    client = get_client()
    modality = Modality(client, settings.source_modality)

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

    # Determine the date range to scan
    date_from = _parse_date(settings.date_from) if settings.date_from else date(2000, 1, 1)
    date_to = _parse_date(settings.date_to) if settings.date_to else date.today()

    # Generate monthly chunks
    months = _monthly_ranges(date_from, date_to)
    logger.info(
        f"Scanning {len(months)} monthly chunks from {date_from} to {date_to}..."
    )

    total_new = 0
    total_found = 0

    for i, (chunk_start, chunk_end) in enumerate(months, 1):
        date_range = f"{chunk_start.strftime('%Y%m%d')}-{chunk_end.strftime('%Y%m%d')}"
        answers = _cfind(client, modality, date_range)
        found = len(answers)
        total_found += found

        if found >= RESULT_LIMIT:
            # This month hit the cap — drill down by day to catch everything
            logger.warning(
                f"  Month {chunk_start.strftime('%Y-%m')} returned {found} results "
                f"(at limit). Splitting into daily queries..."
            )
            answers = _drill_down_daily(client, modality, chunk_start, chunk_end)
            total_found += len(answers) - found  # adjust for the re-count
            found = len(answers)

        new_count = _register_answers(tracker, answers)
        total_new += new_count

        logger.info(
            f"  [{i}/{len(months)}] {chunk_start.strftime('%Y-%m')}: "
            f"{found} found, {new_count} new"
        )

    logger.info(
        f"Discovery complete. {total_found} total studies found, "
        f"{total_new} new, {total_found - total_new} already known."
    )
    return total_new


def _cfind(client, modality: Modality, date_range: str) -> list[dict]:
    """Run a single C-FIND query for a date range and return the answers."""
    query = {
        "Level": "Study",
        "Query": {
            "StudyInstanceUID": "",
            "PatientID": "",
            "StudyDate": date_range,
            "StudyDescription": "",
            "AccessionNumber": "",
            "ModalitiesInStudy": "",
        },
    }
    query_response = modality.query(data=query)
    query_id = query_response["ID"]
    return _get_query_answers(client, query_id)


def _drill_down_daily(
    client, modality: Modality, month_start: date, month_end: date
) -> list[dict]:
    """Query day-by-day within a month that hit the result limit."""
    all_answers = []
    seen_uids = set()
    current = month_start

    while current <= month_end:
        day_str = current.strftime("%Y%m%d")
        answers = _cfind(client, modality, f"{day_str}-{day_str}")

        for answer in answers:
            uid = answer.get("0020,000d", {}).get("Value", "")
            if uid and uid not in seen_uids:
                seen_uids.add(uid)
                all_answers.append(answer)

        if len(answers) >= RESULT_LIMIT:
            logger.warning(
                f"    Day {day_str} also hit limit ({len(answers)} results). "
                f"Some studies on this day may be missed."
            )

        current += timedelta(days=1)

    return all_answers


def _register_answers(tracker: MigrationTracker, answers: list[dict]) -> int:
    """Register C-FIND answers in the tracker. Returns count of new studies."""
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
        )
        new_count += 1
    return new_count


def _get_query_answers(client, query_id: str) -> list[dict]:
    """Retrieve all answers from a completed C-FIND query."""
    answer_indices = client.get_queries_id_answers(id_=query_id)
    answers = []
    for index in answer_indices:
        answer = client.get_queries_id_answers_index_content(
            id_=query_id, index=str(index)
        )
        answers.append(answer)
    return answers


def _monthly_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """Generate (first_of_month, last_of_month) tuples covering start..end."""
    ranges = []
    current = start.replace(day=1)
    while current <= end:
        month_end = (current + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        chunk_end = min(month_end, end)
        chunk_start = max(current, start)
        ranges.append((chunk_start, chunk_end))
        current = month_end + timedelta(days=1)
    return ranges


def _parse_date(s: str) -> date:
    """Parse a YYYYMMDD string into a date object."""
    return datetime.strptime(s, "%Y%m%d").date()

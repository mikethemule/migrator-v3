from contextlib import contextmanager

import httpx
from pyorthanc import Orthanc

from src.config import settings


def get_client() -> Orthanc:
    kwargs = {
        "url": settings.orthanc_url,
        "timeout": settings.query_timeout,
    }
    if settings.orthanc_username:
        kwargs["username"] = settings.orthanc_username
        kwargs["password"] = settings.orthanc_password
    return Orthanc(**kwargs)


@contextmanager
def move_timeout(client: Orthanc):
    """Temporarily apply the longer move_timeout for C-MOVE operations."""
    original = client.timeout
    client.timeout = httpx.Timeout(settings.move_timeout)
    try:
        yield client
    finally:
        client.timeout = original

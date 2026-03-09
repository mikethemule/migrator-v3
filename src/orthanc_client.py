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

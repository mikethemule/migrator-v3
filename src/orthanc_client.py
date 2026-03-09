from pyorthanc import Orthanc

from src.config import settings


def get_client() -> Orthanc:
    return Orthanc(
        url=settings.orthanc_url,
        username=settings.orthanc_username,
        password=settings.orthanc_password,
    )

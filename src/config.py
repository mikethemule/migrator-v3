from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Source PACS — configured as a modality in Orthanc
    source_modality: str = "SOURCE_PACS"

    # Orthanc (destination)
    orthanc_url: str = "http://localhost:8042"
    orthanc_username: str = "orthanc"
    orthanc_password: str = "orthanc"
    dest_aet: str = "DEST_ORTHANC"

    # Migration behaviour
    batch_size: int = 10
    max_retries: int = 3
    retry_backoff_base: int = 2
    retry_backoff_max: int = 60
    query_timeout: float = 600.0

    # Tracking database
    db_path: str = "data/migration.db"

    # Date range for discovery (YYYYMMDD). Empty = all.
    date_from: str = ""
    date_to: str = ""

    class Config:
        env_file = ".env"


settings = Settings()

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
        self.vision_mock = os.getenv("VISION_MOCK", "0") == "1"
        self.token_ttl_days = int(os.getenv("TOKEN_TTL_DAYS", "30"))
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024
        self.max_photos_per_wine = 4

    @property
    def db_path(self) -> Path:
        return self.data_dir / "wineremember.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


settings = Settings()

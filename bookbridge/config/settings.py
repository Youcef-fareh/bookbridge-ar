"""Application settings and path configurations."""

import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AppSettings(BaseModel):
    app_name: str = "BookBridge"
    version: str = "1.0.0"
    data_dir: Path = Field(default_factory=lambda: Path(os.getenv("BOOKBRIDGE_DATA_DIR", Path.home() / ".bookbridge")))
    db_filename: str = "bookbridge.db"
    log_level: str = "INFO"
    default_source_lang: str = "en"
    default_target_lang: str = "ar"
    default_gemini_model: str = "gemini-2.5-flash"
    default_groq_model: str = "llama-3.3-70b-versatile"
    default_orcarouter_model: str = "qwen/qwen3.8-27b-free"
    default_tokenrouter_model: str = "deepseek/deepseek-v4-pro-0813-free"
    max_segment_chars: int = 1200
    context_window_blocks: int = 2
    max_concurrent_requests: int = 3
    request_timeout_seconds: float = 35.0
    max_validation_retries: int = 2

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_directories(self) -> None:
        """Create all required directories with detailed error logging."""
        dirs_to_create = [
            (self.data_dir, "main data directory"),
            (self.cache_dir, "cache directory"),
            (self.exports_dir, "exports directory"),
            (self.logs_dir, "logs directory"),
            (self.data_dir / ".vault", "secure vault directory"),
        ]
        
        for dir_path, description in dirs_to_create:
            try:
                dir_path.mkdir(parents=True, exist_ok=True, mode=0o755)
                if not dir_path.exists():
                    logger.error(f"Created {description} ({dir_path}) but it doesn't exist!")
                else:
                    logger.debug(f"✓ {description}: {dir_path}")
            except PermissionError as e:
                logger.error(f"Permission denied creating {description} at {dir_path}: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Failed to create {description} at {dir_path}: {str(e)}")
                raise


# Global settings singleton
settings = AppSettings()

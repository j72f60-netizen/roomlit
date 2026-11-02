"""Runtime configuration, all from environment variables (see README)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _model_dir() -> str:
    """MODEL_DIR, else ./models next to the app when it is writable, else a temp folder."""
    if os.environ.get("MODEL_DIR"):
        return os.environ["MODEL_DIR"]
    proj = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
    if os.path.isdir(proj) or os.access(os.path.dirname(proj), os.W_OK):
        return proj
    return os.path.join(os.environ.get("DATA_DIR", "/tmp/roomlit"), "models")


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: os.environ.get("APP_ENV", "production"))
    username: str = field(default_factory=lambda: os.environ.get("APP_USERNAME", "admin"))
    password: str = field(default_factory=lambda: os.environ.get("APP_PASSWORD", ""))
    secret_key: str = field(default_factory=lambda: os.environ.get("SESSION_SECRET") or secrets.token_urlsafe(48))
    session_hours: int = field(default_factory=lambda: _int("SESSION_HOURS", 12))

    data_dir: str = field(default_factory=lambda: os.environ.get("DATA_DIR", "/tmp/roomlit"))

    # --- retention (minutes).  Photos never outlive these.
    job_ttl_minutes: int = field(default_factory=lambda: _int("JOB_TTL_MINUTES", 120))
    downloaded_ttl_minutes: int = field(default_factory=lambda: _int("DOWNLOADED_TTL_MINUTES", 30))
    failed_ttl_minutes: int = field(default_factory=lambda: _int("FAILED_TTL_MINUTES", 10))

    # --- limits
    max_file_mb: int = field(default_factory=lambda: _int("MAX_FILE_MB", 80))
    max_zip_mb: int = field(default_factory=lambda: _int("MAX_ZIP_MB", 1500))
    max_job_mb: int = field(default_factory=lambda: _int("MAX_JOB_MB", 2000))
    max_files_per_job: int = field(default_factory=lambda: _int("MAX_FILES_PER_JOB", 400))
    max_jobs: int = field(default_factory=lambda: _int("MAX_JOBS", 6))
    max_megapixels: int = field(default_factory=lambda: _int("MAX_MEGAPIXELS", 40))
    min_free_disk_mb: int = field(default_factory=lambda: _int("MIN_FREE_DISK_MB", 300))

    # --- worker
    cv_threads: int = field(default_factory=lambda: _int("CV_THREADS", 1))
    worker_recycle: int = field(default_factory=lambda: _int("WORKER_RECYCLE", 12))
    task_timeout_s: int = field(default_factory=lambda: _int("TASK_TIMEOUT_S", 420))
    organize_timeout_s: int = field(default_factory=lambda: _int("ORGANIZE_TIMEOUT_S", 900))
    model_dir: str = field(default_factory=lambda: _model_dir())

    @property
    def dev(self) -> bool:
        return self.env == "dev"

    @property
    def max_pixels(self) -> int:
        return self.max_megapixels * 1_000_000

    @property
    def jobs_dir(self) -> str:
        return os.path.join(self.data_dir, "jobs")


def load() -> Settings:
    s = Settings()
    if not s.password:
        if s.dev:
            return Settings(password="dev-password")
        raise RuntimeError("APP_PASSWORD must be set")
    return s

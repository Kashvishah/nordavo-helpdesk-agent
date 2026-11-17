"""Load required settings from environment variables and a local .env file."""

import os
from pathlib import Path


REQUIRED_SETTINGS = (
    "HELPDESK_API_URL",
    "HELPDESK_API_KEY",
    "CANDIDATE_EMAIL",
    "OPENAI_API_KEY",
)


def _load_local_env() -> None:
    """Load simple KEY=VALUE entries without replacing existing environment values."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name:
            os.environ.setdefault(name, value)


def load_config() -> dict[str, str]:
    _load_local_env()
    missing = [name for name in REQUIRED_SETTINGS if not os.environ.get(name)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Missing required environment setting(s): {names}. "
            "Set them in your local .env file or environment."
        )
    return {name: os.environ[name] for name in REQUIRED_SETTINGS}

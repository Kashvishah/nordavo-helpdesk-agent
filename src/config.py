"""Load required settings from environment variables and a local .env file."""

import os
import math
from pathlib import Path


REQUIRED_SETTINGS = (
    "HELPDESK_API_URL",
    "HELPDESK_API_KEY",
    "CANDIDATE_EMAIL",
    "OPENAI_API_KEY",
)
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_MAX_RUN_COST_EUR = "0.5"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_local_env() -> None:
    """Load simple KEY=VALUE entries without replacing existing environment values."""
    env_path = PROJECT_ROOT / ".env"
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
    config = {name: os.environ[name] for name in REQUIRED_SETTINGS}
    config["OPENAI_MODEL"] = os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
    max_cost = os.environ.get("MAX_RUN_COST_EUR", "").strip() or DEFAULT_MAX_RUN_COST_EUR
    try:
        parsed_cost = float(max_cost)
        if not math.isfinite(parsed_cost) or parsed_cost < 0:
            raise ValueError
    except ValueError:
        raise RuntimeError("MAX_RUN_COST_EUR must be a non-negative number.") from None
    config["MAX_RUN_COST_EUR"] = max_cost
    return config

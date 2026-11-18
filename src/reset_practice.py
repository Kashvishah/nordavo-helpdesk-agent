"""Reset practice tickets and rotate local run state and logs."""

import time
import urllib.request
from pathlib import Path

from .config import PROJECT_ROOT, load_config
from .http_json import request_json


ROOT = PROJECT_ROOT
LOG_PATH = ROOT / "logs" / "run.jsonl"
OLD_LOG_PATH = ROOT / "logs" / "run_old.jsonl"
STATE_PATH = ROOT / "local_state" / "handled_ticket_ids.json"
STATE_TEMP_PATH = STATE_PATH.with_suffix(".tmp")


def _archive_path_if_needed() -> tuple[Path, Path | None]:
    """Move an existing run_old aside so it is never overwritten."""
    if not OLD_LOG_PATH.exists():
        return OLD_LOG_PATH, None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    index = 1
    while True:
        suffix = f"_{timestamp}_{index}"
        archive = OLD_LOG_PATH.with_name(f"run_old{suffix}.jsonl")
        if not archive.exists():
            OLD_LOG_PATH.replace(archive)
            return OLD_LOG_PATH, archive
        index += 1


def main() -> None:
    config = load_config()
    reset_url = f"{config['HELPDESK_API_URL'].rstrip('/')}/practice/reset"
    request = urllib.request.Request(
        reset_url,
        data=b"",
        headers={
            "Authorization": f"Bearer {config['HELPDESK_API_KEY']}",
            "X-Candidate-Email": config["CANDIDATE_EMAIL"],
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    # Do not touch local files unless the helpdesk reset succeeds.
    request_json(request, service="Helpdesk POST /practice/reset")
    print("Practice tickets were reset.")

    logs_dir = LOG_PATH.parent
    logs_dir.mkdir(parents=True, exist_ok=True)
    archive_path, preserved_old_log = _archive_path_if_needed()
    if LOG_PATH.exists():
        LOG_PATH.replace(archive_path)
        print(f"Archived the previous run log as logs/{archive_path.name}.")
    else:
        print("No previous run.jsonl was present to archive.")
    if preserved_old_log is not None:
        print(f"Preserved the prior run_old log as logs/{preserved_old_log.name}.")

    cleared_state = False
    for state_file in (STATE_PATH, STATE_TEMP_PATH):
        if state_file.exists():
            state_file.unlink()
            cleared_state = True
    if cleared_state:
        print("Cleared the local handled-ticket state.")
    else:
        print("No local handled-ticket state file was present.")

    LOG_PATH.touch()
    print("Started a fresh logs/run.jsonl.")


if __name__ == "__main__":
    main()

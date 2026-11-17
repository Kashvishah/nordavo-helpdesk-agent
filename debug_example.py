"""Run the debug triage path on E01 from the saved labelled-example results."""

import json
from pathlib import Path

from config import load_config
from triage import _redact_secrets, triage_ticket


LABEL_FILE = Path(__file__).resolve().parent / "logs" / "eval_before.json"
EXAMPLE_ID = "E01"


def main() -> None:
    config = load_config()
    saved = json.loads(LABEL_FILE.read_text(encoding="utf-8"))
    example = next(
        (row for row in saved.get("results", []) if row.get("ticket_id") == EXAMPLE_ID),
        None,
    )
    if example is None or not example.get("ticket_preview"):
        raise RuntimeError(f"{EXAMPLE_ID} is not available in {LABEL_FILE.name}.")

    # The saved label file has the full short E01 text as a preview, but not its
    # separate subject/body fields. Keep the text and omit all gold-label data.
    ticket = {"id": EXAMPLE_ID, "body": example["ticket_preview"]}
    print(f"Debugging {EXAMPLE_ID} from {LABEL_FILE.name}.")
    try:
        result = triage_ticket(ticket, debug=True)
    except Exception as error:
        message = _redact_secrets(str(error), config)
        print(f"Debug run failed: {type(error).__name__}: {message}")
        return
    print("=== Post-processed triage result ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

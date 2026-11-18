"""Check that known instruction-injection and legal-threat tickets are classified correctly."""

from src.config import load_config
from src.triage import triage_ticket
from scripts.try_one import fetch_ticket


def main() -> None:
    config = load_config()
    expected = {"T007": True, "T028": False}

    for ticket_id, expected_suspicious in expected.items():
        try:
            ticket = fetch_ticket(config, ticket_id)
            result = triage_ticket(ticket)
            passed = result["suspicious"] is expected_suspicious
        except Exception:
            passed = False
        print(f"{ticket_id}: {'PASS' if passed else 'FAIL'}")


if __name__ == "__main__":
    main()

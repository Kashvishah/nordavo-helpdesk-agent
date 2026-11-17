"""Dry-run triage for all open tickets; this script never posts decisions."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import load_config
from fetch_tickets import fetch_open_tickets
from triage import triage_ticket


LOG_PATH = Path(__file__).resolve().parent / "logs" / "run.jsonl"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error(error: Exception, config: dict[str, str]) -> str:
    message = str(error)
    for value in (
        f"Bearer {config['HELPDESK_API_KEY']}",
        config["HELPDESK_API_KEY"],
        config["OPENAI_API_KEY"],
        config["CANDIDATE_EMAIL"],
    ):
        if value:
            message = message.replace(value, "[redacted]")
    return f"{type(error).__name__}: {message}"


def _append_record(record: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _print_suspicious_table(rows: list[tuple[str, str, str]]) -> None:
    print("\nSuspicious tickets:")
    headers = ("Ticket ID", "Ticket text (first 60 characters)", "Reason")
    if not rows:
        print("(none)")
        return

    safe_rows = [
        tuple(" ".join(value.replace("|", "/").split()) for value in row)
        for row in rows
    ]
    widths = tuple(
        max(len(header), *(len(row[index]) for row in safe_rows))
        for index, header in enumerate(headers)
    )

    def format_row(row: tuple[str, str, str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in safe_rows:
        print(format_row(row))


def main() -> None:
    config = load_config()
    counts = {"answer": 0, "escalate": 0, "suspicious": 0, "errors": 0}
    suspicious_rows: list[tuple[str, str, str]] = []

    try:
        tickets = fetch_open_tickets(config)
    except Exception as error:
        counts["errors"] += 1
        _append_record(
            {
                "ticket_id": None,
                "decision": None,
                "reason": None,
                "suspicious": None,
                "timestamp": _timestamp(),
                "error": _safe_error(error, config),
            }
        )
        print("Dry run summary: answer 0, escalate 0, suspicious 0, errors 1")
        _print_suspicious_table(suspicious_rows)
        return

    for ticket in tickets:
        ticket_id = ticket.get("id")
        try:
            result = triage_ticket(ticket)
            decision = result["decision"]
            suspicious = result["suspicious"]
            if decision in counts:
                counts[decision] += 1
            if suspicious:
                counts["suspicious"] += 1
                ticket_text = " ".join(str(ticket.get("body", "")).split())[:60]
                suspicious_rows.append(
                    (str(ticket_id or ""), ticket_text, str(result["reason"]))
                )
            record = {
                "ticket_id": ticket_id,
                "decision": decision,
                "reason": result["reason"],
                "suspicious": suspicious,
                "timestamp": _timestamp(),
            }
        except Exception as error:
            counts["errors"] += 1
            record = {
                "ticket_id": ticket_id,
                "decision": None,
                "reason": None,
                "suspicious": None,
                "timestamp": _timestamp(),
                "error": _safe_error(error, config),
            }
        _append_record(record)

    print(
        "Dry run summary: "
        f"answer {counts['answer']}, escalate {counts['escalate']}, "
        f"suspicious {counts['suspicious']}, errors {counts['errors']}"
    )
    _print_suspicious_table(suspicious_rows)


if __name__ == "__main__":
    main()

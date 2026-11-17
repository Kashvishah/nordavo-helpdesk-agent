"""Dry-run triage for all open tickets; this script never posts decisions."""

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import load_config
from fetch_tickets import fetch_open_tickets
from http_json import HTTPCallError, request_json
from triage import RunCostLimitExceeded, reset_run_cost_estimate, triage_ticket
from try_one import fetch_ticket


LOG_PATH = Path(__file__).resolve().parent / "logs" / "run.jsonl"
STATE_PATH = Path(__file__).resolve().parent / "local_state" / "handled_ticket_ids.json"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_secrets(message: str, config: dict[str, str]) -> str:
    for value in (
        f"Bearer {config['HELPDESK_API_KEY']}",
        config["HELPDESK_API_KEY"],
        config["OPENAI_API_KEY"],
        config["CANDIDATE_EMAIL"],
    ):
        if value:
            message = message.replace(value, "[redacted]")
    return message


def _safe_error(error: Exception, config: dict[str, str]) -> str:
    return f"{type(error).__name__}: {_redact_secrets(str(error), config)}"


def _append_record(record: dict[str, Any], config: dict[str, str]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    safe_record = {
        key: _redact_secrets(value, config) if isinstance(value, str) else value
        for key, value in record.items()
    }
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(safe_record, ensure_ascii=False) + "\n")


def _load_handled_ids() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"Invalid local state file: {STATE_PATH}")
    return set(value)


def _save_handled_ids(ticket_ids: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = STATE_PATH.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(sorted(ticket_ids), indent=2) + "\n", encoding="utf-8"
    )
    temporary_path.replace(STATE_PATH)


def _skip_record(ticket_id: Any, reason: str, mode: str) -> dict[str, Any]:
    return {
        "ticket_id": ticket_id,
        "status": "skipped",
        "mode": mode,
        "decision": None,
        "reason": reason,
        "suspicious": None,
        "timestamp": _timestamp(),
    }


def _send_live_action(
    config: dict[str, str], ticket_id: str, result: dict[str, Any]
) -> str:
    decision = result["decision"]
    action_for_decision = {
        "answer": "reply",
        "escalate": "handoff",
        "ignore": "close",
    }
    action = action_for_decision[decision]
    payload: dict[str, Any] = {
        "language": result["language"],
        "category": result["category"],
        "priority": result["priority"],
        "reason": result["reason"],
    }
    if decision == "answer":
        payload["draft_reply"] = result["reply"]
    elif decision == "escalate":
        payload["handoff_note"] = result["reason"]

    encoded_id = urllib.parse.quote(ticket_id, safe="")
    url = (
        f"{config['HELPDESK_API_URL'].rstrip('/')}/tickets/"
        f"{encoded_id}/{action}"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['HELPDESK_API_KEY']}",
            "X-Candidate-Email": config["CANDIDATE_EMAIL"],
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    request_json(request, service=f"Helpdesk POST /tickets/{action}")
    return action


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
    parser = argparse.ArgumentParser(description="Dry-run triage of open tickets.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Process tickets already listed in local state.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Send the decisions to the helpdesk; default is a dry run.",
    )
    parser.add_argument(
        "--only",
        metavar="TICKET_ID",
        help="Process only this ticket ID.",
    )
    args = parser.parse_args()

    config = load_config()
    reset_run_cost_estimate()
    counts = {
        "answer": 0,
        "escalate": 0,
        "suspicious": 0,
        "errors": 0,
        "skipped": 0,
        "fallback": 0,
    }
    suspicious_rows: list[tuple[str, str, str]] = []
    try:
        handled_ids = _load_handled_ids()
    except Exception as error:
        print(f"Could not read local ticket state: {_safe_error(error, config)}")
        return

    if args.only and not args.force and args.only in handled_ids:
        counts["skipped"] += 1
        _append_record(
            _skip_record(
                args.only,
                "Already processed in an earlier run.",
                "live" if args.live else "dry-run",
            ),
            config,
        )
        mode = "Live" if args.live else "Dry run"
        print(f"{mode} summary: answer 0, escalate 0, suspicious 0, errors 0, skipped 1")
        return

    try:
        if args.only:
            tickets = [fetch_ticket(config, args.only)]
        else:
            tickets = fetch_open_tickets(config)
    except Exception as error:
        counts["errors"] += 1
        _append_record(
            {
                "ticket_id": args.only,
                "status": "error",
                "mode": "live" if args.live else "dry-run",
                "decision": None,
                "reason": None,
                "suspicious": None,
                "timestamp": _timestamp(),
                "error": _safe_error(error, config),
            },
            config,
        )
        print(
            f"Run summary: answer 0, escalate 0, suspicious 0, "
            f"errors {counts['errors']}, skipped 0"
        )
        return

    for index, ticket in enumerate(tickets):
        ticket_id = ticket.get("id")
        state_id = str(ticket_id) if ticket_id is not None else None
        if not args.force and state_id in handled_ids:
            counts["skipped"] += 1
            _append_record(
                _skip_record(
                    ticket_id,
                    "Already processed in an earlier run.",
                    "live" if args.live else "dry-run",
                ),
                config,
            )
            continue

        result = None
        triage_status = None
        try:
            result = triage_ticket(ticket)
            triage_status = getattr(result, "status", "processed")
            decision = result["decision"]
            suspicious = result["suspicious"]
            if triage_status == "fallback":
                counts["fallback"] += 1
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
                "status": triage_status,
                "mode": "live" if args.live else "dry-run",
                "decision": decision,
                "reason": result["reason"],
                "suspicious": suspicious,
                "timestamp": _timestamp(),
            }
            if args.live:
                action = _send_live_action(config, str(ticket_id), result)
                record["action"] = action
                record["action_result"] = "sent"
        except HTTPCallError as error:
            counts["errors"] += 1
            was_already_handled = error.status_code == 409
            record = {
                "ticket_id": ticket_id,
                "status": (
                    "fallback"
                    if triage_status == "fallback"
                    else "already_handled" if was_already_handled else "error"
                ),
                "mode": "live" if args.live else "dry-run",
                "decision": result.get("decision") if result is not None else None,
                "reason": result.get("reason") if result is not None else None,
                "suspicious": result.get("suspicious") if result is not None else None,
                "timestamp": _timestamp(),
                "error": _safe_error(error, config),
            }
            if args.live and result is not None:
                record["action"] = {
                    "answer": "reply",
                    "escalate": "handoff",
                    "ignore": "close",
                }.get(result["decision"])
                record["action_result"] = (
                    "already handled by helpdesk" if was_already_handled else "failed"
                )
            if was_already_handled and state_id is not None:
                record["action_result"] = "already handled by helpdesk"
        except RunCostLimitExceeded as error:
            counts["errors"] += 1
            record = {
                "ticket_id": ticket_id,
                "status": "error",
                "mode": "live" if args.live else "dry-run",
                "decision": None,
                "reason": None,
                "suspicious": None,
                "timestamp": _timestamp(),
                "error": _safe_error(error, config),
            }
            _append_record(record, config)
            for remaining_ticket in tickets[index + 1 :]:
                counts["skipped"] += 1
                remaining_id = remaining_ticket.get("id")
                if not args.force and str(remaining_id) in handled_ids:
                    skip_reason = "Already processed in an earlier run."
                else:
                    skip_reason = "Run stopped because the OpenAI cost cap was reached."
                _append_record(
                    _skip_record(
                        remaining_id,
                        skip_reason,
                        "live" if args.live else "dry-run",
                    ),
                    config,
                )
            break
        except Exception as error:
            counts["errors"] += 1
            record = {
                "ticket_id": ticket_id,
                "status": "fallback" if triage_status == "fallback" else "error",
                "mode": "live" if args.live else "dry-run",
                "decision": result.get("decision") if result is not None else None,
                "reason": result.get("reason") if result is not None else None,
                "suspicious": result.get("suspicious") if result is not None else None,
                "timestamp": _timestamp(),
                "error": _safe_error(error, config),
            }
            if args.live and result is not None:
                record["action_result"] = "failed"
        _append_record(record, config)
        completed_fallback = record["status"] == "fallback" and (
            not args.live
            or record.get("action_result") in {"sent", "already handled by helpdesk"}
        )
        if (
            record["status"] in {"processed", "already_handled"} or completed_fallback
        ) and state_id is not None:
            handled_ids.add(state_id)
            _save_handled_ids(handled_ids)

    print(
        f"{'Live' if args.live else 'Dry run'} summary: "
        f"answer {counts['answer']}, escalate {counts['escalate']}, "
        f"suspicious {counts['suspicious']}, errors {counts['errors']}, "
        f"skipped {counts['skipped']}, fallback {counts['fallback']}"
    )
    _print_suspicious_table(suspicious_rows)


if __name__ == "__main__":
    main()

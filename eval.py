"""Compare triage decisions with the labelled examples (read-only helpdesk access)."""

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import load_config
from http_json import get_json
from triage import triage_ticket


OUTPUT_PATH = Path(__file__).resolve().parent / "logs" / "eval_after.json"
ACTION_TO_DECISION = {
    "reply": "answer",
    "handoff": "escalate",
    "close": "ignore",
    "answer": "answer",
    "escalate": "escalate",
    "ignore": "ignore",
}


def fetch_examples(config: dict[str, str]) -> list[dict[str, Any]]:
    """Read the labelled examples using GET /examples; this does not change tickets."""
    url = f"{config['HELPDESK_API_URL'].rstrip('/')}/examples"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {config['HELPDESK_API_KEY']}",
            "X-Candidate-Email": config["CANDIDATE_EMAIL"],
            "Accept": "application/json",
        },
    )
    payload = get_json(request, service="Helpdesk GET /examples")

    if isinstance(payload, list):
        examples = payload
    elif isinstance(payload, dict):
        examples = payload.get("examples", payload.get("tickets"))
    else:
        examples = None
    if not isinstance(examples, list):
        raise RuntimeError("GET /examples returned an unexpected format.")
    return examples


def main() -> None:
    config = load_config()
    examples = fetch_examples(config)
    results = []

    for example in examples:
        ticket_id = example.get("id")
        label = example.get("label") or {}
        action = label.get("action")
        expected = ACTION_TO_DECISION.get(action)
        ticket_preview = " ".join(
            f"{example.get('subject', '')} {example.get('body', '')}".split()
        )[:150]
        try:
            if expected is None:
                raise ValueError(f"Unsupported label action: {action}")
            # Keep the gold label out of the model input to avoid evaluation leakage.
            ticket = {key: value for key, value in example.items() if key != "label"}
            prediction = triage_ticket(ticket)
            got = prediction["decision"]
            match = got == expected
            model_reason = prediction["reason"]
            suspicious = prediction["suspicious"]
            faq_id = prediction["faq_id"]
            faq_quote = prediction["faq_quote"]
            error = None
        except Exception as exc:
            got = None
            match = False
            model_reason = None
            suspicious = None
            faq_id = None
            faq_quote = None
            # Avoid exposing credentials if an SDK error happens to echo them.
            error_text = str(exc)
            for secret in (config["OPENAI_API_KEY"], config["HELPDESK_API_KEY"]):
                if secret:
                    error_text = error_text.replace(secret, "[redacted]")
            error = f"{type(exc).__name__}: {error_text}"

        results.append(
            {
                "ticket_id": ticket_id,
                "expected": expected,
                "label_action": action,
                "label": label,
                "ticket_preview": ticket_preview,
                "got": got,
                "result": "match" if match else "miss",
                "reason": model_reason,
                "suspicious": suspicious,
                "faq_id": faq_id,
                "faq_quote": faq_quote,
                "error": error,
            }
        )

    score = sum(result["result"] == "match" for result in results)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "GET /examples",
                "score": f"{score}/{len(results)}",
                "total": len(results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    headers = ("Ticket ID", "Expected", "Got", "Result")
    rows = [
        (
            str(result["ticket_id"] or ""),
            str(result["expected"] or ""),
            str(result["got"] or "ERROR"),
            result["result"],
        )
        for result in results
    ]
    widths = tuple(
        max(len(header), *(len(row[index]) for row in rows)) if rows else len(header)
        for index, header in enumerate(headers)
    )

    def format_row(row: tuple[str, str, str, str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(format_row(row))
    print(f"Overall score: {score}/{len(results)}")

    for result in results:
        if result["result"] == "miss":
            print(f"\nMiss — {result['ticket_id']}")
            print(f"Ticket (first 150 characters): {result['ticket_preview']}")
            print(f"Expected: {result['expected']}")
            print(f"Agent reason: {result['reason'] or 'Unavailable (triage failed).'}")


if __name__ == "__main__":
    main()

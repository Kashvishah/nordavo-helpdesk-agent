"""Fetch selected tickets, run triage, and print each result."""

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

from config import load_config
from triage import triage_ticket


def fetch_ticket(config: dict[str, str], ticket_id: str) -> dict:
    base_url = config["HELPDESK_API_URL"].rstrip("/")
    encoded_id = urllib.parse.quote(ticket_id, safe="")
    request = urllib.request.Request(
        f"{base_url}/tickets/{encoded_id}",
        headers={
            "Authorization": f"Bearer {config['HELPDESK_API_KEY']}",
            "X-Candidate-Email": config["CANDIDATE_EMAIL"],
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Helpdesk returned HTTP {error.code}.") from None
    except urllib.error.URLError:
        raise RuntimeError("Could not reach the helpdesk API.") from None

    if not isinstance(payload, dict):
        raise RuntimeError("Helpdesk returned an unexpected ticket format.")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Triage selected helpdesk tickets.")
    parser.add_argument("ticket_ids", nargs="+", help="Ticket IDs, such as T007 T012")
    args = parser.parse_args()

    config = load_config()
    for ticket_id in args.ticket_ids:
        try:
            ticket = fetch_ticket(config, ticket_id)
        except Exception as error:
            print(f"{ticket_id}: ticket fetch failed: {error}")
            continue

        body = str(ticket.get("body") or "")
        preview = body[:80]
        print(f"Ticket {ticket_id}: {preview or '[empty ticket body]'}")
        if not body.strip():
            print("Skipped: ticket body is empty.\n")
            continue

        try:
            result = triage_ticket(ticket)
        except Exception:
            # Do not print SDK exception details, which may contain request data.
            print("Triage failed because the model call did not complete; continuing.\n")
            continue
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()

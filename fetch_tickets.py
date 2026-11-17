"""Fetch open helpdesk tickets and print a small, safe summary."""

import urllib.parse
import urllib.request

from config import load_config
from http_json import get_json


def fetch_open_tickets(config: dict[str, str]) -> list[dict]:
    base_url = config["HELPDESK_API_URL"].rstrip("/")
    tickets: list[dict] = []
    cursor = None

    while True:
        query = {"limit": 10, "status": "open"}
        if cursor:
            query["cursor"] = cursor
        url = f"{base_url}/tickets?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {config['HELPDESK_API_KEY']}",
                "X-Candidate-Email": config["CANDIDATE_EMAIL"],
                "Accept": "application/json",
            },
        )
        payload = get_json(request, service="Helpdesk")

        page = payload.get("tickets", []) if isinstance(payload, dict) else []
        tickets.extend(page)
        cursor = payload.get("next_cursor") if isinstance(payload, dict) else None
        if not cursor:
            return tickets


def main() -> None:
    config = load_config()
    tickets = fetch_open_tickets(config)
    print(f"Open ticket count: {len(tickets)}")
    for ticket in tickets:
        ticket_id = str(ticket.get("id", ""))
        preview = str(ticket.get("body", ""))[:60]
        print(f"{ticket_id}: {preview}")


if __name__ == "__main__":
    main()

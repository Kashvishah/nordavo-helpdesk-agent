"""Fetch open helpdesk tickets and print a small, safe summary."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from config import load_config


def _redact_header_values(message: str, config: dict[str, str]) -> str:
    """Avoid exposing any value that was sent in a request header."""
    for value in (
        f"Bearer {config['HELPDESK_API_KEY']}",
        config["HELPDESK_API_KEY"],
        config["CANDIDATE_EMAIL"],
        "application/json",
    ):
        if value:
            message = message.replace(value, "[redacted]")
    return message


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
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.load(response)
                break
            except urllib.error.HTTPError as error:
                if attempt < 5 and error.code == 503:
                    time.sleep(min(0.5 * (2**attempt), 8))
                    attempt += 1
                    continue
                if attempt < 5 and error.code == 429:
                    try:
                        delay = float(error.headers.get("Retry-After", "1"))
                    except (TypeError, ValueError):
                        delay = 1.0
                    time.sleep(max(0.0, delay))
                    attempt += 1
                    continue

                body = error.read(200).decode("utf-8", errors="replace")
                body = _redact_header_values(body, config)
                raise RuntimeError(
                    f"Helpdesk HTTP {error.code}; response body (first 200 characters): {body}"
                ) from None
            except urllib.error.URLError as error:
                reason = error.reason
                detail = f"{type(reason).__name__}: {reason}"
                detail = _redact_header_values(detail, config)
                raise RuntimeError(f"Helpdesk network error: {detail}") from None

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

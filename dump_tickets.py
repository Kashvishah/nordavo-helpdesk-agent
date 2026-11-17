"""Write all open helpdesk tickets to a local, readable text file."""

import json
from pathlib import Path

from config import load_config
from fetch_tickets import fetch_open_tickets


def main() -> None:
    config = load_config()
    tickets = fetch_open_tickets(config)

    blocks = []
    for ticket in tickets:
        ticket_id = str(ticket.get("id", "(no ID)"))
        blocks.append(
            f"Ticket {ticket_id}\n"
            f"{'=' * (7 + len(ticket_id))}\n"
            f"{json.dumps(ticket, ensure_ascii=False, indent=2)}"
        )

    output_path = Path(__file__).resolve().parent / "tickets_view.txt"
    output_path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
    print(f"Wrote {len(tickets)} tickets to {output_path.name}.")


if __name__ == "__main__":
    main()

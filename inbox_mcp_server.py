"""
MCP inbox server — serves emails from a PDF instead of a live mailbox.

Same pattern as Session 4's mcp_demo_server.py: a FastMCP server whose tools
the agents call over stdio. The agents never open the PDF themselves; they
only see these tools, so swapping the PDF for real Gmail/IMAP later means
changing this one file and nothing else.

PDF FORMAT: each email starts with a "From:" line, followed by optional
"To:", "Date:" and "Subject:" lines, a blank line, then the body. One email
can span pages, and one page can hold several emails.

  From: Priya Shah <priya@acme.com>
  To: me@example.com
  Date: 2026-11-26 09:14
  Subject: Contract review by Friday?

  Hi, could you review the attached contract ...

Which PDF: the INBOX_PDF env var (set by common.inbox_server), else
sample_inbox.pdf next to this file.

Try it without any LLM:  mcp dev inbox_mcp_server.py

FOOTGUN (from Session 4): never print() here — stdout IS the MCP wire protocol.
"""

import json
import os
import re
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader

HERE = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.getenv("INBOX_PDF") or os.path.join(HERE, "sample_inbox.pdf")

mcp = FastMCP("Inbox (PDF)")

_HEADER = re.compile(r"^(From|To|Cc|Date|Sent|Subject)\s*:\s*(.*)$", re.IGNORECASE)
_DATE_FORMATS = [
    "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d %b %Y %H:%M", "%d %b %Y", "%d %B %Y",
    "%b %d, %Y %I:%M %p", "%b %d, %Y", "%B %d, %Y %I:%M %p", "%B %d, %Y",
    "%a, %d %b %Y %H:%M:%S", "%a, %d %b %Y %H:%M", "%A, %B %d, %Y %I:%M %p",
    "%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%d/%Y",
]


def _parse_date(raw: str) -> str | None:
    """Turn a Date: header into YYYY-MM-DD, or None if we can't read it."""
    # Drop "(IST)", "+0530" and zone names like "GMT", but keep AM/PM.
    cleaned = re.sub(r"\s*\(.*?\)|\s+[+-]\d{4}$|\s+(?!AM$|PM$)[A-Z]{2,4}$", "", raw.strip())
    cleaned = re.sub(r"\s+[+-]\d{4}$", "", cleaned)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"\d{4}-\d{2}-\d{2}", raw)
    return m.group(0) if m else None


def _load_emails() -> list[dict]:
    if not os.path.exists(PDF_PATH):
        raise FileNotFoundError(f"Inbox PDF not found: {PDF_PATH}")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(PDF_PATH).pages)
    lines = [ln.rstrip() for ln in text.splitlines()]

    # Each email starts at a "From:" line.
    starts = [i for i, ln in enumerate(lines) if re.match(r"^\s*From\s*:", ln, re.IGNORECASE)]
    emails = []
    for n, start in enumerate(starts):
        block = lines[start: starts[n + 1] if n + 1 < len(starts) else len(lines)]
        headers, i = {}, 0
        while i < len(block):
            m = _HEADER.match(block[i].strip())
            if not m:
                break
            headers[m.group(1).lower()] = m.group(2).strip()
            i += 1
        body = "\n".join(block[i:]).strip()
        raw_date = headers.get("date") or headers.get("sent") or ""
        emails.append({
            "id": n + 1,
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": raw_date,
            "day": _parse_date(raw_date) if raw_date else None,
            "subject": headers.get("subject", "(no subject)"),
            "body": body,
        })
    return emails


def _summary(e: dict) -> dict:
    preview = re.sub(r"\s+", " ", e["body"])[:160]
    return {k: e[k] for k in ("id", "from", "date", "subject")} | {"preview": preview}


def _resolve_day(date: str, emails: list[dict]) -> str:
    """'' or 'latest' -> newest day in the inbox; 'today' -> real today; else as given."""
    if date.lower() == "today":
        return datetime.now().date().isoformat()
    if date in ("", "latest"):
        days = [e["day"] for e in emails if e["day"]]
        return max(days) if days else ""
    return date


@mcp.tool()
def inbox_overview() -> str:
    """Count the emails in the inbox and list which days they are from. Call this first."""
    emails = _load_emails()
    days = sorted({e["day"] for e in emails if e["day"]})
    return json.dumps({"total_emails": len(emails), "days": days, "latest_day": days[-1] if days else None})


@mcp.tool()
def list_emails(date: str = "latest") -> str:
    """List emails received on one day as JSON summaries (id, from, date, subject, preview).

    date: 'YYYY-MM-DD', 'latest' (the newest day in the inbox, the default), 'today', or 'all'.
    """
    emails = _load_emails()
    if date.lower() == "all":
        picked, day = emails, "all"
    else:
        day = _resolve_day(date, emails)
        picked = [e for e in emails if e["day"] == day]
    return json.dumps({"day": day, "count": len(picked), "emails": [_summary(e) for e in picked]})


@mcp.tool()
def get_email(email_id: int) -> str:
    """Get one email in full (headers and body) by its id from list_emails."""
    for e in _load_emails():
        if e["id"] == email_id:
            return json.dumps({k: v for k, v in e.items() if k != "day"})
    return json.dumps({"error": f"No email with id {email_id}"})


@mcp.tool()
def get_first_email() -> str:
    """Get the first email in the inbox (the top one in the PDF) in full."""
    emails = _load_emails()
    if not emails:
        return json.dumps({"error": "The inbox PDF has no emails (no 'From:' lines found)."})
    return json.dumps({k: v for k, v in emails[0].items() if k != "day"})


if __name__ == "__main__":
    mcp.run()

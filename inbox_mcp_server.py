"""
MCP inbox server — serves emails from a PDF instead of a live mailbox.

A FastMCP server whose tools the agents call over stdio. The agents never open the PDF themselves; they
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

Quoted replies stay inside their email: a "From:" line right after a reply
marker ("On ... wrote:", "-----Original Message-----", a "____" line, or
"Begin forwarded message") is treated as quoted text, not a new email.

Dates like 03/04/2026 are read day-first (3 April). Set INBOX_DATE_ORDER=MDY
for US-style exports (4 March). Emails with no readable date are listed as
"undated" and can't be picked by day.

Limitation: keep each Subject on one line. PDF text extraction drops blank
lines, so a subject wrapped onto a second line can't be told apart from the body.

Try it without any LLM:  mcp dev inbox_mcp_server.py

FOOTGUN: never print() here — stdout IS the MCP wire protocol.
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
# Lines that introduce a quoted/forwarded message inside an email's body.
_QUOTE_MARKER = re.compile(
    r"^(On .{3,200} wrote:|-{2,}\s*Original Message\s*-{2,}|_{5,}|-{2,}\s*Forwarded message\s*-{2,}|Begin forwarded message:?)$",
    re.IGNORECASE,
)
_DATE_FORMATS = [
    "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d %b %Y %H:%M", "%d %b %Y", "%d %B %Y",
    "%b %d, %Y %I:%M %p", "%b %d, %Y", "%B %d, %Y %I:%M %p", "%B %d, %Y",
    "%a, %d %b %Y %H:%M:%S", "%a, %d %b %Y %H:%M", "%A, %B %d, %Y %I:%M %p",
]
_DMY = ["%d/%m/%Y %H:%M", "%d/%m/%Y", "%d/%m/%Y %I:%M %p"]
_MDY = ["%m/%d/%Y %H:%M", "%m/%d/%Y", "%m/%d/%Y %I:%M %p"]
_NUMERIC_FORMATS = _MDY if os.getenv("INBOX_DATE_ORDER", "DMY").upper() == "MDY" else _DMY


def _parse_date(raw: str) -> str | None:
    """Turn a Date: header into YYYY-MM-DD, or None if we can't read it."""
    # Drop "(IST)", "+0530" and zone names like "GMT", but keep AM/PM.
    cleaned = re.sub(r"\s*\(.*?\)|\s+[+-]\d{4}$|\s+(?!AM$|PM$)[A-Z]{2,4}$", "", raw.strip())
    cleaned = re.sub(r"\s+[+-]\d{4}$", "", cleaned)
    for fmt in _DATE_FORMATS + _NUMERIC_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"\d{4}-\d{2}-\d{2}", raw)
    return m.group(0) if m else None


def _load_emails(path: str | None = None) -> list[dict]:
    """Parse the inbox PDF into emails. `path` lets the UI preview any PDF; the tools use PDF_PATH."""
    path = path or PDF_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"Inbox PDF not found: {path}")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    lines = [ln.rstrip() for ln in text.splitlines()]

    # Each email starts at a "From:" line, unless that line is part of a quoted
    # reply: it comes right after a reply marker, or the quoted text is ">"-prefixed.
    starts = []
    for i, ln in enumerate(lines):
        if not re.match(r"^\s*From\s*:", ln, re.IGNORECASE):
            continue
        before = [p.strip() for p in lines[max(0, i - 3):i] if p.strip()]
        if before and _QUOTE_MARKER.match(before[-1]):
            continue
        starts.append(i)
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


def emails_for_day(emails: list[dict], date: str) -> tuple[str, list[dict]]:
    """The emails list_emails returns for `date` ('latest', 'today', 'all' or YYYY-MM-DD)."""
    if date.lower() == "all":
        return "all", emails
    day = _resolve_day(date, emails)
    return day, [e for e in emails if e["day"] == day]


@mcp.tool()
def inbox_overview() -> str:
    """Count the emails in the inbox and list which days they are from. Call this first."""
    emails = _load_emails()
    days = sorted({e["day"] for e in emails if e["day"]})
    undated = [e["id"] for e in emails if not e["day"]]
    return json.dumps({"total_emails": len(emails), "days": days, "latest_day": days[-1] if days else None, "undated_ids": undated})


@mcp.tool()
def list_emails(date: str = "latest") -> str:
    """List emails received on one day as JSON summaries (id, from, date, subject, preview).

    date: 'YYYY-MM-DD', 'latest' (the newest day in the inbox, the default), 'today', or 'all'.
    """
    day, picked = emails_for_day(_load_emails(), date)
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

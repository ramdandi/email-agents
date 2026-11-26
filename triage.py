"""The Reader's triage task and its structured output, shared by Parts 3 and 4."""

from typing import Literal

from crewai import Agent, Task
from pydantic import BaseModel, Field


class EmailTriage(BaseModel):
    id: int = Field(description="The email id from list_emails")
    sender: str
    subject: str
    category: Literal["needs_action", "no_action"]
    reason: str = Field(description="One short sentence on why")
    action: str = Field(default="", description="For needs_action: what the user must do, in a few words. Empty otherwise.")


class InboxTriage(BaseModel):
    day: str = Field(description="The day that was triaged, YYYY-MM-DD")
    emails: list[EmailTriage]


def triage_task(reader: Agent, date: str) -> Task:
    return Task(
        description=(
            f"Triage every email received on '{date}' ('latest' means the newest day in the "
            "inbox). Call list_emails with that date to get them. If a preview isn't enough "
            "to decide, call get_email for the full text. Put EVERY email from that day in "
            "exactly one category: needs_action or no_action."
        ),
        expected_output="The day triaged and, for every email that day: id, sender, subject, category, reason, and the action needed.",
        agent=reader,
        output_pydantic=InboxTriage,
    )


def print_triage(triage: InboxTriage) -> str:
    """Print the triage as two lists and return the same text as Markdown."""
    need = [e for e in triage.emails if e.category == "needs_action"]
    rest = [e for e in triage.emails if e.category == "no_action"]
    lines = [f"Emails on {triage.day}: {len(triage.emails)}", "", f"1) NEEDS ACTION FROM ME ({len(need)})"]
    lines += [f"   #{e.id} {e.subject} — {e.sender}\n      -> {e.action or e.reason}" for e in need] or ["   (none)"]
    lines += ["", f"2) DOES NOT NEED ACTION FROM ME ({len(rest)})"]
    lines += [f"   #{e.id} {e.subject} — {e.sender}\n      ({e.reason})" for e in rest] or ["   (none)"]
    text = "\n".join(lines)
    print(text)
    return text

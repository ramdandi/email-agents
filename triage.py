"""The Reader's triage task and its structured output, shared by Parts 3 and 4."""

from typing import Literal

from crewai import Agent, Crew, Process, Task
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


def complete_triage(reader: Agent, triage: InboxTriage, expected: list[dict], day: str) -> list[int]:
    """Make the triage cover exactly the day's emails. Returns the ids the Reader had skipped.

    The Reader is told to sort every email, but a small model can drop some.
    Ids that aren't in the day's list are removed, and skipped emails are sent
    back to the Reader by id. The real sender and subject replace whatever the
    model wrote, so they always match the inbox.
    """
    by_id = {e["id"]: e for e in expected}
    triage.day = day
    triage.emails = list({t.id: t for t in reversed(triage.emails) if t.id in by_id}.values())  # one per email (first wins)
    missing = [i for i in by_id if i not in {t.id for t in triage.emails}]
    if missing:
        follow_up = Task(
            description=(
                "These emails still need triage: "
                + ", ".join(f"id {i} ({by_id[i]['subject']})" for i in missing)
                + ". For EACH one, call get_email with its id, then put it in exactly one "
                "category: needs_action or no_action."
            ),
            expected_output="For every listed email: id, sender, subject, category, reason, and the action needed.",
            agent=reader,
            output_pydantic=InboxTriage,
        )
        extra = Crew(agents=[reader], tasks=[follow_up], process=Process.sequential, verbose=True).kickoff().pydantic
        if extra:
            triage.emails += [t for t in extra.emails if t.id in missing]
    for t in triage.emails:
        t.sender, t.subject = by_id[t.id]["from"], by_id[t.id]["subject"]
    triage.emails.sort(key=lambda t: t.id)
    return missing


def format_triage(triage: InboxTriage) -> str:
    """The triage as two plain-text lists."""
    need = [e for e in triage.emails if e.category == "needs_action"]
    rest = [e for e in triage.emails if e.category == "no_action"]
    lines = [f"Emails on {triage.day}: {len(triage.emails)}", "", f"1) NEEDS ACTION FROM ME ({len(need)})"]
    lines += [f"   #{e.id} {e.subject} — {e.sender}\n      -> {e.action or e.reason}" for e in need] or ["   (none)"]
    lines += ["", f"2) DOES NOT NEED ACTION FROM ME ({len(rest)})"]
    lines += [f"   #{e.id} {e.subject} — {e.sender}\n      ({e.reason})" for e in rest] or ["   (none)"]
    return "\n".join(lines)

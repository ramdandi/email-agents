"""
Part 4 — Reader triages the day's emails, then hands off to the Writer,
which drafts a reply to every email that needs action.

  python part4_reader_to_writer.py                       # newest day in the inbox PDF
  python part4_reader_to_writer.py --date 2026-11-26
  python part4_reader_to_writer.py --pdf my_inbox.pdf

THE HANDOFF (scoped context): the Writer's task has
context=[triage], so the Writer sees only the Reader's triage output, not the
Reader's instructions. The Writer then fetches each needs-action email itself
through the same MCP inbox tools, so it replies to the real text,
not the Reader's summary of it.

Both agents' work is checked: the triage must cover every email that day, and
there must be one draft per needs-action email. Anything skipped is sent back
to the agent that skipped it. Drafts are printed and saved to
output/part4_replies.md. Nothing is sent.
"""

import argparse
from dataclasses import dataclass, field

from crewai import Crew, Process, Task
from pydantic import BaseModel

from common import exit_on_inbox_error, inbox_server, load_inbox, make_llm, make_reader, make_writer, require_key, save_output
from inbox_mcp_server import emails_for_day
from triage import InboxTriage, complete_triage, format_triage, triage_task


class Draft(BaseModel):
    email_id: int
    to: str
    subject: str
    body: str


class Drafts(BaseModel):
    drafts: list[Draft]


@dataclass
class Part4Result:
    triage: InboxTriage | None
    triage_raw: str
    drafts: list[Draft] | None
    drafts_raw: str
    day: str = ""
    triage_re_requested: list[int] = field(default_factory=list)  # ids the Reader skipped and was asked again for
    re_requested: list[int] = field(default_factory=list)  # ids the Writer skipped and was asked again for


def run(pdf: str | None = None, date: str = "latest") -> Part4Result:
    """Reader triages, Writer drafts. Raises common.InboxError if the PDF is missing or empty."""
    inbox = load_inbox(pdf)  # fail clearly on a bad PDF before any agent starts
    by_id = {e["id"]: e for e in inbox}
    day, expected = emails_for_day(inbox, date)

    llm = make_llm()
    reader = make_reader(llm, mcps=[inbox_server(pdf)])
    writer = make_writer(llm, mcps=[inbox_server(pdf)])

    triage = triage_task(reader, date)
    write = Task(
        description=(
            "The Reader has triaged the inbox (see context). For EVERY email it marked "
            "needs_action — and only those — call get_email with its id to read the full "
            "email, then draft a reply. Skip every no_action email."
        ),
        expected_output="One draft per needs_action email: email_id, to (the sender's address), subject ('Re: ...'), and the reply body with a sign-off.",
        agent=writer,
        context=[triage],  # <-- the handoff: Writer sees the Reader's output, nothing else
        output_pydantic=Drafts,
    )

    result = Crew(
        agents=[reader, writer],
        tasks=[triage, write],
        process=Process.sequential,  # pipeline: Reader -> Writer
        verbose=True,
    ).kickoff()

    out = Part4Result(
        triage=result.tasks_output[0].pydantic,
        triage_raw=result.tasks_output[0].raw,
        drafts=result.pydantic.drafts if result.pydantic else None,
        drafts_raw=result.raw,
        day=day,
    )

    # Check 1: the triage covers exactly the day's emails (skipped ones go back to the Reader).
    if out.triage:
        out.triage_re_requested = complete_triage(reader, out.triage, expected, day)

    # Check 2: one draft per needs-action email, and nothing else.
    if out.triage and out.drafts is not None:
        needed = {e.id: e for e in out.triage.emails if e.category == "needs_action"}
        out.drafts = [d for d in out.drafts if d.email_id in needed]
        missing = [i for i in needed if i not in {d.email_id for d in out.drafts}]
        if missing:
            out.re_requested = missing
            follow_up = Task(
                description=(
                    "The Reader marked these emails as needing action, but they have no draft "
                    f"reply yet: {', '.join(f'id {i} ({needed[i].subject})' for i in missing)}. "
                    "For EACH of them, call get_email with its id to read it, then draft a reply."
                ),
                expected_output="One draft per listed email: email_id, to, subject ('Re: ...'), and the reply body with a sign-off.",
                agent=writer,
                output_pydantic=Drafts,
            )
            extra = Crew(agents=[writer], tasks=[follow_up], process=Process.sequential, verbose=True).kickoff()
            if extra.pydantic:
                out.drafts += [d for d in extra.pydantic.drafts if d.email_id in missing]
        out.drafts.sort(key=lambda d: d.email_id)

    # Reply to the address actually in the email, not one the model wrote.
    for d in out.drafts or []:
        if d.email_id in by_id and by_id[d.email_id]["from"]:
            d.to = by_id[d.email_id]["from"]

    triage_text = format_triage(out.triage) if out.triage else out.triage_raw
    save_output(
        "part4_replies.md",
        f"# Part 4 — Reader -> Writer\n\n## Reader's triage\n\n```\n{triage_text}\n```\n\n"
        f"## Writer's draft replies\n\n```\n{format_drafts(out.drafts) if out.drafts is not None else out.drafts_raw}\n```\n",
    )
    return out


def format_drafts(drafts: list[Draft]) -> str:
    return "\n\n".join(
        f"--- Reply to email #{d.email_id} ---\nTo: {d.to}\nSubject: {d.subject}\n\n{d.body}" for d in drafts
    ) or "(no emails needed action)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", help="inbox PDF (default: sample_inbox.pdf)")
    parser.add_argument("--date", default="latest", help="YYYY-MM-DD, 'latest' (default) or 'today'")
    args = parser.parse_args()
    require_key()

    out = exit_on_inbox_error(run, args.pdf, args.date)
    if out.triage_re_requested:
        print(f"[check] Reader skipped {', '.join(f'#{i}' for i in out.triage_re_requested)} — asked it to sort those too.")
    if out.re_requested:
        print(f"[check] Writer skipped {', '.join(f'#{i}' for i in out.re_requested)} — asked it to draft those too.")

    # Printed only now, after any follow-up crews have finished logging.
    print("\n=== STEP 1: READER'S TRIAGE ===\n")
    print(format_triage(out.triage) if out.triage else out.triage_raw)
    print("\n=== STEP 2: WRITER'S DRAFT REPLIES (not sent) ===\n")
    print(format_drafts(out.drafts) if out.drafts is not None else out.drafts_raw)
    print("\nSaved to output/part4_replies.md")


if __name__ == "__main__":
    main()

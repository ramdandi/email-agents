"""
Part 4 — Reader triages the day's emails, then hands off to the Writer,
which drafts a reply to every email that needs action.

  python part4_reader_to_writer.py                       # newest day in the inbox PDF
  python part4_reader_to_writer.py --date 2026-11-26
  python part4_reader_to_writer.py --pdf my_inbox.pdf

THE HANDOFF (Session 3's scoped context): the Writer's task has
context=[triage], so the Writer sees only the Reader's triage output, not the
Reader's instructions. The Writer then fetches each needs-action email itself
through the same MCP inbox tools (Session 4), so it replies to the real text,
not the Reader's summary of it.

Drafts are printed and saved to output/part4_replies.md. Nothing is sent.
"""

import argparse

from crewai import Crew, Process, Task
from pydantic import BaseModel

from common import inbox_server, make_llm, make_reader, make_writer, require_key, save_output
from triage import print_triage, triage_task


class Draft(BaseModel):
    email_id: int
    to: str
    subject: str
    body: str


class Drafts(BaseModel):
    drafts: list[Draft]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", help="inbox PDF (default: sample_inbox.pdf)")
    parser.add_argument("--date", default="latest", help="YYYY-MM-DD, 'latest' (default) or 'today'")
    args = parser.parse_args()
    require_key()

    llm = make_llm()
    reader = make_reader(llm, mcps=[inbox_server(args.pdf)])
    writer = make_writer(llm, mcps=[inbox_server(args.pdf)])

    triage = triage_task(reader, args.date)
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

    triage_out = result.tasks_output[0].pydantic
    drafts = result.pydantic

    # Check the Writer's work against the Reader's list: small models sometimes
    # stop after the first draft. Ask again, by id, for any it missed.
    if triage_out and drafts is not None:
        needed = [e for e in triage_out.emails if e.category == "needs_action"]
        missing = [e for e in needed if e.id not in {d.email_id for d in drafts.drafts}]
        if missing:
            ids = ", ".join(f"#{e.id}" for e in missing)
            print(f"[check] Writer skipped {ids} — asking it to draft those too.\n")
            follow_up = Task(
                description=(
                    "The Reader marked these emails as needing action, but they have no draft "
                    f"reply yet: {', '.join(f'id {e.id} ({e.subject})' for e in missing)}. "
                    "For EACH of them, call get_email with its id to read it, then draft a reply."
                ),
                expected_output="One draft per listed email: email_id, to, subject ('Re: ...'), and the reply body with a sign-off.",
                agent=writer,
                output_pydantic=Drafts,
            )
            extra = Crew(agents=[writer], tasks=[follow_up], process=Process.sequential, verbose=True).kickoff()
            if extra.pydantic:
                drafts.drafts += [d for d in extra.pydantic.drafts if d.email_id in {e.id for e in missing}]
            drafts.drafts.sort(key=lambda d: d.email_id)

    # Print the results only now, after any follow-up crew has finished logging.
    print("\n=== STEP 1: READER'S TRIAGE ===\n")
    if triage_out:
        triage_text = print_triage(triage_out)
    else:
        triage_text = result.tasks_output[0].raw
        print(triage_text)

    print("\n=== STEP 2: WRITER'S DRAFT REPLIES (not sent) ===\n")
    if drafts is None:
        drafts_text = result.raw
    else:
        drafts_text = "\n\n".join(
            f"--- Reply to email #{d.email_id} ---\nTo: {d.to}\nSubject: {d.subject}\n\n{d.body}" for d in drafts.drafts
        ) or "(no emails needed action)"
    print(drafts_text)

    path = save_output(
        "part4_replies.md",
        f"# Part 4 — Reader -> Writer\n\n## Reader's triage\n\n```\n{triage_text}\n```\n\n## Writer's draft replies\n\n```\n{drafts_text}\n```\n",
    )
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()

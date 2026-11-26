"""
Part 2 — Writer agent connects to the inbox and replies to the first email.

  python part2_reply_first_email.py                      # uses sample_inbox.pdf
  python part2_reply_first_email.py --pdf my_inbox.pdf   # your own inbox export

"Connecting to email" = the Writer gets the MCP inbox server's tools
(Session 4 pattern). It has to call get_first_email itself; we never hand it
the email text. The reply is saved to output/part2_reply.md. Nothing is sent.
"""

import argparse

from crewai import Crew, Process, Task

from common import inbox_server, make_llm, make_writer, require_key, save_output


def run(pdf: str | None = None) -> str:
    """Have the Writer fetch the first inbox email via MCP and reply. Returns the draft."""
    writer = make_writer(make_llm(), mcps=[inbox_server(pdf)])
    task = Task(
        description=(
            "Use your inbox tool to fetch the FIRST email in the inbox (get_first_email). "
            "Then write a reply to it. Answer every question and request in it, and use "
            "placeholders like [confirm date] for anything you'd have to guess."
        ),
        expected_output=(
            "First a line 'Replying to: <sender> — <subject>', then a blank line, then the reply: "
            "a 'Subject: Re: ...' line, a blank line, and the reply body with a sign-off."
        ),
        agent=writer,
    )
    reply = Crew(agents=[writer], tasks=[task], process=Process.sequential, verbose=True).kickoff().raw
    save_output("part2_reply.md", f"# Part 2 — reply to the first inbox email\n\n{reply}\n")
    return reply


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", help="inbox PDF (default: sample_inbox.pdf)")
    args = parser.parse_args()
    require_key()
    reply = run(args.pdf)
    print("\n=== DRAFT REPLY TO FIRST EMAIL (not sent) ===\n")
    print(reply)
    print("\nSaved to output/part2_reply.md")


if __name__ == "__main__":
    main()

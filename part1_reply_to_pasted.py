"""
Part 1 — Writer agent replies to an email you paste in.

  python part1_reply_to_pasted.py                 # paste the email, then Ctrl-D
  python part1_reply_to_pasted.py email.txt       # or read it from a text file
  pbpaste | python part1_reply_to_pasted.py       # or pipe it from the clipboard (macOS)

No inbox and no MCP here: the email text goes straight into the Writer's task.
The reply is printed and saved to output/part1_reply.md. Nothing is sent.
"""

import sys

from crewai import Crew, Process, Task

from common import make_llm, make_writer, require_key, save_output


def run(email: str) -> str:
    """Draft a reply to one email's text. Returns the draft (subject line + body)."""
    writer = make_writer(make_llm())
    task = Task(
        description=(
            "Write a reply to this email. Answer every question and request in it. "
            "Use placeholders like [confirm date] for anything you'd have to guess.\n\n"
            f"--- EMAIL ---\n{email}\n--- END EMAIL ---"
        ),
        expected_output="Only the reply: a 'Subject: Re: ...' line, a blank line, then the reply body with a sign-off.",
        agent=writer,
    )
    reply = Crew(agents=[writer], tasks=[task], process=Process.sequential, verbose=True).kickoff().raw
    save_output("part1_reply.md", f"# Part 1 — reply to pasted email\n\n## Email\n\n```\n{email}\n```\n\n## Draft reply\n\n{reply}\n")
    return reply


def read_email() -> str:
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1]) as f:
                return f.read()
        except OSError as e:
            sys.exit(f"Error: couldn't read {sys.argv[1]}: {e.strerror}")
    if sys.stdin.isatty():
        print("Paste the email (headers optional), then press Ctrl-D on a new line:\n")
    return sys.stdin.read()


def main() -> None:
    require_key()
    email = read_email().strip()
    if not email:
        sys.exit("No email text given.")
    reply = run(email)
    print("\n=== DRAFT REPLY (not sent) ===\n")
    print(reply)
    print("\nSaved to output/part1_reply.md")


if __name__ == "__main__":
    main()

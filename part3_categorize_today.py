"""
Part 3 — Reader agent reads one day's emails and sorts them into
  1) needs action from me
  2) does not need action from me

  python part3_categorize_today.py                       # newest day in the inbox PDF
  python part3_categorize_today.py --date 2026-11-26     # a specific day
  python part3_categorize_today.py --date today          # the real calendar today
  python part3_categorize_today.py --pdf my_inbox.pdf

Why "newest day" by default: an exported PDF is a snapshot, so the real
calendar today often has no emails in it. Use --date today if yours does.

The Reader reads only through the MCP inbox tools and returns structured
output (a Pydantic model). The result is checked against the day's actual
emails, and any the Reader skipped are sent back to it. Saved to
output/part3_triage.md and .json.
"""

import argparse
from dataclasses import dataclass, field

from crewai import Crew, Process

from common import exit_on_inbox_error, inbox_server, load_inbox, make_llm, make_reader, require_key, save_output
from inbox_mcp_server import emails_for_day
from triage import InboxTriage, complete_triage, format_triage, triage_task


@dataclass
class Part3Result:
    triage: InboxTriage | None  # None if the model didn't return valid structured output
    raw: str
    day: str
    re_requested: list[int] = field(default_factory=list)  # ids the Reader skipped and was asked again for


def run(pdf: str | None = None, date: str = "latest") -> Part3Result:
    """Triage one day's emails. Raises common.InboxError if the PDF is missing or empty."""
    day, expected = emails_for_day(load_inbox(pdf), date)
    reader = make_reader(make_llm(), mcps=[inbox_server(pdf)])
    result = Crew(agents=[reader], tasks=[triage_task(reader, date)], process=Process.sequential, verbose=True).kickoff()

    out = Part3Result(triage=result.pydantic, raw=result.raw, day=day)
    if out.triage is not None:
        out.re_requested = complete_triage(reader, out.triage, expected, day)
        save_output("part3_triage.json", out.triage.model_dump_json(indent=2))
        save_output("part3_triage.md", f"# Part 3 — inbox triage\n\n```\n{format_triage(out.triage)}\n```\n")
    else:
        save_output("part3_triage.md", f"# Part 3 — inbox triage\n\n{out.raw}\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", help="inbox PDF (default: sample_inbox.pdf)")
    parser.add_argument("--date", default="latest", help="YYYY-MM-DD, 'latest' (default) or 'today'")
    args = parser.parse_args()
    require_key()

    out = exit_on_inbox_error(run, args.pdf, args.date)
    print("\n=== INBOX TRIAGE ===\n")
    if out.re_requested:
        print(f"[check] Reader skipped {', '.join(f'#{i}' for i in out.re_requested)} — asked it to sort those too.\n")
    print(format_triage(out.triage) if out.triage else out.raw)
    print("\nSaved to output/part3_triage.md" + (" and part3_triage.json" if out.triage else ""))


if __name__ == "__main__":
    main()

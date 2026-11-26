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
output (a Pydantic model), saved to output/part3_triage.md and .json.
"""

import argparse

from crewai import Crew, Process

from common import inbox_server, make_llm, make_reader, require_key, save_output
from triage import print_triage, triage_task


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", help="inbox PDF (default: sample_inbox.pdf)")
    parser.add_argument("--date", default="latest", help="YYYY-MM-DD, 'latest' (default) or 'today'")
    args = parser.parse_args()
    require_key()

    reader = make_reader(make_llm(), mcps=[inbox_server(args.pdf)])
    task = triage_task(reader, args.date)
    result = Crew(agents=[reader], tasks=[task], process=Process.sequential, verbose=True).kickoff()

    triage = result.pydantic
    print("\n=== INBOX TRIAGE ===\n")
    if triage is None:  # the model didn't return valid structured output
        print(result.raw)
        save_output("part3_triage.md", f"# Part 3 — inbox triage\n\n{result.raw}\n")
        return
    text = print_triage(triage)
    save_output("part3_triage.json", triage.model_dump_json(indent=2))
    path = save_output("part3_triage.md", f"# Part 3 — inbox triage\n\n```\n{text}\n```\n")
    print(f"\nSaved to {path} (and part3_triage.json)")


if __name__ == "__main__":
    main()

"""
Run one part for real and save a screenshot of what the agents did.

  python capture.py part1        # also: part2, part3, part4
  python capture.py part3 --date 2026-11-26   # extra args go to the part

Writes:
  screenshots/<part>.svg   the screenshot (renders on GitHub)
  screenshots/<part>.png   same image as PNG for LinkedIn (macOS only, via Quick Look)
  output/logs/<part>.log   the full verbose CrewAI log of the run

The screenshot shows the real run: the command, which agent called which MCP
tool, and the final output. Nothing in it is typed in by hand.
"""

import os
import re
import shutil
import subprocess
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = {
    "part1": ["part1_reply_to_pasted.py", os.path.join("samples", "pasted_email.txt")],
    "part2": ["part2_reply_first_email.py"],
    "part3": ["part3_categorize_today.py"],
    "part4": ["part4_reader_to_writer.py"],
}
TITLES = {
    "part1": "Part 1 — Writer replies to a pasted email",
    "part2": "Part 2 — Writer reads the inbox (MCP) and replies to the first email",
    "part3": "Part 3 — Reader sorts the day's emails: action needed or not",
    "part4": "Part 4 — Reader hands off to Writer, which replies to every action email",
}
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in PARTS:
        sys.exit(f"usage: python capture.py {{{','.join(PARTS)}}} [args for that part]")
    part, extra = sys.argv[1], sys.argv[2:]
    cmd = [sys.executable, "-W", "ignore", *PARTS[part], *extra]
    shown = "python " + " ".join([*PARTS[part], *extra])

    print(f"Running: {shown}  (this calls Groq; takes ~10s-2min)")
    env = dict(os.environ, CREWAI_TRACING_ENABLED="false")
    proc = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    log = ANSI.sub("", proc.stdout + proc.stderr)

    os.makedirs(os.path.join(HERE, "output", "logs"), exist_ok=True)
    with open(os.path.join(HERE, "output", "logs", f"{part}.log"), "w") as f:
        f.write(log)

    # Which agent called which MCP tool, in order (from CrewAI's verbose boxes).
    steps, agent = [], None
    for line in log.splitlines():
        line = line.strip("│ ").strip()
        if m := re.match(r"^Agent: (.+)$", line):
            agent = m.group(1).strip()
        elif m := re.match(r"^Tool: (\S+)$", line):
            step = f"{agent}  →  {m.group(1)}"
            if not steps or steps[-1] != step:
                steps.append(step)
    # The results come from stdout only; stderr (server logs, warnings) stays in the log file.
    out = ANSI.sub("", proc.stdout)
    final = out[out.find("=== "):] if "=== " in out else log[-3000:]
    final = re.split(r"\nSaved to ", final)[0].strip()  # drop our "Saved to" line and CrewAI's trailing summary box
    checks = [ln for ln in out.splitlines() if ln.startswith("[check]")]
    final = "\n".join(ln for ln in final.splitlines() if not ln.startswith("[check]"))
    if checks:  # keep the Part 4 self-check visible, just above the results
        final = "\n".join(checks) + "\n\n" + final

    console = Console(record=True, width=104, file=open(os.devnull, "w"))
    console.print(Text(f"$ {shown}", style="bold green"))
    console.print()
    if steps:
        console.print(Panel("\n".join(steps), title="Agent → MCP tool calls", title_align="left", border_style="cyan"))
    console.print(Text(final))
    if proc.returncode != 0:
        console.print(Text(f"\n[exit code {proc.returncode}]", style="bold red"))

    shots = os.path.join(HERE, "screenshots")
    os.makedirs(shots, exist_ok=True)
    svg = os.path.join(shots, f"{part}.svg")
    console.save_svg(svg, title=TITLES[part])
    print(f"Saved {svg}")

    if shutil.which("qlmanage"):  # macOS: turn the SVG into a PNG for LinkedIn
        subprocess.run(["qlmanage", "-t", "-s", "1800", "-o", shots, svg], capture_output=True)
        png = svg + ".png"
        if os.path.exists(png):
            out_png = os.path.join(shots, f"{part}.png")
            os.replace(png, out_png)
            # Quick Look pads the image to a square; crop it back to the SVG's shape (centred).
            m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', open(svg).read())
            if m and shutil.which("sips"):
                w, h = float(m.group(1)), float(m.group(2))
                size = 1800
                crop_w, crop_h = (size, round(size * h / w)) if w >= h else (round(size * w / h), size)
                subprocess.run(["sips", "-c", str(crop_h), str(crop_w), out_png], capture_output=True)
            print(f"Saved {out_png}")
    if proc.returncode != 0:
        sys.exit(f"{part} failed (exit {proc.returncode}); see output/logs/{part}.log")


if __name__ == "__main__":
    main()

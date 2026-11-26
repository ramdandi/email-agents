# Email Agents — Reader + Writer with CrewAI and MCP

Two AI agents that work through your inbox:

- A **Reader** sorts the day's emails into *needs action from me* and *doesn't need action from me*.
- A **Writer** drafts replies, and the Reader hands it the emails that need action.

The inbox comes from a **PDF export** and is served to the agents by an **MCP server**. The agents never open the PDF themselves, so connecting a live mailbox (Gmail/IMAP) later only means changing that one server file.

**Nothing is ever sent.** Every reply is a draft, and where a reply needs a decision only you can make, the Writer leaves a placeholder like `[pick Tue or Thu]`.

**Built with:** [CrewAI](https://github.com/crewAIInc/crewAI) for the agents, the [Model Context Protocol](https://modelcontextprotocol.io) (MCP) for inbox access, [Groq](https://groq.com) running `gpt-oss-20b` as the LLM, and [Streamlit](https://streamlit.io) for the web UI.

**Design choices:**
- **Two narrow agents in a pipeline.** The Reader only sorts and the Writer only drafts, run in order with `Process.sequential`.
- **A scoped handoff.** The Writer's task has `context=[triage]`, so it sees the Reader's output and nothing else.
- **Structured output.** The triage and the drafts are Pydantic models, not free text.
- **The agents choose their own tools.** They decide when to call the inbox tools `get_first_email`, `list_emails` and `get_email`. The code never hands them email text.

## How it fits together

```
 sample_inbox.pdf
        │  (read only by the server)
        ▼
 inbox_mcp_server.py ── MCP over stdio ──┐
   tools: inbox_overview, list_emails,   │
          get_email, get_first_email     │
                                         ▼
                     ┌──── CrewAI crew (Groq: gpt-oss-20b) ────┐
                     │  Reader ──context=[triage]──▶ Writer     │
                     │  "needs action?"             draft replies│
                     └─────────────────────────────────────────┘
                                         │
                                         ▼
                          output/*.md  (drafts, never sent)
```

## What it does

| # | Script | What happens |
|---|---|---|
| 1 | `part1_reply_to_pasted.py` | Paste an email, and the **Writer** drafts a reply. No inbox involved. |
| 2 | `part2_reply_first_email.py` | The **Writer** connects to the inbox through MCP, calls `get_first_email`, and replies to it. |
| 3 | `part3_categorize_today.py` | The **Reader** lists one day's emails through MCP and sorts every one into the two categories. |
| 4 | `part4_reader_to_writer.py` | The **Reader** triages, then hands off to the **Writer**, which fetches each needs-action email and drafts a reply. |

## Web UI (real test runs)

`streamlit run app.py` gives every part a tab. These screenshots were taken by `ui_screenshots.py`, which clicks each tab's button in Chrome, waits for the agents, and saves the page.

### Part 4 — Reader sorts the day's emails, Writer drafts replies
![UI Part 4](screenshots/ui_part4.png)

### Part 3 — sort the day's emails
![UI Part 3](screenshots/ui_part3.png)

### Part 2 — reply to the first inbox email
![UI Part 2](screenshots/ui_part2.png)

### Part 1 — reply to a pasted email
![UI Part 1](screenshots/ui_part1.png)

## Run it yourself

You need Python **3.10–3.13** and a free Groq API key from [console.groq.com](https://console.groq.com).

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your GROQ_API_KEY in .env
```

```bash
python part1_reply_to_pasted.py samples/pasted_email.txt   # or run with no file and paste, then Ctrl-D
python part2_reply_first_email.py
python part3_categorize_today.py
python part4_reader_to_writer.py
```

**Or use the web UI:**

```bash
streamlit run app.py
```

It opens at http://localhost:8501. Pick the sample inbox or upload your own PDF, choose the day, and run any part from its tab. Drafts appear in boxes with a copy button. The UI calls the same agents as the scripts.

**Use your own inbox:** export some emails to a PDF, with each email starting with a `From:` line and followed by `Date:` and `Subject:` lines, then pass it with `--pdf my_inbox.pdf`. `python make_sample_inbox.py` shows the format; it generates the fake `sample_inbox.pdf` used here, and every person and company in it is made up.

**Which day counts as "today":** Parts 3 and 4 default to the newest day in the PDF, because an export is a snapshot. Use `--date today` for the real calendar day, or `--date 2026-11-26` for a specific one.

**Try the MCP server with no LLM:** run `mcp dev inbox_mcp_server.py` and call the tools in MCP Inspector.

**Retake the screenshots:** with the UI running, `python ui_screenshots.py`.

## Files

| File | What it is |
|---|---|
| `inbox_mcp_server.py` | MCP server: parses the PDF into emails and serves them as 4 tools |
| `common.py` | LLM setup, the Reader and Writer agents, MCP launch config, Groq compatibility settings |
| `triage.py` | The Reader's task and its Pydantic output, shared by Parts 3 and 4 |
| `part1_…` – `part4_…` | One script per assignment part; each has a `run()` function the UI calls |
| `app.py` | Streamlit web UI for all 4 parts |
| `ui_screenshots.py` | Runs each part in the web UI (headless Chrome via Playwright) and saves `screenshots/ui_partN.png` |
| `make_sample_inbox.py` | Generates the fake `sample_inbox.pdf` |
| `output/` | Drafts and triage from the latest runs |

"""
Simple web UI for the email agents.

  streamlit run app.py

Pick an inbox (the sample PDF or upload your own), then run any of the 4 parts
from its tab. It calls the same run() functions as the command-line scripts,
so the agents, the MCP inbox server and the Groq fixes are all the same.
Nothing is ever sent — every reply is a draft you can copy.
"""

import os

os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")  # no "share trace?" prompt blocking the server

import streamlit as st  # noqa: E402

import part1_reply_to_pasted as part1  # noqa: E402
import part2_reply_first_email as part2  # noqa: E402
import part3_categorize_today as part3  # noqa: E402
import part4_reader_to_writer as part4  # noqa: E402
from common import HERE, MODEL, MY_NAME  # noqa: E402
from inbox_mcp_server import _load_emails  # noqa: E402

SAMPLE_PDF = os.path.join(HERE, "sample_inbox.pdf")
UPLOAD_DIR = os.path.join(HERE, "uploads")
SAMPLE_EMAIL = open(os.path.join(HERE, "samples", "pasted_email.txt")).read()

st.set_page_config(page_title="Email Agents", page_icon="✉️", layout="wide")


# ---------------------------------------------------------------- helpers
def show_draft(text: str, key: str) -> None:
    """A draft in a copyable box (Streamlit code blocks have a copy button)."""
    st.code(text, language=None, wrap_lines=True)


def show_triage(triage) -> None:
    need = [e for e in triage.emails if e.category == "needs_action"]
    rest = [e for e in triage.emails if e.category == "no_action"]
    st.caption(f"{len(triage.emails)} emails on {triage.day}")
    left, right = st.columns(2)
    with left:
        st.markdown(f"#### 🔴 Needs action from me ({len(need)})")
        for e in need:
            with st.container(border=True):
                st.markdown(f"**#{e.id} · {e.subject}**")
                st.caption(e.sender)
                st.markdown(f"➡️ {e.action or e.reason}")
        if not need:
            st.info("Nothing needs action.")
    with right:
        st.markdown(f"#### ⚪ Doesn't need action ({len(rest)})")
        for e in rest:
            with st.container(border=True):
                st.markdown(f"**#{e.id} · {e.subject}**")
                st.caption(f"{e.sender} — {e.reason}")
        if not rest:
            st.info("Everything needs action.")


def show_day_emails(emails: list[dict], day: str, days: list[str]) -> None:
    """Show which emails Parts 3/4 will work on, before running them."""
    from datetime import date as _date
    target = {"latest": days[0] if days else None, "today": _date.today().isoformat()}.get(day, day)
    picked = [e for e in emails if e["day"] == target]
    with st.expander(f"📬 {len(picked)} email(s) on {target} will be sorted", expanded=False):
        if not picked:
            st.warning("No emails on that day. Pick another day in the sidebar.")
        st.dataframe(
            [{"#": e["id"], "From": e["from"], "Subject": e["subject"], "Date": e["date"]} for e in picked],
            hide_index=True, use_container_width=True,
        )


def run_agents(label: str, fn, *args):
    """Run a part with a status box; keep errors on screen instead of crashing the page."""
    with st.status(f"{label} — the agents are working (10s to 2 min)…", expanded=False) as status:
        try:
            result = fn(*args)
        except Exception as e:  # show the real error, e.g. a bad key or Groq being down
            status.update(label=f"{label} failed", state="error", expanded=True)
            st.exception(e)
            return None
        status.update(label=f"{label} — done", state="complete")
    return result


# ---------------------------------------------------------------- sidebar: inbox
with st.sidebar:
    st.header("📥 Inbox")
    source = st.radio("Inbox PDF", ["Sample inbox", "Upload my own"], label_visibility="collapsed")
    pdf_path = SAMPLE_PDF
    if source == "Upload my own":
        upload = st.file_uploader("Inbox PDF", type="pdf", help="Each email starts with a 'From:' line, then 'Date:' and 'Subject:' lines.")
        if upload is None:
            st.info("Upload a PDF, or switch back to the sample inbox.")
            st.stop()
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        pdf_path = os.path.join(UPLOAD_DIR, "inbox.pdf")
        with open(pdf_path, "wb") as f:
            f.write(upload.getbuffer())

    try:
        emails = _load_emails(pdf_path)
    except Exception as e:
        st.error(f"Couldn't read that PDF: {e}")
        st.stop()
    if not emails:
        st.error("No emails found. Each email must start with a line like 'From: Name <a@b.com>'.")
        st.stop()

    days = sorted({e["day"] for e in emails if e["day"]}, reverse=True)
    per_day = {d: sum(e["day"] == d for e in emails) for d in days}
    st.success(f"{len(emails)} emails  \n" + "  \n".join(f"{d}: {n}" for d, n in per_day.items()))
    day = st.selectbox(
        "Day for Parts 3 & 4", ["latest"] + days + ["today"],
        format_func=lambda d: {"latest": f"Newest in PDF ({days[0] if days else '—'})", "today": "Real today"}.get(d, d),
    )
    with st.expander("Preview emails"):
        for e in emails:
            st.markdown(f"**#{e['id']} {e['subject']}**  \n{e['from']}  \n_{e['date']}_")

    st.divider()
    if os.getenv("GROQ_API_KEY"):
        st.caption(f"✅ Groq key loaded · `{MODEL.split('/', 1)[-1]}`")
    else:
        st.error("No GROQ_API_KEY. Add it to .env and restart.")
    st.caption(f"Signing replies as: **{MY_NAME}** (set MY_NAME in .env)")


# ---------------------------------------------------------------- main
st.title("✉️ Email Agents")
st.markdown(
    "A **Reader** sorts your emails and a **Writer** drafts replies. They read the inbox "
    "through an **MCP server**, using CrewAI on Groq. **Nothing is ever sent.** Replies are drafts, "
    "with `[placeholders]` where you need to decide something."
)

t1, t2, t3, t4 = st.tabs(["1 · Reply to a pasted email", "2 · Reply to the first email", "3 · Sort the day's emails", "4 · Sort + draft replies"])
state = st.session_state

with t1:
    st.markdown("Paste any email, and the **Writer** drafts a reply. This doesn't use the inbox.")
    email_text = st.text_area("Email", value=SAMPLE_EMAIL, height=220)
    if st.button("✍️ Draft reply", type="primary", key="b1", disabled=not email_text.strip()):
        state["p1"] = run_agents("Writer", part1.run, email_text.strip())
    if state.get("p1"):
        st.markdown("#### Draft reply")
        show_draft(state["p1"], "p1")

with t2:
    first = emails[0]
    st.markdown("The **Writer** connects to the inbox through MCP, fetches the first email itself, and replies to it.")
    st.caption(f"First email in this inbox: **{first['subject']}** — {first['from']}")
    if st.button("✍️ Reply to first email", type="primary", key="b2"):
        state["p2"] = run_agents("Writer", part2.run, pdf_path)
    if state.get("p2"):
        st.markdown("#### Draft reply")
        show_draft(state["p2"], "p2")

with t3:
    st.markdown("The **Reader** lists the day's emails through MCP and sorts every one of them.")
    show_day_emails(emails, day, days)
    if st.button("🔎 Sort emails", type="primary", key="b3"):
        state["p3"] = run_agents("Reader", part3.run, pdf_path, day)
    if state.get("p3"):
        triage, raw = state["p3"]
        if triage:
            show_triage(triage)
        else:
            st.code(raw, language=None, wrap_lines=True)

with t4:
    st.markdown(
        "The **Reader** sorts the day's emails, then hands its list to the **Writer**. The Writer fetches each "
        "email that needs action and drafts a reply."
    )
    show_day_emails(emails, day, days)
    if st.button("🚀 Sort and draft replies", type="primary", key="b4"):
        state["p4"] = run_agents("Reader → Writer", part4.run, pdf_path, day)
    out = state.get("p4")
    if out:
        st.markdown("### Step 1 · Reader's triage")
        if out.triage:
            show_triage(out.triage)
        else:
            st.code(out.triage_raw, language=None, wrap_lines=True)
        st.markdown("### Step 2 · Writer's draft replies")
        if out.re_requested:
            st.info(f"The Writer skipped {', '.join(f'#{i}' for i in out.re_requested)} at first, so it was asked again.")
        if out.drafts is None:
            st.code(out.drafts_raw, language=None, wrap_lines=True)
        elif not out.drafts:
            st.success("No emails needed action, so there's nothing to reply to.")
        for d in out.drafts or []:
            with st.container(border=True):
                st.markdown(f"**Reply to #{d.email_id}** · to {d.to}")
                show_draft(f"Subject: {d.subject}\n\n{d.body}", f"p4-{d.email_id}")

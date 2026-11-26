"""
Basic checks for the email agents. No Groq calls, no API key needed.

  pytest -q
"""

import json
import os
import subprocess
import sys

import litellm
import pytest

import common
import inbox_mcp_server as inbox
import triage as T

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def no_real_waits_or_output(monkeypatch, tmp_path):
    """Keep tests fast and keep them from overwriting the committed output/ files."""
    monkeypatch.setattr(common.time, "sleep", lambda *_: None)
    monkeypatch.setattr(common, "OUTPUT_DIR", str(tmp_path))


# ---------------------------------------------------------------- the inbox

def test_sample_inbox_parses():
    emails = inbox._load_emails()
    assert len(emails) == 8
    assert emails[0]["subject"].startswith("Vendor contract")
    assert emails[0]["from"].startswith("Priya Shah")
    assert all(e["day"] for e in emails)


def test_latest_day_has_six_emails():
    day, picked = inbox.emails_for_day(inbox._load_emails(), "latest")
    assert day == "2026-11-26" and len(picked) == 6


def test_mcp_tools():
    listed = json.loads(inbox.list_emails("latest"))
    assert listed["count"] == 6 and listed["emails"][0]["id"] == 1
    assert json.loads(inbox.get_first_email())["subject"].startswith("Vendor contract")
    assert json.loads(inbox.get_email(5))["from"].startswith("Anita Rao")
    assert "error" in json.loads(inbox.get_email(99))
    assert "error" in json.loads(inbox.list_emails("26-11-2026"))


@pytest.mark.parametrize("raw", [
    "2026-11-26 09:42", "Thu, Nov 26, 2026 at 9:14 AM", "Thu, 26 Nov 2026 09:14:00 +0530",
    "Thursday, November 26, 2026 6:20 PM", "26/11/2026",
])
def test_common_date_formats(raw):
    assert inbox._parse_date(raw) == "2026-11-26"


def test_quoted_reply_stays_one_email(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = tmp_path / "reply.pdf"
    c, y = canvas.Canvas(str(path), pagesize=A4), 800
    for line in ["From: Alice <a@x.example>", "Date: 2026-11-26 10:00", "Subject: Re: Budget", "Can you confirm?",
                 "-----Original Message-----", "From: Me <me@example.com>", "Sent: 2026-11-25 09:00", "Subject: Budget", "Draft."]:
        c.drawString(50, y, line)
        y -= 14
    c.save()
    assert len(inbox._load_emails(str(path))) == 1


# ---------------------------------------------------------------- bad input

def test_missing_pdf_is_a_clear_error():
    with pytest.raises(common.InboxError, match="not found"):
        common.load_inbox("nope.pdf")


@pytest.mark.parametrize("date, ok", [("latest", True), ("today", True), ("2026-11-26", True), ("26-11-2026", False)])
def test_date_check(date, ok):
    if ok:
        common.check_date(date)
    else:
        with pytest.raises(common.InboxError):
            common.check_date(date)


def test_empty_day_skips_the_agents():
    import part3_categorize_today as part3
    import part4_reader_to_writer as part4

    # A day with no emails returns straight away; reaching the agents would need Groq.
    assert part3.run(date="2026-01-01").triage.emails == []
    assert part4.run(date="2026-01-01").drafts == []


def test_cli_missing_pdf_exits_cleanly():
    result = subprocess.run(
        [sys.executable, "-W", "ignore", "part2_reply_first_email.py", "--pdf", "nope.pdf"],
        cwd=HERE, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 1
    assert "Inbox PDF not found" in result.stderr


# ---------------------------------------------------------------- the Reader check

def _triage(*ids, category="no_action"):
    return T.InboxTriage(day="?", emails=[T.EmailTriage(id=i, sender="model", subject="model", category=category, reason="r") for i in ids])


def test_triage_check_drops_duplicates_and_made_up_ids():
    t = _triage(1, 1, 99)
    missing = T.complete_triage(None, t, [{"id": 1, "from": "A <a@x>", "subject": "S"}], "2026-11-26")
    assert missing == [] and [e.id for e in t.emails] == [1]
    assert t.emails[0].sender == "A <a@x>" and t.day == "2026-11-26"  # from the inbox, not the model


def test_triage_check_asks_again_for_skipped_emails(monkeypatch):
    class FakeCrew:
        def __init__(self, **_): pass
        def kickoff(self):
            class Result: pydantic = _triage(2)
            return Result()

    monkeypatch.setattr(T, "Crew", FakeCrew)
    t = _triage(1)
    expected = [{"id": 1, "from": "A", "subject": "S1"}, {"id": 2, "from": "B", "subject": "S2"}]
    assert T.complete_triage(None, t, expected, "d") == [2]
    assert [e.id for e in t.emails] == [1, 2]


# ---------------------------------------------------------------- Groq fixes

def test_groq_request_fixes(monkeypatch):
    params = {
        "messages": [{"role": "system", "content": "x", "cache_breakpoint": True}],
        "tools": [{"type": "function", "function": {"name": "t", "parameters": {"type": "object", "properties": {}, "required": []}}}],
    }
    monkeypatch.setattr(common, "_orig_prepare_completion_params", lambda *a, **k: params)
    out = common._prepare_completion_params_for_groq(None)
    assert "cache_breakpoint" not in out["messages"][0]
    assert "required" not in out["tools"][0]["function"]["parameters"]


def _groq_error(cls, msg):
    return cls(message=msg, llm_provider="groq", model="m")


def _call_with(monkeypatch, errors):
    queue = list(errors)

    def fake_completion(*_, **__):
        if queue:
            raise queue.pop(0)
        return "OK"

    monkeypatch.setattr(common, "_orig_completion", fake_completion)
    return common._completion_waiting_on_rate_limits()


def test_retries_rate_limits_server_errors_and_bad_output(monkeypatch):
    rate = _groq_error(litellm.RateLimitError, "tokens per minute (TPM). Please try again in 1.2s")
    bad = _groq_error(litellm.BadRequestError, "output_parse_failed")
    down = _groq_error(litellm.ServiceUnavailableError, "503 over capacity")
    # Each kind of error has its own retry limit, so mixing them still succeeds.
    assert _call_with(monkeypatch, [rate, rate, bad, down, bad]) == "OK"


def test_does_not_retry_real_errors(monkeypatch):
    with pytest.raises(litellm.BadRequestError):
        _call_with(monkeypatch, [_groq_error(litellm.BadRequestError, "invalid model")])
    with pytest.raises(litellm.RateLimitError):
        _call_with(monkeypatch, [_groq_error(litellm.RateLimitError, "tokens per day (TPD)")])

"""
Shared pieces for all 4 parts: the LLM, the two agents, and the MCP inbox server.

Session 3 ideas reused here:
  - narrow agent roles (Reader vs Writer), like Research -> Write -> Review
  - scoped handoffs via Task(context=[...]) — the Writer only sees the Reader's output
Session 4 ideas reused here:
  - the inbox lives behind an MCP server (inbox_mcp_server.py) started over stdio;
    the agents only ever see its tools, never the PDF itself
"""

import os
import re
import sys
import time

import litellm
from dotenv import load_dotenv
from crewai import Agent, LLM
from crewai.mcp import MCPServerStdio
from crewai.mcp.tool_resolver import MCPToolResolver

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

MODEL = os.getenv("GROQ_MODEL", "groq/openai/gpt-oss-20b")
MY_NAME = os.getenv("MY_NAME", "[Your Name]")
OUTPUT_DIR = os.path.join(HERE, "output")

# --- Groq fixes, applied to every request right before it's sent -------------
# 1. (Same patch as Session 3's demo2.) crewai tags messages with an internal
#    'cache_breakpoint' marker that Groq rejects: "property 'cache_breakpoint'
#    is unsupported". Strip it.
# 2. For MCP tools with no arguments (get_first_email, inbox_overview), crewai
#    sends {"properties": {}, "required": []}. The empty "properties" gets
#    dropped on the way to Groq, which then rejects the whole request:
#    "'required' present but 'properties' is missing". Drop the empty
#    "required" too.
_orig_prepare_completion_params = LLM._prepare_completion_params


def _prepare_completion_params_for_groq(self, *args, **kwargs):
    params = _orig_prepare_completion_params(self, *args, **kwargs)
    for message in params.get("messages", []):
        if isinstance(message, dict):
            message.pop("cache_breakpoint", None)
    for tool in params.get("tools") or []:
        fn = tool.get("function", {}) if isinstance(tool, dict) else {}
        schema = fn.get("parameters")
        if isinstance(schema, dict) or schema is None:
            schema = schema or {}
            schema.setdefault("type", "object")
            schema.setdefault("properties", {})
            if not schema["properties"] and not schema.get("required"):
                schema.pop("required", None)
            fn["parameters"] = schema
    return params


LLM._prepare_completion_params = _prepare_completion_params_for_groq

# 3. Groq's free tier allows ~8k tokens per minute, and a Reader -> Writer run
#    goes over that. Groq's error says how long to wait ("try again in 7.5s"),
#    so wait that long and retry instead of crashing mid-run.
_orig_completion = litellm.completion


_FLAKY_GENERATION = ("output_parse_failed", "tool_use_failed")


def _completion_waiting_on_rate_limits(*args, **kwargs):
    for attempt in range(8):
        try:
            return _orig_completion(*args, **kwargs)
        except litellm.BadRequestError as e:
            # 4. gpt-oss on Groq sometimes produces output Groq can't parse
            #    ("output_parse_failed") or a malformed tool call. Retrying the
            #    same request usually works.
            if attempt >= 2 or not any(code in str(e) for code in _FLAKY_GENERATION):
                raise
            print("[retry] Groq couldn't parse the model's output — trying again...", file=sys.stderr)
            time.sleep(2)
        except litellm.RateLimitError as e:
            if attempt == 7 or "per day" in str(e):  # daily limits won't clear by waiting
                raise
            m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(e))
            wait = (int(m.group(1) or 0) * 60 + float(m.group(2)) if m else 10) + 1
            print(f"[rate limit] Groq asked us to wait {wait:.0f}s — waiting, then retrying...", file=sys.stderr)
            time.sleep(wait)


litellm.completion = _completion_waiting_on_rate_limits
# -----------------------------------------------------------------------------

# --- Short MCP tool names -----------------------------------------------------
# crewai names stdio MCP tools "<command>_<args>_<tool>" and cuts that to 64
# characters. With full paths (/Users/.../.venv/bin/python /Users/.../x.py)
# the real tool name is cut off, and a "python_..." prefix makes gpt-oss call
# its built-in "python" tool instead. Name stdio servers after their script,
# so tools come out as e.g. "inbox_mcp_server_get_email".
_orig_create_transport = MCPToolResolver._create_transport


def _create_transport_short_name(mcp_config):
    transport, server_name = _orig_create_transport(mcp_config)
    if isinstance(mcp_config, MCPServerStdio) and mcp_config.args:
        server_name = os.path.splitext(os.path.basename(mcp_config.args[-1]))[0]
    return transport, server_name


MCPToolResolver._create_transport = staticmethod(_create_transport_short_name)
# -----------------------------------------------------------------------------


def require_key() -> None:
    if not os.getenv("GROQ_API_KEY"):
        sys.exit("Set GROQ_API_KEY in .env (see .env.example) before running.")


def make_llm() -> LLM:
    # Rate limits are handled by the wait-and-retry wrapper above.
    return LLM(model=MODEL, temperature=0.2)


def inbox_server(pdf_path: str | None = None) -> MCPServerStdio:
    """How to launch the MCP inbox server (Session 4's stdio pattern)."""
    env = dict(os.environ)
    if pdf_path:
        env["INBOX_PDF"] = os.path.abspath(pdf_path)
    return MCPServerStdio(command=sys.executable, args=[os.path.join(HERE, "inbox_mcp_server.py")], env=env)


def make_writer(llm: LLM, mcps: list | None = None) -> Agent:
    return Agent(
        role="Email Reply Writer",
        goal="Write a clear, polite, ready-to-send reply to each email you're given",
        backstory=(
            f"You write email replies on behalf of {MY_NAME}. You answer every question "
            "and request in the email, match its tone, and keep replies short. You never "
            "invent facts, prices or commitments, and you never pick a time, date, yes/no "
            "decision or number on the user's behalf: when the reply needs something only "
            "the user knows or decides, you leave a placeholder like [pick Tue or Thu, time] "
            "or [approve 60-day terms? yes/no]. You never send anything — you only draft."
        ),
        llm=llm,
        mcps=mcps or [],
        verbose=True,
    )


def make_reader(llm: LLM, mcps: list) -> Agent:
    return Agent(
        role="Inbox Triage Reader",
        goal="Read the inbox and decide which emails need action from the user",
        backstory=(
            f"You triage email for {MY_NAME}. An email NEEDS ACTION if it asks "
            f"{MY_NAME} a direct question, requests a decision, approval, reply, "
            "document, payment or meeting, or has a deadline for them. Newsletters, "
            "promotions, automated notifications, receipts and FYI updates do NOT need "
            "action. You read emails only through your inbox tools and never guess "
            "at content you haven't read."
        ),
        llm=llm,
        mcps=mcps,
        verbose=True,
    )


def save_output(name: str, text: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    with open(path, "w") as f:
        f.write(text)
    return path

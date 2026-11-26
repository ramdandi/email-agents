"""
Generate sample_inbox.pdf — a fake inbox for testing (all people and companies are made up).

  python make_sample_inbox.py            # writes sample_inbox.pdf
  python make_sample_inbox.py my.pdf     # writes my.pdf

Newest email first, like a real inbox. Mix of emails that need action and
ones that don't, across two days, so Part 3's "today" filter has something to drop.
"""

import sys
import textwrap

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

EMAILS = [
    {
        "From": "Priya Shah <priya.shah@northwind-legal.example>",
        "Date": "2026-11-26 09:42",
        "Subject": "Vendor contract - need your sign-off by Friday",
        "body": (
            "Hi,\n\nI've finished redlining the Brightpath vendor contract. Two open points need your "
            "call: (1) are you OK with a 60-day payment term instead of 30, and (2) should we cap "
            "liability at 12 months of fees? Legal needs your sign-off by Friday 28 Nov so we can "
            "countersign before month end.\n\nThanks,\nPriya"
        ),
    },
    {
        "From": "The Weekly Byte <newsletter@weeklybyte.example>",
        "Date": "2026-11-26 08:30",
        "Subject": "This week: 7 AI agent frameworks compared",
        "body": (
            "Hello reader,\n\nIn this issue: we compare seven agent frameworks, look at MCP adoption, "
            "and share three prompts our readers loved. Read online at weeklybyte.example.\n\n"
            "You're receiving this because you subscribed. Unsubscribe anytime."
        ),
    },
    {
        "From": "Marcus Lee <marcus.lee@contoso.example>",
        "Date": "2026-11-26 08:05",
        "Subject": "Can we move Thursday's sync?",
        "body": (
            "Hey,\n\nSomething came up on my side for Thursday 2pm. Could we move our project sync to "
            "Friday morning instead - anytime between 10am and 12pm works for me. Let me know what "
            "suits you and I'll update the invite.\n\nCheers,\nMarcus"
        ),
    },
    {
        "From": "ShopFast Orders <no-reply@shopfast.example>",
        "Date": "2026-11-26 07:51",
        "Subject": "Your order #48213 has shipped",
        "body": (
            "Good news! Your order #48213 (USB-C hub, 1 item) has shipped and should arrive by "
            "Saturday. Track your parcel in the ShopFast app.\n\nThis is an automated message - "
            "please do not reply."
        ),
    },
    {
        "From": "Anita Rao <anita.rao@fabrikam.example>",
        "Date": "2026-11-26 07:10",
        "Subject": "Invoice INV-2291 question",
        "body": (
            "Hello,\n\nWe received invoice INV-2291 but the total (Rs 1,85,000) doesn't match the PO "
            "we raised (Rs 1,60,000). Could you confirm whether the extra Rs 25,000 is for the "
            "additional training day, and send a revised invoice if not? Our payment run is on "
            "Monday.\n\nRegards,\nAnita Rao\nAccounts Payable, Fabrikam"
        ),
    },
    {
        "From": "Team Updates <updates@company.example>",
        "Date": "2026-11-26 06:00",
        "Subject": "FYI: office closed on Monday for maintenance",
        "body": (
            "Hi all,\n\nJust a heads-up that the office will be closed on Monday for electrical "
            "maintenance. Please work from home that day. No action needed.\n\nFacilities Team"
        ),
    },
    {
        "From": "Dev Kapoor <dev.kapoor@company.example>",
        "Date": "2026-11-25 18:20",
        "Subject": "Slides for the Q4 review?",
        "body": (
            "Hi,\n\nCould you send me your 3 slides for the Q4 review by Wednesday? Just the "
            "highlights, risks and next-quarter plan.\n\nThanks,\nDev"
        ),
    },
    {
        "From": "CloudBox <billing@cloudbox.example>",
        "Date": "2026-11-25 10:00",
        "Subject": "Your November receipt",
        "body": "Thanks for your payment of $9.99 for CloudBox Plus (November). No action is required.",
    },
]


def build(path: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    left, top, bottom, line_h = 50, height - 50, 50, 14
    y = top

    def line(text: str, font: str = "Helvetica", size: int = 10) -> None:
        nonlocal y
        if y < bottom:
            c.showPage()
            y = top
        c.setFont(font, size)
        c.drawString(left, y, text)
        y -= line_h

    for email in EMAILS:
        line(f"From: {email['From']}", "Helvetica-Bold")
        line("To: me@example.com")
        line(f"Date: {email['Date']}")
        line(f"Subject: {email['Subject']}", "Helvetica-Bold")
        line("")
        for para in email["body"].split("\n"):
            for wrapped in textwrap.wrap(para, 95) or [""]:
                line(wrapped)
        line("")
        line("")
    c.save()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sample_inbox.pdf"
    build(out)
    print(f"Wrote {out} with {len(EMAILS)} emails")

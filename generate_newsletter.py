#!/usr/bin/env python3
"""
TheShareGame Weekly Newsletter Generator
==========================================
Runs on a schedule via GitHub Actions (see .github/workflows/weekly-newsletter.yml).
No server, no Oracle, no cost — GitHub's free scheduler triggers this, it calls
the Gemini free tier for copy, then Brevo's API to create + send the campaign.

Env vars required (set as GitHub repo Secrets, never hardcoded):
  GEMINI_API_KEY   - from aistudio.google.com, no billing attached
  BREVO_API_KEY    - from Brevo dashboard, Settings > SMTP & API > API Keys
  BREVO_LIST_ID    - the numeric ID of your subscriber list in Brevo
  ADMIN_ALERT_EMAIL (optional) - your own email, gets a warning if something fails

WEEKLY DATA:
Gemini has no idea what happened in TheShareGame this week — it can only
write from what you give it. Edit weekly_data.txt in this repo before Monday
with a few bullet points (top movers, new companies, market news) and this
script will feed that in as source material.
"""

import os
import sys
import json
import requests
from datetime import datetime

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_LIST_ID = int(os.environ.get("BREVO_LIST_ID", "0"))
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "TheShareGame")
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "")  # must be a verified sender in Brevo

ADMIN_ALERT_EMAIL = os.environ.get("ADMIN_ALERT_EMAIL", "")

WEEKLY_DATA_FILE = os.environ.get("WEEKLY_DATA_FILE", "weekly_data.txt")


# ─────────────────────────────────────────────────────────────
# STEP 1 — Generate this week's copy with Gemini
# ─────────────────────────────────────────────────────────────
def load_weekly_data() -> str:
    if not os.path.exists(WEEKLY_DATA_FILE):
        return "(No weekly data file found — write general TheShareGame commentary this week.)"
    with open(WEEKLY_DATA_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def build_prompt(week_data: str, week_label: str) -> str:
    return f"""You are writing the weekly email newsletter for TheShareGame, an online
game where players run and invest in their own virtual companies.

Write the newsletter for the week of {week_label}, using the following raw
notes about what happened this week:

---
{week_data}
---

Requirements:
- Friendly but sharp, business/markets tone (players are running companies).
- Structure: a short intro line, then 3-5 short sections with bold headers
  (e.g. "Top Movers", "New Companies", "Market News", "Tip of the Week").
- Keep total length under ~350 words.
- Output PLAIN TEXT only, no HTML, no markdown symbols like ** or #.
  Use simple line breaks and short header lines instead.
- Do not invent specific numbers or company names that weren't given to you
  in the notes above — if the notes are thin, keep that section short or
  general rather than making up data.
"""


def call_gemini(prompt: str) -> tuple[bool, str]:
    if not GEMINI_API_KEY:
        return False, "GEMINI_API_KEY is not set."

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        resp = requests.post(url, json=payload, timeout=60)
    except requests.RequestException as e:
        return False, f"Network error calling Gemini: {e}"

    if resp.status_code == 429:
        return False, (
            "QUOTA_EXCEEDED: Gemini free-tier limit hit. No charge occurred "
            "(no billing enabled on this project) — the request was simply "
            "rejected. Try again later or tomorrow."
        )
    if resp.status_code != 200:
        return False, f"Gemini API error {resp.status_code}: {resp.text[:500]}"

    try:
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return True, text.strip()
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return False, f"Unexpected Gemini response shape: {e} — raw: {resp.text[:500]}"


# ─────────────────────────────────────────────────────────────
# STEP 2 — Wrap the copy in TheShareGame's black/gold HTML theme
# ─────────────────────────────────────────────────────────────
def render_html(body_text: str, week_label: str) -> str:
    lines = [l.rstrip() for l in body_text.split("\n")]
    html_parts = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        looks_like_header = (
            len(stripped) < 40
            and not stripped.endswith(".")
            and (stripped.istitle() or stripped.isupper())
        )
        if looks_like_header:
            html_parts.append(f'<h2 class="nl-h2">{stripped}</h2>')
        else:
            html_parts.append(f'<p class="nl-p">{stripped}</p>')
    body_html = "\n".join(html_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body {{
    background:#0a0a0a; margin:0; padding:0;
    font-family: 'Didact Gothic', Helvetica, Arial, sans-serif;
  }}
  .nl-wrap {{ max-width:640px; margin:0 auto; background:#111111; }}
  .nl-header {{
    padding:40px 40px 24px; text-align:center;
    border-bottom:1px solid rgba(255,255,255,0.08);
  }}
  .nl-est {{
    font-family: Georgia, serif; font-size:10px; letter-spacing:0.3em;
    color:#c9a96e; text-transform:uppercase; margin-bottom:6px;
  }}
  .nl-logo {{
    font-family: Georgia, serif; font-size:16px; letter-spacing:0.15em;
    color:#f5f3ef; text-transform:uppercase;
  }}
  .nl-week {{
    font-family: Georgia, serif; font-size:11px; letter-spacing:0.2em;
    color:rgba(245,243,239,0.5); margin-top:14px; text-transform:uppercase;
  }}
  .nl-body {{ padding:36px 40px 8px; }}
  .nl-h2 {{
    font-family: Georgia, serif; font-weight:400; font-style:italic;
    font-size:20px; color:#e2c99a; margin:28px 0 10px;
  }}
  .nl-p {{
    font-size:14px; line-height:1.8; color:rgba(245,243,239,0.75);
    margin:0 0 14px;
  }}
  .nl-cta {{ text-align:center; padding:24px 40px 40px; }}
  .nl-btn {{
    display:inline-block; font-family:Georgia, serif; font-size:11px;
    letter-spacing:0.2em; text-transform:uppercase; color:#0a0a0a;
    background:#c9a96e; padding:14px 30px; text-decoration:none;
  }}
  .nl-footer {{
    padding:24px 40px 40px; text-align:center;
    border-top:1px solid rgba(255,255,255,0.08);
  }}
  .nl-foot-text {{ font-size:10px; letter-spacing:0.05em; color:rgba(255,255,255,0.3); }}
</style>
</head>
<body>
  <div class="nl-wrap">
    <div class="nl-header">
      <div class="nl-est">TheShareGame</div>
      <div class="nl-logo">Weekly Markets Newsletter</div>
      <div class="nl-week">{week_label}</div>
    </div>
    <div class="nl-body">
      {body_html}
    </div>
    <div class="nl-cta">
      <a class="nl-btn" href="https://www.thesharegame.com">Open TheShareGame</a>
    </div>
    <div class="nl-footer">
      <div class="nl-foot-text">You're receiving this because you subscribed on TheShareGame. Unsubscribe anytime via the link below.</div>
      {{{{ unsubscribe }}}}
    </div>
  </div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
# STEP 3 — Push to Brevo (create campaign + send)
# ─────────────────────────────────────────────────────────────
def send_via_brevo(subject: str, html: str) -> tuple[bool, str]:
    if not BREVO_API_KEY:
        return False, "BREVO_API_KEY is not set."
    if not BREVO_SENDER_EMAIL:
        return False, "BREVO_SENDER_EMAIL is not set (must be a verified sender in Brevo)."
    if not BREVO_LIST_ID:
        return False, "BREVO_LIST_ID is not set."

    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    create_resp = requests.post(
        "https://api.brevo.com/v3/emailCampaigns",
        headers=headers,
        json={
            "name": subject,
            "subject": subject,
            "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
            "htmlContent": html,
            "recipients": {"listIds": [BREVO_LIST_ID]},
        },
        timeout=30,
    )
    if create_resp.status_code not in (200, 201):
        return False, f"Brevo campaign creation failed: {create_resp.status_code} {create_resp.text[:300]}"

    campaign_id = create_resp.json().get("id")
    if not campaign_id:
        return False, f"Brevo did not return a campaign id: {create_resp.text[:300]}"

    send_resp = requests.post(
        f"https://api.brevo.com/v3/emailCampaigns/{campaign_id}/sendNow",
        headers=headers,
        timeout=30,
    )
    if send_resp.status_code not in (200, 201, 204):
        return False, f"Brevo send failed: {send_resp.status_code} {send_resp.text[:300]}"

    return True, f"Campaign {campaign_id} sent via Brevo."


def alert_admin(message: str):
    """Best-effort plain warning email to you via Brevo's transactional
    endpoint, so a Gemini quota hit or Brevo error doesn't vanish silently."""
    if not ADMIN_ALERT_EMAIL or not BREVO_API_KEY or not BREVO_SENDER_EMAIL:
        print(f"[ALERT - admin email/keys not fully configured] {message}")
        return
    try:
        requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            json={
                "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
                "to": [{"email": ADMIN_ALERT_EMAIL}],
                "subject": "Newsletter automation alert",
                "htmlContent": f"<p>{message}</p>",
            },
            timeout=15,
        )
    except requests.RequestException:
        print(f"[ALERT - failed to send, printing instead] {message}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    week_label = datetime.now().strftime("Week of %B %d, %Y")
    weekly_data = load_weekly_data()

    prompt = build_prompt(weekly_data, week_label)
    ok, result = call_gemini(prompt)

    if not ok:
        alert_admin(f"Newsletter generation FAILED this week ({week_label}): {result}")
        print(f"ERROR: {result}", file=sys.stderr)
        sys.exit(1)

    html = render_html(result, week_label)
    subject = f"TheShareGame — {week_label}"

    sent_ok, send_msg = send_via_brevo(subject, html)
    if not sent_ok:
        alert_admin(f"Newsletter WRITTEN but Brevo send FAILED ({week_label}): {send_msg}")
        print(f"ERROR: {send_msg}", file=sys.stderr)
        sys.exit(1)

    print(f"Success: {send_msg}")


if __name__ == "__main__":
    main()

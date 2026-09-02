#!/usr/bin/env python3
"""
TheShareGame Weekly Newsletter Generator (Kit edition)
========================================================
Runs on a schedule via GitHub Actions (see .github/workflows/weekly-newsletter.yml).
No server, no cost — GitHub's free scheduler triggers this, it calls the
Gemini free tier for copy, then Kit's v4 API to create + send a broadcast
to your whole subscriber list with a single call.

Env vars required (set as GitHub repo Secrets, never hardcoded):
  GEMINI_API_KEY   - from aistudio.google.com, no billing attached
  KIT_API_KEY      - from Kit dashboard > Settings > Developer / API
  ADMIN_ALERT_EMAIL (optional) - not used for sending here since Kit has no
                     simple transactional single-send endpoint on free plan;
                     failures are surfaced in the GitHub Actions run log/status
                     instead, which you'll see under the repo's Actions tab.

WEEKLY DATA:
Gemini has no idea what happened in TheShareGame this week — it can only
write from what you give it. Edit weekly_data.txt in this repo before Monday
with a few bullet points (top movers, new companies, market news) and this
script will feed that in as source material.
"""

import os
import sys
import json
from datetime import datetime, timezone
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

KIT_API_KEY = os.environ.get("KIT_API_KEY", "")

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

    # Kit's broadcast "content" field takes HTML for the body of the email;
    # Kit wraps it in its own email chrome (unsubscribe footer etc. are
    # handled automatically by Kit), so we only need to style the inner
    # content block itself here, inline-styled since many email clients
    # strip <style> blocks in injected HTML content.
    return f"""
<div style="background:#0a0a0a;padding:0;margin:0;font-family:Georgia, 'Cormorant Garamond', serif;">
  <div style="max-width:640px;margin:0 auto;background:#111111;">
    <div style="padding:40px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.08);">
      <div style="font-size:10px;letter-spacing:0.3em;color:#c9a96e;text-transform:uppercase;margin-bottom:6px;">TheShareGame</div>
      <div style="font-size:16px;letter-spacing:0.15em;color:#f5f3ef;text-transform:uppercase;">Weekly Markets Newsletter</div>
      <div style="font-size:11px;letter-spacing:0.2em;color:rgba(245,243,239,0.5);margin-top:14px;text-transform:uppercase;">{week_label}</div>
    </div>
    <div style="padding:36px 40px 8px;">
      {body_html}
    </div>
    <div style="text-align:center;padding:24px 40px 40px;">
      <a href="https://www.thesharegame.com" style="display:inline-block;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#0a0a0a;background:#c9a96e;padding:14px 30px;text-decoration:none;">Open TheShareGame</a>
    </div>
  </div>
</div>
""".replace(
        '<h2 class="nl-h2">',
        '<h2 style="font-weight:400;font-style:italic;font-size:20px;color:#e2c99a;margin:28px 0 10px;">',
    ).replace(
        '<p class="nl-p">',
        '<p style="font-size:14px;line-height:1.8;color:rgba(245,243,239,0.75);margin:0 0 14px;font-family:Arial, sans-serif;">',
    )


# ─────────────────────────────────────────────────────────────
# STEP 3 — Create and send the broadcast via Kit's v4 API
# ─────────────────────────────────────────────────────────────
def send_via_kit(subject: str, html: str) -> tuple[bool, str]:
    if not KIT_API_KEY:
        return False, "KIT_API_KEY is not set."

    headers = {
        "Content-Type": "application/json",
        "X-Kit-Api-Key": KIT_API_KEY,
    }

    # send_at set to "now" (UTC) sends immediately to all subscribers.
    # public=False keeps it as an email-only send, not posted to a public feed.
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    payload = {
        "subject": subject,
        "content": html,
        "description": subject,
        "public": False,
        "published_at": now_iso,
        "send_at": now_iso,
        "subscriber_filter": [
            {"all": [{"type": "all_subscribers"}], "any": None, "none": None}
        ],
    }

    resp = requests.post(
        "https://api.kit.com/v4/broadcasts",
        headers=headers,
        json=payload,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        return False, f"Kit broadcast creation failed: {resp.status_code} {resp.text[:500]}"

    data = resp.json()
    broadcast_id = data.get("broadcast", {}).get("id")
    return True, f"Broadcast {broadcast_id} created and scheduled to send now via Kit."


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    week_label = datetime.now().strftime("Week of %B %d, %Y")
    weekly_data = load_weekly_data()

    prompt = build_prompt(weekly_data, week_label)
    ok, result = call_gemini(prompt)

    if not ok:
        print(f"ERROR: {result}", file=sys.stderr)
        sys.exit(1)

    html = render_html(result, week_label)
    subject = f"TheShareGame — {week_label}"

    sent_ok, send_msg = send_via_kit(subject, html)
    if not sent_ok:
        print(f"ERROR: {send_msg}", file=sys.stderr)
        sys.exit(1)

    print(f"Success: {send_msg}")


if __name__ == "__main__":
    main()

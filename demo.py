"""
demo.py — Test all 3 email generation endpoints in one go
==========================================================
Run with:  py -3.13 demo.py
Make sure the server is running first:  py -3.13 -m backend.main

This script:
  1. Generates a fresh email (welcome / reengagement / custom)
  2. Rewrites it with stylistic suggestions
  3. Generates a follow-up based on an email outcome

Set SEND_TO_INBOX = True and fill in YOUR_EMAIL to receive real emails.
"""

import httpx
import json
import sys

BASE = "http://localhost:8000"

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
# Set to True to actually send emails to your inbox via SendGrid
SEND_TO_INBOX = False
YOUR_EMAIL    = "almanesque1129@gmail.com"

# Campaign type for the initial email:
# "welcome" | "reengagement" | "variant_test" | "custom"
CAMPAIGN_TYPE = "welcome"

# For custom campaigns -- ignored for other types
CUSTOM_INSTRUCTIONS = (
    "Write a Black Friday sale email with 30% off everything. "
    "Use urgency language and highlight that the offer expires in 48 hours."
)
# ──────────────────────────────────────────────────────────────────────────────


def pretty(label: str, data: dict):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)
    email = data.get("email", {})
    if isinstance(email, list):
        # variant_test returns a list
        for i, v in enumerate(email):
            print(f"\n  --- Variant {i+1} ---")
            print(f"  Subject : {v.get('subject_line', '')}")
            print(f"  Preview : {v.get('preview_text', '')}")
            meta = v.get("metadata", {})
            style = meta.get("stylistic_suggestions", {})
            if style:
                hooks = style.get("alternative_hooks", [])
                if hooks:
                    print(f"  Alt. subject lines:")
                    for h in hooks:
                        print(f"    * {h}")
    else:
        print(f"  Customer: {data.get('customer', {}).get('name', 'N/A')}")
        print(f"  Segment : {data.get('customer', {}).get('segment', 'N/A')}")
        print(f"  Subject : {email.get('subject_line', '')}")
        print(f"  Preview : {email.get('preview_text', '')}")
        body = email.get("body", {})
        print(f"\n  Greeting    : {body.get('greeting', '')}")
        opening = body.get('opening', '')
        print(f"  Opening     : {opening[:120]}{'...' if len(opening) > 120 else ''}")
        main = body.get('main_content', '')
        print(f"  Main (first 150 chars): {main[:150]}{'...' if len(main) > 150 else ''}")
        print(f"  CTA         : {body.get('call_to_action', '')}")
        print(f"  Closing     : {body.get('closing', '')}")
        meta = email.get("metadata", {})
        print(f"\n  Tone        : {meta.get('tone', '')}")
        print(f"  Send time   : {meta.get('recommended_send_time', '')}")
        print(f"  Open boost  : {meta.get('estimated_open_rate_boost', '')}")
        print(f"  Reasoning   : {meta.get('reasoning', '')}")
        style = meta.get("stylistic_suggestions", {})
        if style:
            print(f"\n  --- Writing Style Insights ---")
            print(f"  Figure of speech : {style.get('figure_of_speech_used', '')}")
            print(f"  Language changes : {style.get('parts_of_speech_adjustments', '')}")
            hooks = style.get("alternative_hooks", [])
            if hooks:
                print(f"  Alt. subject lines:")
                for h in hooks:
                    print(f"    * {h}")
    sent = data.get("sent", False)
    send_result = data.get("send_result")
    if send_result:
        if sent:
            print(f"\n  [SENT] Email delivered! Message ID: {send_result.get('message_id')}")
        else:
            note = send_result.get('note', send_result.get('error', ''))
            print(f"\n  [STUB] Not sent. {note}")
    print(f"\n  Generation time: {data.get('generation_time_ms', 0):.0f} ms")


def run():
    client = httpx.Client(timeout=90)

    print(f"\nConnecting to {BASE}...")
    try:
        r = client.get(f"{BASE}/")
        r.raise_for_status()
        info = r.json()
        print(f"Server: {info['status']} | Dataset: {info['dataset_records']} records")
    except Exception as e:
        print(f"ERROR: Cannot reach server at {BASE}. Is it running?\n  {e}")
        sys.exit(1)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 1: GENERATE EMAIL
    # ──────────────────────────────────────────────────────────────────────────
    print(f"\n[1/3] Generating {CAMPAIGN_TYPE.upper()} email...")

    payload: dict = {
        "campaign_type": CAMPAIGN_TYPE,
        "send": SEND_TO_INBOX,
        "to_override": YOUR_EMAIL if SEND_TO_INBOX else None,
    }

    if CAMPAIGN_TYPE == "custom":
        payload["user_instructions"] = CUSTOM_INSTRUCTIONS
    elif CAMPAIGN_TYPE == "variant_test":
        payload["num_variants"] = 5
        payload["base_campaign_type"] = "reengagement"

    r = client.post(f"{BASE}/api/email/generate", json=payload)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text}")
        sys.exit(1)

    generate_result = r.json()
    pretty("STEP 1: GENERATED EMAIL", generate_result)

    # Extract data for the next two steps
    customer_id = generate_result.get("customer", {}).get("id")
    generated_email = generate_result.get("email", {})
    if isinstance(generated_email, list):
        first_email = generated_email[0]
    else:
        first_email = generated_email

    subject_line = first_email.get("subject_line", "Your update")
    body = first_email.get("body", {})
    original_email_text = (
        f"Subject: {first_email.get('subject_line', '')}\n\n"
        f"{body.get('greeting', '')}\n\n"
        f"{body.get('opening', '')}\n\n"
        f"{body.get('main_content', '')}\n\n"
        f"CTA: {body.get('call_to_action', '')} => {body.get('cta_url', '')}\n\n"
        f"{body.get('closing', '')}"
    )

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 2: REWRITE THE EMAIL (with stylistic suggestions)
    # ──────────────────────────────────────────────────────────────────────────
    print(f"\n[2/3] Rewriting email with stylistic feedback...")

    rewrite_payload = {
        "customer_id": customer_id,
        "original_email": original_email_text,
        "feedback": (
            "Make the subject line shorter and punchier using alliteration. "
            "Replace all passive voice with active verbs. "
            "Add a metaphor comparing the product journey to a specific milestone. "
            "Trim the body to 150 words max. "
            "Make the CTA button text more action-oriented and urgent."
        ),
    }

    r = client.post(f"{BASE}/api/email/rewrite", json=rewrite_payload)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text}")
    else:
        rewrite_result = r.json()
        pretty("STEP 2: REWRITTEN EMAIL (with Style Insights)", rewrite_result)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 3: GENERATE FOLLOW-UP
    # ──────────────────────────────────────────────────────────────────────────
    print(f"\n[3/3] Generating follow-up (outcome: opened_no_click)...")

    followup_payload = {
        "customer_id": customer_id,
        "previous_email_subject": subject_line,
        "outcome": "opened_no_click",  # try: not_opened | clicked_no_convert | converted
        "send": SEND_TO_INBOX,
        "to_override": YOUR_EMAIL if SEND_TO_INBOX else None,
    }

    r = client.post(f"{BASE}/api/email/followup", json=followup_payload)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text}")
    else:
        followup_result = r.json()
        pretty("STEP 3: FOLLOW-UP EMAIL", followup_result)

    print(f"\n{'='*60}")
    print("  All 3 steps completed successfully!")
    if SEND_TO_INBOX:
        print(f"  Check your inbox: {YOUR_EMAIL}")
    else:
        print("  Set SEND_TO_INBOX = True in demo.py to receive real emails.")
    print('='*60)


if __name__ == "__main__":
    run()

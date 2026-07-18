"""
pages/1_✍️_Manual_Editor.py
Manual campaign composer — no AI, full control.
"""
import streamlit as st
from utils_shared import SHARED_CSS, render_sidebar, attachment_row, run_async, init_session

st.set_page_config(
    page_title="Manual Editor · Gemini Email AI",
    page_icon="✍️", layout="wide", initial_sidebar_state="expanded"
)
st.markdown(SHARED_CSS, unsafe_allow_html=True)
init_session()

cust, mode, be = render_sidebar()

# ── Backend check ─────────────────────────────────────────────────────────────
if not be["ok"]:
    st.error(f"⚠️ Backend unavailable: {be.get('error')}")
    st.markdown("""
    <div style="background:#fef3e2;border:1px solid #f0d9b5;border-radius:12px;padding:16px;margin-top:16px;">
      <strong>How to fix:</strong><br>
      1. Open a new terminal in <code>C:\\Users\\alman\\ai-email-agent</code><br>
      2. Run: <code>py -3.13 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload</code><br>
      3. Refresh this page.
    </div>""", unsafe_allow_html=True)
    st.stop()

compose_html = be["_compose_html_email"]
send_sg      = be["_send_via_sendgrid"]

# Helper to get template defaults
def get_template_defaults(tmpl_type: str, name: str, interests_list: list) -> dict:
    interests_str = ", ".join(interests_list[:3])
    if tmpl_type == "👋 Welcome":
        return {
            "subject_line": f"Welcome to the family, {name}!",
            "body": {
                "greeting": f"Hi {name},",
                "opening": "We're absolutely thrilled to have you join our community.",
                "main_content": (
                    f"Based on your interest in {interests_str}, we've put together "
                    "a curated set of premium benefits just for you. Explore what's waiting inside."
                    if interests_str else
                    "We've put together a curated set of premium benefits just for you. Explore what's waiting inside."
                ),
                "call_to_action": "Get Started Now →",
                "cta_url": "https://app.example.com/welcome",
                "closing": "Warmly,\nThe Team"
            },
            "attachments": []
        }
    elif tmpl_type == "📢 Newsletter":
        return {
            "subject_line": f"Gemini AI Newsletter: What's new this month, {name}?",
            "body": {
                "greeting": f"Hello {name},",
                "opening": "We're back with our monthly round-up of stories, updates, and insights.",
                "main_content": (
                    f"Since you are interested in {interests_str or 'technology'}, we wanted "
                    "to share our latest featured report detailing productivity gains and premium design systems."
                ),
                "call_to_action": "Read Featured Article →",
                "cta_url": "https://app.example.com/blog",
                "closing": "Cheers,\nThe Editors"
            },
            "attachments": []
        }
    elif tmpl_type == "⏰ Re-engagement":
        return {
            "subject_line": f"Long time no see, {name}! We miss you.",
            "body": {
                "greeting": f"Dear {name},",
                "opening": "It's been a while since we last connected, and we wanted to say hello.",
                "main_content": (
                    f"We noticed you haven't visited us recently. Since we know you enjoy {interests_str or 'high-quality updates'}, "
                    "we've prepared a special return bonus just for you."
                ),
                "call_to_action": "Claim 20% Return Code →",
                "cta_url": "https://app.example.com/reengage",
                "closing": "Best regards,\nThe Support Team"
            },
            "attachments": []
        }
    else:  # 🚀 Product Launch
        return {
            "subject_line": f"Introducing Gemini Email Studio: Build connections, {name}!",
            "body": {
                "greeting": f"Hi {name},",
                "opening": "We are incredibly excited to announce the launch of our brand new workspace.",
                "main_content": (
                    "Gemini Email Studio is a state-of-the-art campaign engine. "
                    f"We selected you because of your interest in {interests_str or 'premium software'}."
                ),
                "call_to_action": "Watch Launch Video →",
                "cta_url": "https://app.example.com/launch",
                "closing": "Excitedly,\nThe Product Team"
            },
            "attachments": []
        }

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="gemini-greeting" style="font-size:2rem;">
  ✍️ <span class="greeting-gradient">Manual Campaign Editor</span>
</div>
<div class="gemini-sub" style="font-size:.95rem;">
  Choose a template or write your own. Edit fields at the top, preview below, and add attachments.
</div>
""", unsafe_allow_html=True)

# ── Must have a customer ──────────────────────────────────────────────────────
if not cust:
    st.markdown("""
    <div style="background:#fef3e2;border:1px solid #f0d9b5;border-radius:14px;
    padding:20px;text-align:center;margin-top:20px;">
      <div style="font-size:2rem;">👈</div>
      <div style="font-weight:700;color:#78350f;font-size:16px;margin-top:8px;">
        Select a recipient from the sidebar</div>
      <div style="color:#92400e;font-size:13px;margin-top:6px;">
        Click any name in the <strong>Select Recipient</strong> section on the left.</div>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ── Recipient mini-card ───────────────────────────────────────────────────────
pills = "".join(f'<span class="pill-interest">{i}</span>' for i in cust.get("interests",[])[:5])
st.markdown(f"""
<div class="active-profile-card" style="margin-bottom:14px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <span style="font-size:.72rem;color:#64748b;font-weight:700;text-transform:uppercase;">
        ✅ Composing for</span>
      <div style="font-weight:700;color:#0f172a;font-size:16px;margin-top:2px;">
        {cust.get('name','—')}</div>
      <div style="color:#64748b;font-size:13px;">{cust.get('email','—')}</div>
    </div>
    <div>{pills}</div>
  </div>
</div>""", unsafe_allow_html=True)

# ── Template Selection ───────────────────────────────────────────────────────
st.markdown("#### 📋 1. Select Template Option")
tmpl_choice = st.radio(
    "Select Template Option",
    ["👋 Welcome", "📢 Newsletter", "⏰ Re-engagement", "🚀 Product Launch"],
    horizontal=True,
    key=f"me_tmpl_choice_{cust.get('id')}",
    label_visibility="collapsed"
)

# ── Per-customer draft state (persists while same customer is selected) ────────
ck = f"manual_draft_{cust.get('id','x')}"
prev_tmpl_key = f"prev_tmpl_{cust.get('id','x')}"

# If template choice changed or draft not initialized, update fields
if ck not in st.session_state or st.session_state.get(prev_tmpl_key) != tmpl_choice:
    st.session_state[prev_tmpl_key] = tmpl_choice
    st.session_state[ck] = get_template_defaults(
        tmpl_choice,
        cust.get('name', 'there'),
        cust.get('interests', [])
    )

draft = st.session_state[ck]
body  = draft["body"]

# =============================================================================
# 1. EDIT FIELDS SECTION (ABOVE)
# =============================================================================
st.markdown("---")
st.markdown("#### 📝 2. Edit Fields")

new_s  = st.text_input("✉️ Subject Line", value=draft["subject_line"], key="me_sub")

c_g, c_o = st.columns([1, 2])
with c_g:
    new_g  = st.text_input("👋 Greeting", value=body["greeting"], key="me_greet")
with c_o:
    new_o  = st.text_area("📖 Opening Paragraph", value=body["opening"], key="me_open", height=68)

new_m  = st.text_area("📄 Main Body Content", value=body["main_content"], key="me_main", height=100)

cc1, cc2, cc3 = st.columns([1, 1, 1])
with cc1:
    new_ct = st.text_input("🔘 CTA Button Text", value=body["call_to_action"], key="me_cta_t")
with cc2:
    new_cu = st.text_input("🌐 CTA URL Link", value=body["cta_url"], key="me_cta_u")
with cc3:
    new_cl = st.text_input("🖊️ Closing Sign-off", value=body["closing"].replace('\n', '  '), key="me_close")

# Save values back to session state
draft["subject_line"]         = new_s
draft["body"]["greeting"]     = new_g
draft["body"]["opening"]      = new_o
draft["body"]["main_content"] = new_m
draft["body"]["call_to_action"] = new_ct
draft["body"]["cta_url"]      = new_cu
# restore newlines if closed with spaces
draft["body"]["closing"]      = new_cl.replace('  ', '\n')
st.session_state[ck]          = draft

# =============================================================================
# 2. LIVE PREVIEW SECTION (MIDDLE)
# =============================================================================
st.markdown("---")
st.markdown("#### 🎨 3. Live Preview")
st.markdown(
    f"""<div style="background:#f1f5f9;border-radius:10px;padding:8px 14px;
    font-size:13px;margin-bottom:10px;color:#475569;">
    <strong>Subject:</strong> {draft['subject_line']}</div>""",
    unsafe_allow_html=True)

try:
    html_out = compose_html(draft, cust)
    tab_v, tab_c = st.tabs(["🎨 Visual", "📄 Raw HTML"])
    with tab_v:
        st.components.v1.html(html_out, height=480, scrolling=True)
    with tab_c:
        st.code(html_out, language="html")
except Exception as e:
    st.error(f"Preview error: {e}")
    html_out = "<p>Preview unavailable</p>"

# =============================================================================
# 3. ATTACHMENTS SECTION (BELOW LIVE PREVIEW)
# =============================================================================
st.markdown("---")
atts = attachment_row("me")
draft["attachments"] = atts
st.session_state[ck] = draft

# Re-compile html if attachments changed
html_out = compose_html(draft, cust)

# =============================================================================
# 4. SEND & DOWNLOAD SECTION (BOTTOM)
# =============================================================================
st.markdown("---")
st.markdown("#### 🛫 4. Send or Download")

col_addr, _ = st.columns([2, 1])
ov_email = col_addr.text_input(
    "📧 Override Recipient Address (Live Send)", value=st.session_state["override_email"], key="me_ov")
st.session_state["override_email"] = ov_email

b_send, b_dl = st.columns(2)
with b_send:
    if st.button("🚀 Send Now", use_container_width=True, key="me_send"):
        with st.spinner("Sending email…"):
            try:
                res = run_async(send_sg(cust, draft, to_override=ov_email))
                if res and res.get("success"):
                    st.session_state["delivery_status_type"] = "success"
                    st.session_state["delivery_status"] = (
                        f"✅ Stub mode — email logged (not actually sent): {res.get('note','')}"
                        if res.get("stub_mode") else
                        f"🚀 Sent live to {ov_email} · Message ID: {res.get('message_id','?')}"
                    )
                else:
                    st.session_state["delivery_status_type"] = "error"
                    st.session_state["delivery_status"] = f"❌ Send failed: {(res or {}).get('error','unknown error')}"
            except Exception as e:
                st.session_state["delivery_status_type"] = "error"
                st.session_state["delivery_status"] = f"❌ Exception: {e}"
        st.rerun()

with b_dl:
    st.download_button(
        "📥 Download HTML File", data=html_out,
        file_name=f"manual_{cust.get('name','email').replace(' ','_')}.html",
        mime="text/html", use_container_width=True, key="me_dl")

# ── Status banner ──
if st.session_state.get("delivery_status"):
    if st.session_state["delivery_status_type"] == "success":
        st.markdown(
            f"""<div style="background-color:#f0fdf4;border:2px solid #16a34a;border-radius:12px;
            padding:14px 18px;color:#15803d;font-weight:700;font-size:14px;margin-top:14px;
            box-shadow:0 4px 12px rgba(22,163,74,0.08);display:flex;align-items:center;gap:10px;">
              <span style="font-size:1.2rem;">🚀</span>
              <div>{st.session_state["delivery_status"]}</div>
            </div>""",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"""<div style="background-color:#fef2f2;border:2px solid #dc2626;border-radius:12px;
            padding:14px 18px;color:#991b1b;font-weight:700;font-size:14px;margin-top:14px;
            box-shadow:0 4px 12px rgba(220,38,38,0.08);display:flex;align-items:center;gap:10px;">
              <span style="font-size:1.2rem;">❌</span>
              <div>{st.session_state["delivery_status"]}</div>
            </div>""",
            unsafe_allow_html=True
        )

"""
streamlit_app.py  —  Home / Walkthrough landing page
"""
import streamlit as st
from utils_shared import SHARED_CSS, render_sidebar, init_session, fetch_customers

st.set_page_config(
    page_title="Gemini Email AI",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.markdown(SHARED_CSS, unsafe_allow_html=True)

init_session()
cust, mode, be = render_sidebar()

# ── Hero ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="gemini-greeting">
  Hi Composer 👋<br>
  <span class="greeting-gradient">what connection shall we build today?</span>
</div>
<div class="gemini-sub">
  A powerful AI email studio — craft campaigns manually or let Gemini write, refine,
  and personalise them automatically. Select a customer, pick a page, and hit Generate.
</div>
""", unsafe_allow_html=True)

# ── Active recipient card ─────────────────────────────────────────────────────
if cust:
    pills = "".join(f'<span class="pill-interest">{i}</span>' for i in cust.get("interests",[]))
    purchases = ", ".join(
        f"{p.get('item')} (${p.get('amount')})" for p in cust.get("purchase_history",[])
    )
    seg = cust.get("segment","active")
    seg_colors = {
        "vip":        ("#b45309","rgba(180,83,9,0.1)","rgba(180,83,9,0.3)"),
        "active":     ("#16a34a","rgba(22,163,74,0.1)","rgba(22,163,74,0.3)"),
        "inactive":   ("#64748b","rgba(100,116,139,0.1)","rgba(100,116,139,0.3)"),
        "churn_risk": ("#dc2626","rgba(220,38,38,0.1)","rgba(220,38,38,0.3)"),
        "new":        ("#2563eb","rgba(37,99,235,0.1)","rgba(37,99,235,0.3)"),
    }
    sc, sbg, sbd = seg_colors.get(seg.lower(), ("#475569","rgba(71,85,105,0.1)","rgba(71,85,105,0.3)"))
    eb = cust.get("email_behavior") or {}
    send_time = eb.get("preferred_send_time", "anytime")
    st.markdown(f"""
    <div class="active-profile-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
        <div>
          <span style="font-size:.72rem;color:#64748b;font-weight:700;text-transform:uppercase;
          letter-spacing:1px;">✅ Active Recipient</span>
          <h3 style="margin:4px 0 2px 0;color:#0f172a;font-weight:700;font-size:1.25rem;">
            {cust.get('name','—')}
          </h3>
          <div style="color:#64748b;font-size:13px;">
            📧 {cust.get('email','—')} &nbsp;·&nbsp;
            🕐 Best time: {send_time}
          </div>
        </div>
        <span style="display:inline-block;padding:4px 12px;border-radius:9999px;font-size:12px;
        font-weight:700;text-transform:uppercase;background:{sbg};color:{sc};border:1px solid {sbd};">
          {seg}
        </span>
      </div>
      <div style="margin-bottom:8px;">{pills}</div>
      <div style="font-size:12px;color:#64748b;">
        🛒 <strong>Recent purchases:</strong> {purchases or "None on record"}
      </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("👈 Select a customer from the sidebar to get started.")

# ── Feature cards ─────────────────────────────────────────────────────────────
st.markdown("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("""
    <div class="suggestion-card">
      <div>
        <div class="suggestion-title">✍️ Manual Editor</div>
        <div class="suggestion-desc">Write every field yourself — subject, greeting, body,
        CTA, and attachments. Instant live HTML preview on the right.</div>
      </div>
      <div style="margin-top:12px;font-size:12px;color:#b45309;font-weight:600;margin-bottom:8px;">
        → Use for: Custom one-off campaigns
      </div>
    </div>""", unsafe_allow_html=True)
    if st.button("✍️ Open Manual Editor", use_container_width=True, key="go_manual"):
        st.switch_page("pages/1_✍️_Manual_Editor.py")

with c2:
    st.markdown("""
    <div class="suggestion-card">
      <div>
        <div class="suggestion-title">🌌 AI Draft Generator</div>
        <div class="suggestion-desc">Pick a campaign type and let Gemini write a personalised
        draft. Refine with plain-English instructions, generate A/B variants, and send.</div>
      </div>
      <div style="margin-top:12px;font-size:12px;color:#b45309;font-weight:600;margin-bottom:8px;">
        → Use for: Fast personalised outreach
      </div>
    </div>""", unsafe_allow_html=True)
    if st.button("🌌 Open AI Generator", use_container_width=True, key="go_ai"):
        st.switch_page("pages/2_🌌_AI_Draft.py")

with c3:
    st.markdown("""
    <div class="suggestion-card">
      <div>
        <div class="suggestion-title">🔁 Follow-up Sequences</div>
        <div class="suggestion-desc">After generating a campaign, scroll to the follow-up
        section on the AI Draft page. Choose what the customer did and get a smart reply.</div>
      </div>
      <div style="margin-top:12px;font-size:12px;color:#b45309;font-weight:600;margin-bottom:8px;">
        → Use for: Re-engagement & nurture
      </div>
    </div>""", unsafe_allow_html=True)
    if st.button("🔁 Go to Follow-up", use_container_width=True, key="go_follow"):
        st.switch_page("pages/2_🌌_AI_Draft.py")

# ── Full Walkthrough ──────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<h2 style="font-size:1.5rem;font-weight:800;color:#0f172a;margin-bottom:4px;">
  📖 How to Use This App
</h2>
<p style="color:#475569;font-size:14px;margin-bottom:18px;">
  Follow these steps to send your first personalised campaign in under 2 minutes.
</p>
""", unsafe_allow_html=True)

steps = [
    ("1", "🎯", "Select a Recipient",
     "In the sidebar, find the <strong>Select Recipient</strong> section. "
     "Use the search box to filter by name or email. Click any name — it turns amber/gold "
     "to confirm selection. The recipient's profile appears above on this page."),

    ("2", "🗂️", "Choose a Workflow",
     "Click <strong>✍️ Manual Editor</strong> or <strong>🌌 AI Draft</strong> in the top "
     "navigation of the sidebar. These are the two pill-shaped amber buttons at the very top."),

    ("3a", "✍️", "Manual Editor — Fill in the Fields",
     "On the Manual Editor page, edit the <em>Subject Line, Greeting, Opening, Body, CTA Button/URL, "
     "and Closing</em> in the left panel. The right panel shows a live HTML preview that updates "
     "as you type. No AI needed — you have full control."),

    ("3b", "🌌", "AI Draft — Pick a Type & Generate",
     "On the AI Draft page, click one of the four <strong>Quick Template</strong> buttons "
     "(Welcome, Newsletter, Re-engagement, Product Launch) <em>or</em> choose a type from the "
     "dropdown and add custom instructions. Then press <strong>🌌 Generate Campaign</strong>."),

    ("4", "📎", "Add Attachments",
     "Both pages show <strong>5 coloured attachment cards</strong>: "
     "🔴 PDF Brochure, 🟣 Demo Video, 🟢 Image Card, 🔵 Web Link, 🟡 Calendar Invite. "
     "Click the checkbox under each card to toggle it on/off. Selected cards turn brighter "
     "with a ✅ tick. These attachments are embedded in the email HTML."),

    ("5", "✏️", "Refine (AI Draft only)",
     "After generating, you can edit any field directly in the right panel. "
     "Or use the <strong>💬 AI Rewrite</strong> box — type plain-English feedback like "
     "<em>'make it shorter and add urgency'</em> and press Apply. The draft updates instantly."),

    ("6", "🔁", "Add a Follow-up (AI Draft only)",
     "Scroll to the bottom of the AI Draft page. Choose what the customer did "
     "(opened, clicked, ignored, converted) and press <strong>🔁 Draft Follow-up</strong>. "
     "A smart follow-up email is generated matching the context."),

    ("7", "🚀", "Send or Download",
     "Enter the recipient email address in the field at the bottom. "
     "Click <strong>🚀 Send Now</strong> to deliver (stub mode logs, live mode sends via SendGrid). "
     "Or click <strong>📥 Download HTML</strong> to save the email file."),
]

for num, icon, title, desc in steps:
    st.markdown(f"""
    <div class="step-card">
      <div class="step-num">{num}</div>
      <div class="step-body">
        <h4>{icon} {title}</h4>
        <p>{desc}</p>
      </div>
    </div>""", unsafe_allow_html=True)

st.markdown("""
<div style="margin-top:20px;padding:16px 20px;background:linear-gradient(135deg,
  rgba(180,83,9,0.06),rgba(217,119,6,0.04));border:1px solid rgba(180,83,9,0.2);
  border-radius:14px;font-size:13px;color:#78350f;font-weight:500;line-height:1.6;">
  💡 <strong>Pro Tip:</strong> Your session is persistent — switching between Manual Editor
  and AI Draft pages does <em>not</em> clear your selected customer or generated drafts.
  Use <strong>➕ New Campaign</strong> in the sidebar to start fresh.
</div>
""", unsafe_allow_html=True)

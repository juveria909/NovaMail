"""
pages/2_🌌_AI_Draft.py
AI campaign generator + follow-up sequences.
"""
import streamlit as st
import json
import requests
from utils_shared import (
    SHARED_CSS, render_sidebar, attachment_row, run_async,
    init_session, BACKEND_URL
)

st.set_page_config(
    page_title="AI Draft · Gemini Email AI",
    page_icon="🌌", layout="wide", initial_sidebar_state="expanded"
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
      1. Open a terminal in <code>C:\\Users\\alman\\ai-email-agent</code><br>
      2. Run: <code>py -3.13 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload</code><br>
      3. Refresh this page.
    </div>""", unsafe_allow_html=True)
    st.stop()

gen_campaign = be["generate_campaign_email"]
gen_followup = be["generate_followup_email"]
gen_rewrite  = be["generate_rewrite"]
gen_custom   = be["generate_custom_campaign"]
gen_ab       = be["generate_ab_variants"]
compose_html = be["_compose_html_email"]
send_sg      = be["_send_via_sendgrid"]

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="gemini-greeting" style="font-size:2rem;">
  🌌 <span class="greeting-gradient">AI Campaign Generator</span>
</div>
<div class="gemini-sub" style="font-size:.95rem;">
  Pick a template or describe your campaign. Gemini writes a personalised draft.
  Edit inline, rewrite with plain English, then send or follow up.
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
        Click any name in the <strong>Select Recipient</strong> section.</div>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ── Recipient card ────────────────────────────────────────────────────────────
_eb = cust.get("email_behavior") or {}
_send_time = _eb.get("preferred_send_time", "anytime")
pills = "".join(f'<span class="pill-interest">{i}</span>' for i in cust.get("interests",[])[:6])
st.markdown(f"""
<div class="active-profile-card">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
    <div>
      <span style="font-size:.72rem;color:#64748b;font-weight:700;text-transform:uppercase;">
        ✅ Active Recipient</span>
      <div style="font-weight:700;color:#0f172a;font-size:16px;margin-top:2px;">
        {cust.get('name','—')}</div>
      <div style="color:#64748b;font-size:13px;">
        📧 {cust.get('email','—')} &nbsp;·&nbsp;
        🕐 {_send_time}
      </div>
    </div>
    <span style="display:inline-block;padding:4px 12px;border-radius:9999px;font-size:12px;
    font-weight:700;background:rgba(37,99,235,.1);color:#2563eb;border:1px solid rgba(37,99,235,.25);">
      {cust.get('segment','active')}
    </span>
  </div>
  <div>{pills}</div>
</div>""", unsafe_allow_html=True)

# =============================================================================
# SECTION A — Generate draft
# =============================================================================
if st.session_state["generated_email"] is None:
    st.markdown("#### ⚡ Quick Templates")
    tmpl_cols = st.columns(4)
    templates = [
        ("👋 Welcome",        "welcome"),
        ("📢 Newsletter",     "newsletter"),
        ("⏰ Re-engagement",  "reengagement"),
        ("🚀 Product Launch", "product_launch"),
    ]
    picked_type = None
    for col, (lbl, t) in zip(tmpl_cols, templates):
        with col:
            if st.button(lbl, key=f"tmpl_{t}", use_container_width=True):
                picked_type = t

    st.markdown("---")
    st.markdown("#### 🎛️ Custom Campaign Builder")
    camp_cols = st.columns([2, 3])
    with camp_cols[0]:
        camp_type = st.selectbox(
            "Campaign type",
            ["welcome","reengagement","cold_outreach","newsletter",
             "product_launch","sales_pitch","custom","variant_test"],
            format_func=lambda x: x.replace("_"," ").title(),
            key="ai_camp_type")
    with camp_cols[1]:
        custom_instr = st.text_input(
            "Custom instructions (optional)",
            placeholder="E.g. Keep under 100 words, add 20% off coupon, use formal tone…",
            key="ai_custom_instr")

    atts = attachment_row("ai")

    if st.button("🌌  Generate Campaign", use_container_width=True, key="ai_gen_btn") or picked_type:
        g_type = picked_type or camp_type
        with st.spinner(f"✨ Gemini is writing a '{g_type.replace('_',' ').title()}' campaign for {cust.get('name')}…"):
            try:
                res = None
                if mode == "api":
                    payload = {"campaign_type": g_type, "customer_id": cust.get("id"), "send": False}
                    if g_type == "custom":
                        payload["user_instructions"] = custom_instr
                    elif g_type == "variant_test":
                        payload["base_campaign_type"] = "reengagement"
                        payload["num_variants"] = 3
                    r = requests.post(f"{BACKEND_URL}/api/email/generate", json=payload, timeout=90)
                    if r.status_code == 200:
                        res = r.json()
                    else:
                        st.error(f"API returned {r.status_code}: {r.text[:300]}")
                else:
                    if g_type == "custom":
                        res = run_async(gen_custom(customer_id=cust.get("id"),
                                                    user_instructions=custom_instr, send=False))
                    elif g_type == "variant_test":
                        res = run_async(gen_ab(customer_id=cust.get("id"),
                                               base_campaign_type="reengagement", num_variants=3))
                    else:
                        res = run_async(gen_campaign(campaign_type=g_type,
                                                      customer_id=cust.get("id"), send=False))

                if res and res.get("success"):
                    res["customer_full"] = cust
                    if isinstance(res["email"], list):
                        for v in res["email"]:
                            v["attachments"] = atts
                        res["html_content"] = [compose_html(v, cust) for v in res["email"]]
                    else:
                        res["email"]["attachments"] = atts
                        res["html_content"] = compose_html(res["email"], cust)
                    st.session_state["generated_email"]  = res
                    st.session_state["selected_variant_idx"] = 0
                    st.success("✅ Draft generated! Scroll down or the page will refresh.")
                    st.rerun()
                elif res:
                    st.error(f"Generation failed: {res.get('error','unknown')}")
            except Exception as e:
                st.error(f"Generation error: {e}")

# =============================================================================
# SECTION B — Draft console
# =============================================================================
else:
    draft_res  = st.session_state["generated_email"]
    cust_full  = draft_res.get("customer_full", cust)
    is_variants = isinstance(draft_res["email"], list)

    # Variant selector
    if is_variants:
        v_titles = [f"Variant {chr(65+i)}: {v.get('subject_line','—')}"
                    for i, v in enumerate(draft_res["email"])]
        v_idx = st.selectbox("🔀 Select Variant", range(len(v_titles)),
                             format_func=lambda i: v_titles[i],
                             index=st.session_state["selected_variant_idx"],
                             key="ai_var_sel")
        st.session_state["selected_variant_idx"] = v_idx
        email_data = draft_res["email"][v_idx]
        html_code  = draft_res["html_content"][v_idx]
    else:
        email_data = draft_res["email"]
        html_code  = draft_res["html_content"]

    # ── Top action bar ────────────────────────────────────────────────────────
    act1, act2, act3 = st.columns([2, 1, 1])
    with act1:
        st.markdown(
            f"""<div class="chat-prompt" style="margin-bottom:0;">
            <div class="chat-prompt-body">
              🤖 <strong>{draft_res.get('campaign_type','Campaign').replace('_',' ').title()}</strong>
              draft for <strong>{cust_full.get('name')}</strong>
            </div></div>""",
            unsafe_allow_html=True)
    with act2:
        if st.button("🔄 Regenerate", use_container_width=True, key="ai_regen"):
            st.session_state["generated_email"] = None
            st.rerun()
    with act3:
        if st.button("➕ New Campaign", use_container_width=True, key="ai_new2"):
            st.session_state["generated_email"] = None
            st.session_state["followup_email"]  = None
            st.rerun()

    st.markdown("---")

    # ── Two-column: Preview LEFT, Editor RIGHT ────────────────────────────────
    col_prev, col_edit = st.columns([1.15, 1], gap="large")

    with col_prev:
        st.markdown("#### 🎨 Email Preview")
        st.markdown(
            f"""<div style="background:#f1f5f9;border-radius:10px;padding:8px 14px;
            font-size:13px;margin-bottom:10px;color:#475569;">
            <strong>Subject:</strong> {email_data.get('subject_line','')}</div>""",
            unsafe_allow_html=True)
        tab_v, tab_c = st.tabs(["🎨 Visual", "📄 Raw HTML"])
        with tab_v:
            st.components.v1.html(html_code, height=540, scrolling=True)
        with tab_c:
            st.code(html_code, language="html")

        # AI metrics
        meta = email_data.get("metadata", {})
        st_time = meta.get("recommended_send_time")
        or_boost = meta.get("estimated_open_rate_boost")
        if st_time or or_boost:
            m1, m2 = st.columns(2)
            if st_time:  m1.metric("⏰ Best Send Time",  st_time)
            if or_boost: m2.metric("📈 Open-Rate Boost", or_boost)

    with col_edit:
        st.markdown("#### ✏️ Edit & Refine")
        tab_fields, tab_insights, tab_refine = st.tabs(
            ["✍️ Edit Fields", "💡 Insights", "💬 AI Rewrite"])

        with tab_fields:
            body_dict = email_data.get("body", {})
            e_s  = st.text_input("Subject",  value=email_data.get("subject_line",""), key="ai_e_s")
            e_g  = st.text_input("Greeting", value=body_dict.get("greeting",""),      key="ai_e_g")
            e_o  = st.text_area("Opening",   value=body_dict.get("opening",""),       key="ai_e_o", height=80)
            e_m  = st.text_area("Body",      value=body_dict.get("main_content",""),  key="ai_e_m", height=110)
            ec1, ec2 = st.columns(2)
            e_ct = ec1.text_input("CTA Text", value=body_dict.get("call_to_action",""), key="ai_e_ct")
            e_cu = ec2.text_input("CTA URL",  value=body_dict.get("cta_url",""),        key="ai_e_cu")
            e_cl = st.text_area("Closing",   value=body_dict.get("closing",""),        key="ai_e_cl", height=75)

            if st.button("💾 Apply Field Edits", use_container_width=True, key="ai_apply_edits"):
                email_data["subject_line"] = e_s
                email_data["body"].update({
                    "greeting": e_g, "opening": e_o, "main_content": e_m,
                    "call_to_action": e_ct, "cta_url": e_cu, "closing": e_cl,
                })
                new_html = compose_html(email_data, cust_full)
                if is_variants:
                    draft_res["html_content"][v_idx] = new_html
                else:
                    draft_res["html_content"] = new_html
                st.session_state["generated_email"] = draft_res
                st.success("✅ Fields updated!")
                st.rerun()

        with tab_insights:
            ss = meta.get("stylistic_suggestions", {})
            if ss:
                st.markdown(f"**Figure of speech**: {ss.get('figure_of_speech_used','—')}")
                st.markdown(f"**Language style**: {ss.get('parts_of_speech_adjustments','—')}")
                hooks = ss.get("alternative_hooks", [])
                if hooks:
                    st.markdown("**Alternative hooks:**")
                    for h in hooks:
                        st.markdown(f"> {h}")
            else:
                st.info("No insights available for this draft.")

        with tab_refine:
            refine_q = st.text_area(
                "What should change?",
                placeholder="E.g. Make it shorter, add urgency, include a 20% discount code, use formal tone…",
                height=80, key="ai_refine_q")
            if st.button("✨ Apply AI Rewrite", use_container_width=True, key="ai_refine_btn"):
                if refine_q.strip():
                    with st.spinner("Rewriting with Gemini…"):
                        try:
                            if mode == "api":
                                r2 = requests.post(
                                    f"{BACKEND_URL}/api/email/rewrite",
                                    json={"customer_id": cust_full.get("id"),
                                          "original_email": json.dumps(email_data),
                                          "feedback": refine_q}, timeout=90)
                                res2 = r2.json() if r2.status_code == 200 else None
                            else:
                                res2 = run_async(gen_rewrite(
                                    customer_id=cust_full.get("id"),
                                    original_email=json.dumps(email_data),
                                    feedback=refine_q))
                            if res2 and res2.get("success"):
                                new_e = res2["email"]
                                new_e["attachments"] = email_data.get("attachments", [])
                                new_html = compose_html(new_e, cust_full)
                                if is_variants:
                                    draft_res["email"][v_idx] = new_e
                                    draft_res["html_content"][v_idx] = new_html
                                else:
                                    draft_res["email"] = new_e
                                    draft_res["html_content"] = new_html
                                st.session_state["generated_email"] = draft_res
                                st.success("✅ Draft rewritten!")
                                st.rerun()
                            else:
                                st.error(f"Rewrite failed: {(res2 or {}).get('error','unknown')}")
                        except Exception as e:
                            st.error(f"Rewrite error: {e}")
                else:
                    st.warning("Type your feedback first.")

        # ── Attachments update ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 📎 Update Attachments")
        new_atts = attachment_row("ai_edit")
        if st.button("🔄 Apply Attachments", use_container_width=True, key="ai_apply_atts"):
            email_data["attachments"] = new_atts
            new_html = compose_html(email_data, cust_full)
            if is_variants:
                draft_res["html_content"][v_idx] = new_html
            else:
                draft_res["html_content"] = new_html
            st.session_state["generated_email"] = draft_res
            st.success("✅ Attachments updated!")
            st.rerun()

        # ── Send / Download ───────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 🛫 Send or Download")
        ov = st.text_input("📧 Recipient address",
                           value=st.session_state["override_email"], key="ai_ov")
        st.session_state["override_email"] = ov
        as1, as2 = st.columns(2)
        with as1:
            if st.button("🚀 Send Now", use_container_width=True, key="ai_send"):
                with st.spinner("Sending…"):
                    try:
                        res3 = run_async(send_sg(cust_full, email_data, to_override=ov))
                        if res3 and res3.get("success"):
                            st.session_state["delivery_status_type"] = "success"
                            st.session_state["delivery_status"] = (
                                f"✅ Stub mode — logged, not actually sent."
                                if res3.get("stub_mode") else
                                f"🚀 Sent to {ov} · ID: {res3.get('message_id','?')}"
                            )
                        else:
                            st.session_state["delivery_status_type"] = "error"
                            st.session_state["delivery_status"] = \
                                f"❌ {(res3 or {}).get('error','unknown')}"
                    except Exception as e:
                        st.session_state["delivery_status_type"] = "error"
                        st.session_state["delivery_status"] = f"❌ {e}"
                st.rerun()
        with as2:
            st.download_button(
                "📥 Download HTML", data=html_code,
                file_name=f"{draft_res.get('campaign_type','email')}_draft.html",
                mime="text/html", use_container_width=True, key="ai_dl")

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

    # =========================================================================
    # SECTION C — Follow-up
    # =========================================================================
    st.markdown("---")
    st.markdown("""
    <h3 style="font-size:1.3rem;font-weight:800;color:#0f172a;margin-bottom:4px;">
      🔁 Follow-up Campaign
    </h3>
    <p style="color:#475569;font-size:13px;margin-bottom:14px;">
      Generate a smart follow-up based on how the customer responded to this campaign.
    </p>""", unsafe_allow_html=True)

    fu_col1, fu_col2 = st.columns([2, 1])
    with fu_col1:
        follow_outcome = st.selectbox(
            "What did the customer do after receiving this email?",
            ["opened_no_click", "not_opened", "clicked_no_convert", "converted"],
            format_func=lambda x: {
                "opened_no_click":   "👀 Opened but didn't click anything",
                "not_opened":        "📪 Didn't open (needs a re-send nudge)",
                "clicked_no_convert":"👆 Clicked but didn't buy/sign up",
                "converted":         "🎉 Converted — send a thank-you/upsell",
            }[x],
            key="fu_outcome")
    with fu_col2:
        f_atts = []  # simple — no separate attachment row for follow-up
        generate_fu = st.button("🔁 Draft Follow-up", use_container_width=True, key="fu_gen")

    if generate_fu:
        with st.spinner("Gemini is writing your follow-up…"):
            try:
                prev_s = email_data.get("subject_line", "Important Update")
                if mode == "api":
                    r_fu = requests.post(
                        f"{BACKEND_URL}/api/email/followup",
                        json={"customer_id": cust_full.get("id"),
                              "previous_email_subject": prev_s,
                              "outcome": follow_outcome, "send": False}, timeout=90)
                    res_fu = r_fu.json() if r_fu.status_code == 200 else None
                else:
                    res_fu = run_async(gen_followup(
                        customer_id=cust_full.get("id"),
                        previous_email_subject=prev_s,
                        outcome=follow_outcome, send=False))

                if res_fu and res_fu.get("success"):
                    res_fu["customer_full"] = cust_full
                    res_fu["email"]["attachments"] = []
                    res_fu["html_content"] = compose_html(res_fu["email"], cust_full)
                    st.session_state["followup_email"] = res_fu
                    st.success("✅ Follow-up draft ready!")
                    st.rerun()
                else:
                    st.error(f"Follow-up failed: {(res_fu or {}).get('error','unknown')}")
            except Exception as e:
                st.error(f"Follow-up error: {e}")

    # ── Follow-up draft display ───────────────────────────────────────────────
    if st.session_state.get("followup_email"):
        f_res   = st.session_state["followup_email"]
        f_data  = f_res["email"]
        f_html  = f_res["html_content"]
        f_cust  = f_res.get("customer_full", cust)

        st.markdown("---")
        fpc, fec = st.columns([1.15, 1], gap="large")

        with fpc:
            st.markdown("##### 🎨 Follow-up Preview")
            st.markdown(
                f"""<div style="background:#f1f5f9;border-radius:10px;padding:8px 14px;
                font-size:13px;margin-bottom:10px;color:#475569;">
                <strong>Subject:</strong> {f_data.get('subject_line','')}</div>""",
                unsafe_allow_html=True)
            ft1, ft2 = st.tabs(["🎨 Visual", "📄 HTML"])
            with ft1: st.components.v1.html(f_html, height=500, scrolling=True)
            with ft2: st.code(f_html, language="html")

        with fec:
            st.markdown("##### ✍️ Edit Follow-up")
            fb  = f_data.get("body", {})
            fs  = st.text_input("Subject",  value=f_data.get("subject_line",""), key="fu_es")
            fg  = st.text_input("Greeting", value=fb.get("greeting",""),         key="fu_eg")
            fo  = st.text_area("Opening",   value=fb.get("opening",""),          key="fu_eo", height=75)
            fm  = st.text_area("Body",      value=fb.get("main_content",""),     key="fu_em", height=100)
            fc1, fc2 = st.columns(2)
            fct = fc1.text_input("CTA Text", value=fb.get("call_to_action",""), key="fu_ect")
            fcu = fc2.text_input("CTA URL",  value=fb.get("cta_url",""),        key="fu_ecu")
            fcl = st.text_area("Closing",   value=fb.get("closing",""),         key="fu_ecl", height=75)

            if st.button("💾 Apply Edits", use_container_width=True, key="fu_apply"):
                f_data["subject_line"] = fs
                f_data["body"].update({
                    "greeting":fg,"opening":fo,"main_content":fm,
                    "call_to_action":fct,"cta_url":fcu,"closing":fcl})
                f_res["html_content"] = compose_html(f_data, f_cust)
                st.session_state["followup_email"] = f_res
                st.success("✅ Follow-up updated!")
                st.rerun()

            st.markdown("---")
            ov_fu = st.session_state.get("override_email","almanesque1129@gmail.com")
            fa1, fa2 = st.columns(2)
            with fa1:
                if st.button("🚀 Send Follow-up", use_container_width=True, key="fu_send"):
                    with st.spinner("Sending…"):
                        try:
                            rfu = run_async(send_sg(f_cust, f_data, to_override=ov_fu))
                            if rfu and rfu.get("success"):
                                st.markdown(
                                    f"""<div style="background-color:#f0fdf4;border:2px solid #16a34a;border-radius:12px;
                                    padding:12px 16px;color:#15803d;font-weight:700;font-size:14px;margin-bottom:12px;">
                                      🚀 Follow-up sent to {ov_fu}!
                                    </div>""",
                                    unsafe_allow_html=True
                                )
                            else:
                                err_msg = (rfu or {}).get('error','unknown')
                                st.markdown(
                                    f"""<div style="background-color:#fef2f2;border:2px solid #dc2626;border-radius:12px;
                                    padding:12px 16px;color:#991b1b;font-weight:700;font-size:14px;margin-bottom:12px;">
                                      ❌ Send failed: {err_msg}
                                    </div>""",
                                    unsafe_allow_html=True
                                )
                        except Exception as e:
                            st.markdown(
                                f"""<div style="background-color:#fef2f2;border:2px solid #dc2626;border-radius:12px;
                                padding:12px 16px;color:#991b1b;font-weight:700;font-size:14px;margin-bottom:12px;">
                                  ❌ Exception: {e}
                                </div>""",
                                unsafe_allow_html=True
                            )
            with fa2:
                st.download_button(
                    "📥 Download", data=f_html,
                    file_name=f"followup_{f_res.get('campaign_type','email')}.html",
                    mime="text/html", use_container_width=True, key="fu_dl")

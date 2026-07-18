"""
utils_shared.py — Shared CSS, helpers, data fetching, sidebar.
"""

import asyncio
import requests
import streamlit as st

BACKEND_URL = "http://localhost:8000"

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
SHARED_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');

html, body, [data-testid="stSidebar"], .stMarkdown {
    font-family: 'Outfit', sans-serif !important;
    background-color: #f8fafc;
    color: #0f172a;
}
.stApp { background-color: #f8fafc; }

/* Force all widget labels and text to be dark and visible */
label, 
.stWidgetLabel, 
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p,
[data-testid="stRadio"] label,
[data-testid="stRadio"] label p,
[data-testid="stRadio"] p,
[data-testid="stRadio"] div,
[data-testid="stRadio"] span {
    color: #0f172a !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}

/* ── Sidebar background ── */
[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #e2e8f0; }

/* ── Sidebar page-nav section ── */
[data-testid="stSidebarNav"],
section[data-testid="stSidebar"] nav {
    background: linear-gradient(160deg, #1e1b4b 0%, #312e81 100%) !important;
    border-bottom: 2px solid #4338ca !important;
    border-radius: 0 0 18px 18px !important;
    padding: 10px 8px 16px 8px !important;
    margin-bottom: 12px !important;
}
/* Nav links — every state */
[data-testid="stSidebarNav"] a,
section[data-testid="stSidebar"] nav ul li a {
    display: flex !important; align-items: center !important; gap: 10px !important;
    padding: 10px 14px !important; border-radius: 10px !important; margin: 5px 0 !important;
    font-size: 13px !important; font-weight: 700 !important; color: #c7d2fe !important;
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(165,180,252,0.2) !important;
    text-decoration: none !important; transition: all 0.2s ease !important;
    letter-spacing: 0.2px !important;
}
[data-testid="stSidebarNav"] a:hover,
section[data-testid="stSidebar"] nav ul li a:hover {
    background: rgba(255,255,255,0.14) !important;
    border-color: rgba(165,180,252,0.5) !important;
    color: #ffffff !important; transform: translateX(4px) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"],
section[data-testid="stSidebar"] nav ul li a[aria-current="page"] {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
    border-color: rgba(165,180,252,0.4) !important; color: #ffffff !important;
    box-shadow: 0 4px 14px rgba(79,70,229,0.5) !important;
    font-weight: 800 !important;
}
/* Span/p text inside nav links */
[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNav"] a p {
    color: inherit !important; font-weight: inherit !important;
}

/* ── Buttons ── */
div.stButton > button:first-child {
    background-color: #ffffff; color: #0f172a;
    border: 1px solid #cbd5e1; border-radius: 20px; font-weight: 600; transition: all .2s;
}
div.stButton > button:first-child:hover { background-color: #f1f5f9; border-color: #94a3b8; }

/* ── Primary buttons (Generate Campaign) ── */
div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #b45309, #d97706) !important;
    color: white !important; border: none !important; border-radius: 12px !important;
    font-weight: 700 !important; font-size: 15px !important;
    box-shadow: 0 4px 14px rgba(180,83,9,0.3) !important;
}

/* ── Sidebar Recipient Selection Buttons (Light, High-Contrast Cards) ── */
[data-testid="stSidebar"] div.stButton > button {
    background-color: #ffffff !important;
    background: #ffffff !important;
    color: #1e293b !important;
    border: 1.5px solid #cbd5e1 !important;
    border-radius: 12px !important;
    padding: 8px 14px !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    text-align: left !important;
    box-shadow: 0 2px 5px rgba(0,0,0,0.04) !important;
    transition: all 0.2s ease !important;
    margin-bottom: 5px !important;
}
[data-testid="stSidebar"] div.stButton > button:hover {
    background-color: #fffbeb !important;
    background: #fffbeb !important;
    border-color: #f59e0b !important;
    color: #b45309 !important;
    transform: translateX(4px) !important;
    box-shadow: 0 4px 12px rgba(245,158,11,0.15) !important;
}
[data-testid="stSidebar"] div.stButton > button span,
[data-testid="stSidebar"] div.stButton > button p,
[data-testid="stSidebar"] div.stButton > button div {
    color: #1e293b !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] div.stButton > button:hover span,
[data-testid="stSidebar"] div.stButton > button:hover p,
[data-testid="stSidebar"] div.stButton > button:hover div {
    color: #b45309 !important;
}

/* ── Greeting ── */
.gemini-greeting { font-size:2.6rem; font-weight:700; letter-spacing:-1px; line-height:1.15;
    margin-top:8px; margin-bottom:6px; text-align:center; color:#0f172a; }
.greeting-gradient { background: linear-gradient(135deg,#7c2d12 0%,#b45309 50%,#d97706 100%);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
.gemini-sub { font-size:1rem; color:#475569; text-align:center; margin-bottom:20px;
    max-width:680px; margin-left:auto; margin-right:auto; }

/* ── Cards ── */
.suggestion-card { background:#fff; border:1px solid #e2e8f0; border-radius:16px; padding:18px;
    min-height:120px; display:flex; flex-direction:column; justify-content:space-between;
    box-shadow:0 4px 6px -1px rgba(0,0,0,.05); transition:all .2s; }
.suggestion-card:hover { transform:translateY(-2px); border-color:#b45309;
    box-shadow:0 8px 20px rgba(180,83,9,0.12); }
.suggestion-title { font-size:1rem; font-weight:700; color:#0f172a; margin-bottom:6px; }
.suggestion-desc  { font-size:.83rem; color:#475569; line-height:1.45; }

/* ── Profile / recipient card ── */
.active-profile-card { background:#fff; border:1px solid #e2e8f0; border-radius:16px;
    padding:18px; margin-bottom:18px; box-shadow:0 2px 8px rgba(0,0,0,.04); }
.badge-label { display:inline-block; padding:3px 10px; border-radius:9999px;
    font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; }
.pill-interest { display:inline-block; padding:3px 10px; background:rgba(37,99,235,.1);
    color:#2563eb; border:1px solid rgba(37,99,235,.3); border-radius:8px;
    font-size:12px; font-weight:500; margin:3px; }

/* ── Stats ── */
.stat-container { display:flex; justify-content:space-between; gap:8px; margin-bottom:16px; }
.stat-box { flex:1; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;
    padding:10px; text-align:center; }
.stat-val { font-size:1.3rem; font-weight:800; color:#2563eb; }
.stat-lbl { font-size:.7rem; color:#64748b; text-transform:uppercase; letter-spacing:.5px; margin-top:3px; }

/* ── Sidebar recipient radio list ── */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 4px !important;
    display: flex !important;
    flex-direction: column !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    background: #ffffff !important;
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 9px 14px !important;
    margin: 0 !important;
    color: #1e293b !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    cursor: pointer !important;
    transition: all 0.18s ease !important;
    display: flex !important;
    align-items: center !important;
    width: 100% !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: #fffbeb !important;
    border-color: #f59e0b !important;
    color: #b45309 !important;
    transform: translateX(4px) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"],
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%) !important;
    border-color: #f59e0b !important;
    color: #b45309 !important;
    font-weight: 800 !important;
    box-shadow: 0 3px 10px rgba(245,158,11,0.18) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label p,
[data-testid="stSidebar"] [data-testid="stRadio"] label span {
    color: inherit !important;
    font-weight: inherit !important;
}
/* Hide radio circle dot */
[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"] ~ div:first-of-type svg,
[data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"] {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* ── Checkboxes styled as cards ── */
div[data-testid="stCheckbox"] {
    background-color: #ffffff !important;
    border: 2px solid #e2e8f0 !important;
    border-radius: 16px !important;
    padding: 16px 12px !important;
    min-height: 100px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: all 0.2s ease-in-out !important;
    width: 100% !important;
    box-sizing: border-box !important;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05) !important;
}
div[data-testid="stCheckbox"]:hover {
    border-color: #b45309 !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 16px rgba(180,83,9,0.12) !important;
}
div[data-testid="stCheckbox"]:has(input[type="checkbox"]:checked) {
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%) !important;
    border-color: #d97706 !important;
    box-shadow: 0 6px 14px rgba(217,119,6,0.15) !important;
}
div[data-testid="stCheckbox"] label {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 10px !important;
    width: 100% !important;
    height: 100% !important;
    cursor: pointer !important;
    margin: 0 !important;
}
div[data-testid="stCheckbox"] label p {
    color: #0f172a !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    margin: 0 !important;
    text-align: center !important;
}
div[data-testid="stCheckbox"] div[role="checkbox"],
div[data-testid="stCheckbox"] span[role="checkbox"] {
    background-color: #ffffff !important;
    border: 2px solid #cbd5e1 !important;
    border-radius: 6px !important;
    width: 20px !important;
    height: 20px !important;
}
div[data-testid="stCheckbox"] input[type="checkbox"]:checked + div,
div[data-testid="stCheckbox"] input[type="checkbox"]:checked + span {
    background-color: #d97706 !important;
    border-color: #d97706 !important;
    color: #ffffff !important;
}

/* ── Tabs ── */
button[data-baseweb="tab"] { background:transparent !important; border:none !important;
    color:#475569 !important; font-weight:600 !important; font-size:14px !important;
    padding:10px 16px !important; transition:all .2s !important; }
button[data-baseweb="tab"]:hover { color:#b45309 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color:#b45309 !important;
    border-bottom:2px solid #b45309 !important; }

/* ── Walkthrough steps ── */
.step-card { display:flex; gap:16px; align-items:flex-start; padding:16px;
    background:#fff; border:1px solid #e2e8f0; border-radius:14px; margin-bottom:12px;
    box-shadow:0 2px 6px rgba(0,0,0,0.04); }
.step-num { width:36px; height:36px; border-radius:50%; background:linear-gradient(135deg,#b45309,#d97706);
    color:white; font-weight:800; font-size:15px; display:flex; align-items:center;
    justify-content:center; flex-shrink:0; }
.step-body h4 { margin:0 0 4px 0; font-size:15px; font-weight:700; color:#0f172a; }
.step-body p  { margin:0; font-size:13px; color:#475569; line-height:1.5; }
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Async helper
# ─────────────────────────────────────────────────────────────────────────────
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ─────────────────────────────────────────────────────────────────────────────
# Backend — import once, cache for whole process
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def load_backend():
    try:
        from backend.ai.email_generator import (
            generate_campaign_email, generate_followup_email,
            generate_rewrite, generate_custom_campaign,
            generate_ab_variants, _compose_html_email, _send_via_sendgrid,
        )
        from backend.data.stream_manager import dataset_manager
        if not dataset_manager._initialized:
            try:
                run_async(dataset_manager.initialize())
            except Exception:
                # If network initialization failed, manually bootstrap the manager with mock users!
                from backend.data.data_enricher import enrich_batch
                import uuid
                mock_raw = []
                first_names = ["Emma", "Liam", "Sophia", "Noah", "Olivia", "Lucas", "Isabella", "Ethan", "Sarah", "John",
                               "Mia", "Oliver", "Charlotte", "Amelia", "Harper", "Evelyn", "Abigail", "Emily", "Elizabeth", "Sofia"]
                last_names  = ["Smith", "Jones", "Miller", "Davis", "Garcia", "Rodriguez", "Wilson", "Thomas", "Taylor", "Moore",
                               "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez"]
                domains     = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
                for i in range(40):
                    fn = first_names[i % len(first_names)]
                    ln = last_names[(i * 3) % len(last_names)]
                    mock_raw.append({
                        "gender": "female" if i % 2 == 0 else "male",
                        "name": {"title": "Ms" if i % 2 == 0 else "Mr", "first": fn, "last": ln},
                        "location": {"city": "Austin", "country": "United States", "state": "Texas"},
                        "email": f"{fn.lower()}.{ln.lower()}{i}@{domains[i % len(domains)]}",
                        "dob": {"date": "1997-03-15T00:00:00Z", "age": 29},
                        "registered": {"date": "2023-09-12T00:00:00Z"},
                        "picture": {"thumbnail": "https://randomuser.me/api/portraits/thumb/women/1.jpg" if i % 2 == 0 else "https://randomuser.me/api/portraits/thumb/men/1.jpg"},
                        "phone": f"+1-555-010{i:02d}"
                    })
                # Enrich mock raw users
                enriched = enrich_batch(mock_raw)
                # Manually set dataset_manager._dataset
                dataset_manager._dataset = enriched
                dataset_manager._stats["total_records"] = len(enriched)
                dataset_manager._initialized = True
        return {
            "ok": True,
            "dataset_manager": dataset_manager,
            "generate_campaign_email": generate_campaign_email,
            "generate_followup_email": generate_followup_email,
            "generate_rewrite": generate_rewrite,
            "generate_custom_campaign": generate_custom_campaign,
            "generate_ab_variants": generate_ab_variants,
            "_compose_html_email": _compose_html_email,
            "_send_via_sendgrid": _send_via_sendgrid,
        }
    except ImportError as e:
        return {"ok": False, "error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# Data fetching — cached so sidebar doesn't hammer API on every widget
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=10)
def fetch_customers():
    """Try REST API first; fall back to in-memory dataset_manager."""
    # 1. Try the live REST API
    try:
        r = requests.get(f"{BACKEND_URL}/api/dataset?limit=200", timeout=4)
        if r.status_code == 200:
            records = r.json().get("records", [])
            if records:
                return records
    except Exception:
        pass
    # 2. In-memory fallback — import the dataset manager directly
    try:
        from backend.data.stream_manager import dataset_manager
        records = run_async(dataset_manager.get_all(limit=200))
        if records:
            return records
    except Exception:
        pass
    return []

@st.cache_data(ttl=10)
def fetch_stats():
    """Try REST API first; fall back to in-memory dataset_manager."""
    try:
        r = requests.get(f"{BACKEND_URL}/api/dataset/stats", timeout=4)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    try:
        from backend.data.stream_manager import dataset_manager
        stats = run_async(dataset_manager.get_stats())
        if stats:
            return stats
    except Exception:
        pass
    return {}

@st.cache_data(ttl=4)
def check_backend_alive():
    try:
        r = requests.get(f"{BACKEND_URL}/api/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# Session-state initialisation — call at top of every page
# ─────────────────────────────────────────────────────────────────────────────
DEFAULTS = {
    "selected_customer":       None,
    "selected_customer_id":    None,
    "selected_customer_email": None,
    "generated_email":         None,
    "followup_email":          None,
    "selected_variant_idx":    0,
    "delivery_status":         None,
    "delivery_status_type":    "info",
    "override_email":          "almanesque1129@gmail.com",
}

def init_session():
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — shared across all pages
# ─────────────────────────────────────────────────────────────────────────────
def render_sidebar():
    """Draw sidebar, handle customer selection, return (cust, mode, be)."""
    init_session()
    be    = load_backend()
    alive = check_backend_alive()

    # ── Connection badge ──
    if alive:
        st.sidebar.markdown(
            """<div style="background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.3);
            border-radius:10px;padding:9px 12px;font-size:12px;color:#16a34a;margin-bottom:12px;
            font-weight:600;">🟢 API Connected — localhost:8000</div>""",
            unsafe_allow_html=True)
        mode = "api"
    elif be["ok"]:
        st.sidebar.markdown(
            """<div style="background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.3);
            border-radius:10px;padding:9px 12px;font-size:12px;color:#2563eb;margin-bottom:12px;
            font-weight:600;">🤖 In-Memory Mode (API offline)</div>""",
            unsafe_allow_html=True)
        mode = "local"
    else:
        st.sidebar.error(f"Backend error: {be.get('error','unknown')}")
        mode = "error"

    # ── Branding ──
    st.sidebar.markdown(
        """<div style="font-size:1.2rem;font-weight:800;color:#0f172a;
        margin-bottom:14px;display:flex;align-items:center;gap:8px;">
        🌌 Gemini Email AI</div>""",
        unsafe_allow_html=True)

    # ── New Campaign button ──
    if st.sidebar.button("➕ New Campaign", use_container_width=True, key="sb_new"):
        st.session_state["generated_email"]  = None
        st.session_state["followup_email"]   = None
        st.session_state["delivery_status"]  = None
        st.session_state["selected_variant_idx"] = 0
        st.rerun()

    # ── Stats ──
    stats = fetch_stats()
    if stats:
        dist  = stats.get("segment_distribution", {})
        vip   = dist.get("vip", 0) + dist.get("high_value", 0)
        inact = dist.get("inactive", 0)
        total = stats.get("total_records", 0)
        st.sidebar.markdown(
            f"""<div class="stat-container">
              <div class="stat-box"><div class="stat-val">{total}</div><div class="stat-lbl">Records</div></div>
              <div class="stat-box"><div class="stat-val">{vip}</div><div class="stat-lbl">VIPs</div></div>
              <div class="stat-box"><div class="stat-val">{inact}</div><div class="stat-lbl">Inactive</div></div>
            </div>""",
            unsafe_allow_html=True)

    # ── Search + filter ──
    st.sidebar.markdown(
        """<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;
        letter-spacing:1px;margin-top:8px;margin-bottom:3px;'>🔍 Search by name or email</div>""",
        unsafe_allow_html=True)
    search_q = st.sidebar.text_input(
        "Search customers", placeholder="Type a name or email…",
        key="sb_search", label_visibility="collapsed")

    st.sidebar.markdown(
        """<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;
        letter-spacing:1px;margin-top:6px;margin-bottom:3px;'>🏷️ Filter by segment</div>""",
        unsafe_allow_html=True)
    seg_f = st.sidebar.selectbox(
        "Filter segment",
        ["All segments","active","vip","inactive","churn_risk","new"],
        format_func=lambda x: {
            "All segments": "👥 All segments",
            "active":       "🟢 Active",
            "vip":          "👑 VIP",
            "inactive":     "⚪ Inactive",
            "churn_risk":   "🔴 Churn Risk",
            "new":          "🆕 New",
        }.get(x, x),
        key="sb_seg", label_visibility="collapsed")

    customers = fetch_customers()

    # Determine currently selected ID/email
    curr_cust  = st.session_state.get("selected_customer")
    curr_id    = (curr_cust or {}).get("id") or st.session_state.get("selected_customer_id")
    curr_email = (curr_cust or {}).get("email") or st.session_state.get("selected_customer_email")

    # Match from current fetched list
    matched = None
    if curr_id:
        matched = next((c for c in customers if c.get("id") == curr_id), None)
    if not matched and curr_email:
        matched = next((c for c in customers if c.get("email") == curr_email), None)
    if not matched and customers:
        matched = customers[0]

    if matched:
        st.session_state["selected_customer"]       = matched
        st.session_state["selected_customer_id"]    = matched.get("id")
        st.session_state["selected_customer_email"] = matched.get("email")

    seg_filter = seg_f if seg_f != "All segments" else "All"
    filtered = [
        c for c in customers
        if (not search_q
            or search_q.lower() in c.get("name","").lower()
            or search_q.lower() in c.get("email","").lower()
            or any(search_q.lower() in i.lower() for i in c.get("interests",[])))
        and (seg_filter == "All" or c.get("segment","").lower() == seg_filter.lower())
    ]

    if not customers:
        st.sidebar.markdown(
            """<div style='background:#fef3e2;border:1px solid #f0d9b5;border-radius:10px;
            padding:10px 12px;font-size:12px;color:#92400e;margin:8px 0;'>
            ⏳ Loading customers… If this persists, start the backend:<br><br>
            <code style='font-size:11px;'>py -3.13 -m uvicorn backend.main:app --port 8000</code>
            </div>""",
            unsafe_allow_html=True)

    selected_id    = st.session_state.get("selected_customer_id")
    selected_email = st.session_state.get("selected_customer_email")

    # ── Customer list as radio (immune to dark button theming) ──────────────────
    st.sidebar.markdown(
        """<div style="font-size:.75rem;font-weight:700;color:#b45309;text-transform:uppercase;
        letter-spacing:1.2px;margin-top:10px;margin-bottom:6px;padding:0 4px;">
        👥 Select Recipient</div>""",
        unsafe_allow_html=True)

    pool = filtered[:20]
    if pool:
        seg_icon_map = lambda seg: (
            "👑" if seg.upper() == "VIP"
            else "🟢" if seg.upper() in ("ACTIVE", "HIGH_VALUE")
            else "🟡" if seg.upper() in ("AT_RISK", "CHURN_RISK")
            else "⚪"
        )
        radio_labels = [
            f"{seg_icon_map(c.get('segment',''))} {c.get('name', '—')}"
            for c in pool
        ]

        # Find default index matching the currently selected customer
        curr_idx = 0
        for idx, c in enumerate(pool):
            if c.get("id") == selected_id or c.get("email") == selected_email:
                curr_idx = idx
                break

        chosen_label = st.sidebar.radio(
            "Recipients",
            radio_labels,
            index=curr_idx,
            key="recipient_radio",
            label_visibility="collapsed",
        )

        # Resolve the chosen label back to the full customer object
        chosen_idx = radio_labels.index(chosen_label) if chosen_label in radio_labels else 0
        new_cust   = pool[chosen_idx]

        if new_cust.get("id") != selected_id or new_cust.get("email") != selected_email:
            st.session_state["selected_customer"]       = new_cust
            st.session_state["selected_customer_id"]    = new_cust.get("id")
            st.session_state["selected_customer_email"] = new_cust.get("email")
            st.session_state["delivery_status"]         = None
            st.session_state["followup_email"]          = None
            st.session_state["generated_email"]         = None
            st.rerun()

    # ── ML Intelligence Badge for selected customer ──────────────────────────
    sel_cust = st.session_state.get("selected_customer")
    if sel_cust:
        try:
            from backend.ml.ml_engine import run_ml_predictions, train_ml_models
            ml_p = run_ml_predictions(sel_cust, filtered)
            churn_label = ml_p.get("churn_label", "")
            churn_pct   = ml_p.get("churn_pct", "")
            rec_prod    = ml_p.get("recommended_product", "")

            churn_color = (
                "#dc2626" if churn_label == "High Risk"
                else "#d97706" if churn_label == "Moderate Risk"
                else "#16a34a"
            )
            churn_emoji = (
                "🔴" if churn_label == "High Risk"
                else "🟡" if churn_label == "Moderate Risk"
                else "🟢"
            )
            st.sidebar.markdown(
                f"""<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
                padding:10px 12px;margin:6px 0 4px 0;">
                  <div style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;
                  letter-spacing:.9px;margin-bottom:6px;">🤖 ML Intelligence</div>
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
                    <span style="font-size:11px;color:#475569;font-weight:600;">Churn Risk</span>
                    <span style="font-size:11px;font-weight:800;color:{churn_color};">
                      {churn_emoji} {churn_pct} · {churn_label}
                    </span>
                  </div>
                  <div style="font-size:10px;color:#64748b;border-top:1px solid #f1f5f9;padding-top:5px;
                  margin-top:2px;">
                    🎯 <strong>Recommended:</strong> {rec_prod}
                  </div>
                </div>""",
                unsafe_allow_html=True)
        except Exception:
            pass  # ML not available — silently skip badge

    # ── User footer ──
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """<div style="display:flex;align-items:center;gap:10px;padding:4px 0;">
          <div style="width:34px;height:34px;background:linear-gradient(135deg,#2563eb,#7c3aed);
          border-radius:50%;display:flex;align-items:center;justify-content:center;
          font-weight:bold;color:white;font-size:13px;flex-shrink:0;">MA</div>
          <div>
            <div style="font-weight:600;color:#0f172a;font-size:13px;">Mohammad Alman</div>
            <div style="font-size:11px;color:#64748b;">almanesque1129@gmail.com</div>
          </div>
        </div>""",
        unsafe_allow_html=True)

    return st.session_state.get("selected_customer"), mode, be



# ─────────────────────────────────────────────────────────────────────────────
# Attachment row — 5 colourful cards
# ─────────────────────────────────────────────────────────────────────────────
ATT_CONFIG = [
    {
        "key":   "pdf",
        "label": "PDF Brochure",
        "icon":  "📄",
        "color": "#dc2626",   # red
        "bg":    "rgba(220,38,38,0.08)",
        "border":"rgba(220,38,38,0.35)",
        "data":  {"type":"pdf","title":"Premium Product Catalog","url":"https://example.com/guide.pdf"},
    },
    {
        "key":   "vid",
        "label": "Demo Video",
        "icon":  "🎬",
        "color": "#7c3aed",   # purple
        "bg":    "rgba(124,58,237,0.08)",
        "border":"rgba(124,58,237,0.35)",
        "data":  {"type":"video","title":"Feature Walkthrough Demo",
                  "url":"https://example.com/demo",
                  "thumbnail_url":"https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?auto=format&fit=crop&w=600&q=80"},
    },
    {
        "key":   "img",
        "label": "Image Card",
        "icon":  "🖼️",
        "color": "#059669",   # emerald
        "bg":    "rgba(5,150,105,0.08)",
        "border":"rgba(5,150,105,0.35)",
        "data":  {"type":"image","title":"Exclusive Product Showcase",
                  "url":"https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=600&q=80"},
    },
    {
        "key":   "link",
        "label": "Web Link",
        "icon":  "🔗",
        "color": "#2563eb",   # blue
        "bg":    "rgba(37,99,235,0.08)",
        "border":"rgba(37,99,235,0.35)",
        "data":  {"type":"link","title":"Visit Our Knowledge Base","url":"https://example.com/knowledgebase"},
    },
    {
        "key":   "cal",
        "label": "Calendar",
        "icon":  "📅",
        "color": "#d97706",   # amber
        "bg":    "rgba(217,119,6,0.08)",
        "border":"rgba(217,119,6,0.35)",
        "data":  {"type":"calendar","title":"Schedule a Call","url":"https://example.com/calendar"},
    },
]

def attachment_row(key_prefix: str):
    """Render 5 colourful attachment toggle cards. Returns list of selected attachments."""
    st.markdown(
        """<div style="text-align:center;margin:14px 0 10px;font-size:13px;font-weight:700;
        color:#475569;letter-spacing:0.3px;">📎 SELECT ATTACHMENTS TO INCLUDE</div>""",
        unsafe_allow_html=True)

    cols = st.columns(5)
    selected = []

    for col, cfg in zip(cols, ATT_CONFIG):
        k = f"{key_prefix}_{cfg['key']}"
        label_text = f"{cfg['icon']} {cfg['label']}"
        with col:
            # Render a styled native checkbox
            is_checked = st.checkbox(label_text, key=k)
            if is_checked:
                selected.append(cfg["data"])

    return selected

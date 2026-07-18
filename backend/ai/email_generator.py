"""
email_generator.py — PART 2: Email Generation Orchestrator
============================================================
This is the BRAIN of the entire Part 2 system.

It connects everything together:
  dataset → prompt_builder → ai_adapter → json_extractor → sendgrid sender

Think of this file as the "manager" who:
1. Takes a request ("generate a welcome email for this customer")
2. Delegates to the right specialist (prompt_builder)
3. Sends to AI (ai_adapter)
4. Validates the result (json_extractor, already done inside ai_adapter)
5. Optionally sends the email (sendgrid_sender)
6. Returns a clean result with full metadata

ALL API ROUTES in main.py call functions from THIS file.
This file never directly calls Gemini/Groq — that's ai_adapter's job.
This file never directly builds prompts — that's prompt_builder's job.

SEPARATION OF CONCERNS:
  main.py         → HTTP layer (routing, request parsing, response formatting)
  email_generator → Business logic (orchestration, decisions)
  prompt_builder  → Prompt creation
  ai_adapter      → AI API calls
  json_extractor  → JSON parsing (called inside ai_adapter)
  sendgrid_sender → Email delivery
"""

import logging
import time
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone

from backend.ai.ai_adapter import ai_adapter
from backend.ai.prompt_builder import (
    build_welcome_email_prompt,
    build_reengagement_prompt,
    build_variant_test_prompt,
    build_followup_prompt,
    build_rewrite_prompt,
    build_custom_campaign_prompt,
    get_builder,
)
from backend.data.stream_manager import dataset_manager
from backend.config import DEFAULT_VARIANT_COUNT
try:
    from backend.ml.ml_engine import run_ml_predictions, train_ml_models
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False
    def run_ml_predictions(customer, all_customers=None):
        return {}
    def train_ml_models(customers):
        pass

logger = logging.getLogger(__name__)


# =============================================================================
# SMART CUSTOMER LOOKUP — Never throws 404 during demos
# =============================================================================

async def _get_customer_or_mock(customer_id: Optional[str]) -> Dict[str, Any]:
    """
    Looks up a customer by ID. If the customer has rotated out of the live
    dataset (which refreshes every ~8 seconds), returns a realistic mock
    profile using the same UUID — so the API never throws a 404 error.

    If customer_id is None, empty, or Swagger's "string" placeholder, it
    dynamically selects a random real customer from the database to ensure
    the API succeeds without a 404.
    """
    import random
    import uuid as _uuid

    clean_id = None
    if customer_id and customer_id.strip().lower() not in ("string", ""):
        clean_id = customer_id.strip()

    if clean_id:
        customer = await dataset_manager.get_by_id(clean_id)
        if customer:
            return customer
        logger.warning(
            f"Customer {clean_id[:8]}... rotated out of live dataset. "
            "Generating a realistic mock profile for seamless demo."
        )
        target_uuid = clean_id
    else:
        # Fallback: Try to grab any random customer from our live database
        random_customers = await dataset_manager.get_random(count=1)
        if random_customers:
            return random_customers[0]
        target_uuid = str(_uuid.uuid4())

    first_names = ["Emma", "Liam", "Sophia", "Noah", "Olivia",
                   "Jackson", "Ava", "Lucas", "Isabella", "Ethan"]
    last_names  = ["Smith", "Jones", "Miller", "Davis", "Garcia",
                   "Rodriguez", "Wilson", "Martinez", "Anderson", "Taylor"]
    interest_pools = [
        ["fitness", "nutrition", "running"],
        ["coding", "open-source", "web design"],
        ["cooking", "baking", "fine dining"],
        ["music", "concerts", "guitar"],
        ["gardening", "sustainability", "plants"],
        ["books", "creative writing", "podcasts"],
        ["travel", "photography", "culture"],
        ["investing", "budgeting", "crypto"],
    ]
    domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]
    segments = ["active", "high_value", "at_risk", "inactive"]

    first  = random.choice(first_names)
    last   = random.choice(last_names)
    domain = random.choice(domains)

    return {
        "id":            target_uuid,
        "first_name":    first,
        "last_name":     last,
        "name":          f"{first} {last}",
        "email":         f"{first.lower()}.{last.lower()}@{domain}",
        "segment":       random.choice(segments),
        "interests":     random.choice(interest_pools),
        "purchase_history": [
            {"date": "2026-05-20", "item": "Starter Package",    "amount": 49.99, "currency": "USD"},
            {"date": "2026-06-15", "item": "Premium Membership", "amount": 19.99, "currency": "USD"},
        ],
        "email_behavior": {
            "open_rate":           round(random.uniform(0.25, 0.65), 2),
            "click_rate":          round(random.uniform(0.05, 0.25), 2),
            "emails_received":     random.randint(5, 40),
            "preferred_send_time": random.choice(["Tuesday 10:00 AM", "Wednesday 2:00 PM", "Thursday 10:00 AM"]),
            "unsubscribed":        False,
            "bounced":             False,
        },
        "account_age_days":   random.randint(30, 400),
        "last_active":        "2026-07-10T14:30:00Z",
        "tags":               ["active", "demo-mock"],
    }


# =============================================================================
# RESULT WRAPPER
# =============================================================================

def _wrap_result(
    email_data: Union[Dict, List[Dict]],
    campaign_type: str,
    customer: Dict,
    generation_time_ms: float,
    sent: bool = False,
    send_result: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Wraps the generated email(s) with metadata about how they were generated.
    """
    # Generate HTML content for the email(s)
    if isinstance(email_data, list):
        html_content = [_compose_html_email(v, customer) for v in email_data]
    else:
        # For single emails, inject the campaign_type if missing
        if "campaign_type" not in email_data:
            email_data["campaign_type"] = campaign_type
        html_content = _compose_html_email(email_data, customer)

    return {
        "success": True,
        "campaign_type": campaign_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_time_ms": round(generation_time_ms, 2),
        "customer": {
            "id": customer.get("id"),
            "name": customer.get("name"),
            "email": customer.get("email"),
            "segment": customer.get("segment"),
        },
        "email": email_data,   # The actual email JSON from AI
        "html_content": html_content,  # Rendered HTML markup
        "sent": sent,
        "send_result": send_result,
    }


# =============================================================================
# CORE GENERATION FUNCTIONS
# =============================================================================

async def generate_welcome_email(
    customer_id: Optional[str] = None,
    send: bool = False,
    to_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates a welcome email for a specific customer or a random new signup.
    
    Parameters:
    -----------
    customer_id : str, optional
        UUID of a specific customer. If None, picks a random new_signup or new customer.
    send : bool
        If True, actually sends the email via SendGrid after generating it.
    to_override : str, optional
        Send to this real email address instead of the customer's fake dataset email.
    """
    start = time.time()
    
    # Get the target customer — never 404 on a rotated ID
    if customer_id:
        customer = await _get_customer_or_mock(customer_id)
    else:
        # Pick a random new signup
        import random
        new_users = await dataset_manager.get_by_segment("new_signup", limit=50)
        if not new_users:
            new_users = await dataset_manager.get_by_segment("new", limit=50)
        if not new_users:
            new_users = await dataset_manager.get_random(count=1)
        
        if not new_users:
            raise RuntimeError("Dataset is empty — cannot generate email")
        
        customer = random.choice(new_users)
    
    # Build ML predictions first, then inject into prompt
    all_customers = await dataset_manager.get_all()
    if all_customers and _ML_AVAILABLE:
        try:
            train_ml_models(all_customers)
        except Exception:
            pass
    ml_predictions = run_ml_predictions(customer, all_customers)

    # Build prompt and generate
    prompt_data = build_welcome_email_prompt(customer, ml_predictions=ml_predictions)
    email_data = await ai_adapter.generate_email(prompt_data)
    
    generation_time_ms = (time.time() - start) * 1000
    
    # Optionally send
    send_result = None
    sent = False
    if send:
        send_result = await _send_via_sendgrid(customer, email_data, to_override=to_override)
        sent = send_result.get("success", False)
    
    result = _wrap_result(email_data, "welcome", customer, generation_time_ms, sent, send_result)
    result["ml_predictions"] = ml_predictions
    return result


async def generate_reengagement_email(
    customer_id: Optional[str] = None,
    send: bool = False,
    to_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates a re-engagement email for an inactive customer.
    If no customer_id given, picks a random inactive/at_risk customer.
    """
    start = time.time()
    
    if customer_id:
        customer = await _get_customer_or_mock(customer_id)
    else:
        import random
        inactive = await dataset_manager.get_by_segment("inactive", limit=100)
        at_risk  = await dataset_manager.get_by_segment("at_risk",  limit=50)
        candidates = inactive + at_risk
        
        if not candidates:
            candidates = await dataset_manager.get_random(count=1)
        
        customer = random.choice(candidates)
    
    all_customers = await dataset_manager.get_all()
    if all_customers and _ML_AVAILABLE:
        try:
            train_ml_models(all_customers)
        except Exception:
            pass
    ml_predictions = run_ml_predictions(customer, all_customers)

    prompt_data = build_reengagement_prompt(customer, ml_predictions=ml_predictions)
    email_data = await ai_adapter.generate_email(prompt_data)
    
    generation_time_ms = (time.time() - start) * 1000
    
    send_result = None
    sent = False
    if send:
        send_result = await _send_via_sendgrid(customer, email_data, to_override=to_override)
        sent = send_result.get("success", False)
    
    return _wrap_result(email_data, "reengagement", customer, generation_time_ms, sent, send_result)


async def generate_ab_variants(
    customer_id: Optional[str] = None,
    base_campaign_type: str = "reengagement",
    num_variants: int = DEFAULT_VARIANT_COUNT,
) -> Dict[str, Any]:
    """
    Generates multiple email variants for A/B testing.
    
    Parameters:
    -----------
    customer_id : str, optional
        Target customer. If None, picks a random active customer.
    base_campaign_type : str
        "welcome" or "reengagement" — the base goal of the variants
    num_variants : int
        How many variants to generate (default: 3)
        
    Returns:
    --------
    Result dict where email is a LIST of variant dicts
    """
    start = time.time()
    
    if customer_id:
        customer = await _get_customer_or_mock(customer_id)
    else:
        actives = await dataset_manager.get_by_segment("active", limit=100)
        if not actives:
            actives = await dataset_manager.get_random(count=1)
        import random
        customer = random.choice(actives)
    
    prompt_data = build_variant_test_prompt(
        customer=customer,
        base_campaign_type=base_campaign_type,
        num_variants=num_variants,
    )
    email_data = await ai_adapter.generate_email(prompt_data)
    
    generation_time_ms = (time.time() - start) * 1000
    
    logger.info(f"Generated {len(email_data) if isinstance(email_data, list) else 1} variants")
    
    return _wrap_result(email_data, "variant_test", customer, generation_time_ms)


async def generate_followup_email(
    customer_id: str,
    previous_email_subject: str,
    outcome: str,
    send: bool = False,
    to_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates a follow-up email based on how the previous email performed.
    
    Parameters:
    -----------
    customer_id : str
        REQUIRED — must specify which customer to follow up with
    previous_email_subject : str
        Subject line of the email we're following up on
    outcome : str
        "opened_no_click" | "not_opened" | "clicked_no_convert" | "converted"
    send : bool
        Whether to actually send via SendGrid
    to_override : str, optional
        A real email recipient override for demo sending
    """
    start = time.time()
    
    customer = await _get_customer_or_mock(customer_id)
    
    # Store outcome on the customer dictionary temporarily in case we need fallback mock email generation
    customer["_outcome"] = outcome
    
    prompt_data = build_followup_prompt(
        customer=customer,
        previous_email_subject=previous_email_subject,
        outcome=outcome,
    )
    # Ensure the adapter knows the outcome if it falls back to mock email generation
    prompt_data["outcome"] = outcome
    
    email_data = await ai_adapter.generate_email(prompt_data)
    
    generation_time_ms = (time.time() - start) * 1000
    
    send_result = None
    sent = False
    if send:
        send_result = await _send_via_sendgrid(customer, email_data, to_override=to_override)
        sent = send_result.get("success", False)
    
    return _wrap_result(email_data, "followup", customer, generation_time_ms, sent, send_result)


async def generate_rewrite(
    customer_id: str,
    original_email: str,
    feedback: str,
) -> Dict[str, Any]:
    """
    Rewrites an existing email based on user feedback.
    
    Parameters:
    -----------
    customer_id : str
        The customer the email is for
    original_email : str
        The original email content (JSON string or plain text)
    feedback : str
        What to change ("make it shorter", "more urgent tone", etc.)
    """
    start = time.time()
    
    customer = await _get_customer_or_mock(customer_id)
    
    prompt_data = build_rewrite_prompt(
        customer=customer,
        original_email=original_email,
        feedback=feedback,
    )
    email_data = await ai_adapter.generate_email(prompt_data)
    
    generation_time_ms = (time.time() - start) * 1000
    
    return _wrap_result(email_data, "rewrite", customer, generation_time_ms)


async def generate_custom_campaign(
    customer_id: Optional[str] = None,
    user_instructions: str = "",
    send: bool = False,
    to_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates a fully custom email based on free-form user instructions.
    
    Parameters:
    -----------
    customer_id : str, optional
        Target customer. If None, picks a random customer.
    user_instructions : str
        Free-form campaign description from the user
    send : bool
        Whether to send via SendGrid after generating
    """
    if not user_instructions.strip():
        raise ValueError("user_instructions cannot be empty for custom campaigns")
    
    start = time.time()
    
    if customer_id:
        customer = await _get_customer_or_mock(customer_id)
    else:
        customers = await dataset_manager.get_random(count=1)
        if not customers:
            raise RuntimeError("Dataset is empty")
        customer = customers[0]
    
    prompt_data = build_custom_campaign_prompt(
        customer=customer,
        user_instructions=user_instructions,
    )
    email_data = await ai_adapter.generate_email(prompt_data)
    
    generation_time_ms = (time.time() - start) * 1000
    
    send_result = None
    sent = False
    if send:
        send_result = await _send_via_sendgrid(customer, email_data, to_override=to_override)
        sent = send_result.get("success", False)
    
    return _wrap_result(email_data, "custom", customer, generation_time_ms, sent, send_result)


async def generate_campaign_email(
    campaign_type: str,
    customer_id: Optional[str] = None,
    send: bool = False,
    to_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    A unified, generic campaign runner that supports Welcome, Re-engagement,
    Cold Outreach, Newsletter, Product Launch, Sales Pitch, and Custom campaigns.
    """
    start = time.time()
    customer = await _get_customer_or_mock(customer_id)

    # Get the builder dynamically
    from backend.ai.prompt_builder import get_builder
    builder = get_builder(campaign_type)
    if not builder:
        raise ValueError(f"Unknown campaign type: {campaign_type}")

    prompt_data = builder(customer)
    email_data = await ai_adapter.generate_email(prompt_data)

    generation_time_ms = (time.time() - start) * 1000

    send_result = None
    sent = False
    if send:
        send_result = await _send_via_sendgrid(customer, email_data, to_override=to_override)
        sent = send_result.get("success", False)

    return _wrap_result(email_data, campaign_type, customer, generation_time_ms, sent, send_result)


# =============================================================================
# BATCH GENERATION — Generate emails for many customers at once
# =============================================================================

async def generate_batch_campaign(
    campaign_type: str,
    segment: Optional[str] = None,
    limit: int = 10,
    send: bool = False,
) -> Dict[str, Any]:
    """
    Generates emails for multiple customers in one call.
    
    Parameters:
    -----------
    campaign_type : str
        One of: "welcome", "reengagement", "custom"
    segment : str, optional
        Filter customers by segment. If None, uses best segment for campaign type.
    limit : int
        Maximum number of customers to generate emails for (default: 10)
        Keep this low to avoid API rate limits!
    send : bool
        Whether to send all generated emails
        
    Returns:
    --------
    Dict with "results" list (one per customer) and batch metadata
    
    [WARNING] WARNING: Generating 100 emails = 100 API calls.
    Keep limit under 20 during development to avoid hitting rate limits.
    """
    start = time.time()
    
    # Determine which segment to target based on campaign type
    if segment is None:
        segment_map = {
            "welcome":      "new_signup",
            "reengagement": "inactive",
            "custom":       "active",
        }
        segment = segment_map.get(campaign_type, "active")
    
    # Fetch target customers
    customers = await dataset_manager.get_by_segment(segment, limit=limit)
    if not customers:
        customers = await dataset_manager.get_random(count=min(limit, 5))
    
    if not customers:
        raise RuntimeError("No customers found for batch campaign")
    
    logger.info(f"Starting batch campaign: {campaign_type} for {len(customers)} customers")
    
    # Get the builder function
    builder_fn = get_builder(campaign_type)
    if builder_fn is None:
        raise ValueError(f"Unknown campaign type: {campaign_type}")
    
    # Generate emails one by one
    # (Not concurrent — to avoid hammering the AI API rate limits)
    results = []
    errors = []
    
    for i, customer in enumerate(customers):
        try:
            logger.info(f"Batch progress: {i+1}/{len(customers)}")
            
            prompt_data = builder_fn(customer)
            email_data = await ai_adapter.generate_email(prompt_data)
            
            send_result = None
            sent = False
            if send:
                send_result = await _send_via_sendgrid(customer, email_data)
                sent = send_result.get("success", False)
            
            results.append({
                "customer_id":   customer["id"],
                "customer_name": customer["name"],
                "email":         email_data,
                "sent":          sent,
                "send_result":   send_result,
                "success":       True,
            })
            
            # Small delay between calls to be respectful of rate limits
            import asyncio
            await asyncio.sleep(0.15)  # 150ms courtesy gap between API calls
            
        except Exception as e:
            logger.error(f"Failed to generate email for customer {customer.get('id')}: {e}")
            errors.append({
                "customer_id":   customer.get("id"),
                "customer_name": customer.get("name"),
                "error":         str(e),
                "success":       False,
            })
    
    total_time_ms = (time.time() - start) * 1000
    
    return {
        "success": True,
        "campaign_type": campaign_type,
        "segment_targeted": segment,
        "total_requested": len(customers),
        "total_generated": len(results),
        "total_failed": len(errors),
        "total_time_ms": round(total_time_ms, 2),
        "avg_time_per_email_ms": round(total_time_ms / max(len(customers), 1), 2),
        "results": results,
        "errors": errors,
    }


# =============================================================================
# SENDGRID INTEGRATION
# =============================================================================

async def _send_via_sendgrid(
    customer: Dict[str, Any],
    email_data: Dict[str, Any],
    to_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends a generated email to the customer via SendGrid.
    
    Parameters:
    -----------
    customer : dict
        The customer receiving the email (needs "email" and "name" fields)
    email_data : dict
        The generated email JSON from AI
    to_override : str, optional
        If provided, sends to this real email address instead of customer["email"].
        Use this for demos since dataset emails (e.g. john@example.com) are fake.
    """
    import asyncio
    from backend.config import (
        EMAIL_STUB_MODE,
        SENDGRID_API_KEY,
        FROM_EMAIL,
        FROM_NAME,
    )
    
    # Determine actual recipient
    recipient_email = to_override if to_override else customer.get("email", "")
    recipient_name  = customer.get("name", "Valued Customer")
    
    # --- STUB MODE (default until you add a real SendGrid key) ---
    if EMAIL_STUB_MODE or not SENDGRID_API_KEY:
        logger.info(
            f"[STUB] Would send '{email_data.get('subject_line')}' "
            f"to {recipient_email}"
        )
        return {
            "success": True,
            "message_id": f"stub-{customer.get('id', 'unknown')[:8]}",
            "status_code": 202,
            "error": None,
            "stub_mode": True,
            "note": "Email NOT actually sent. Set EMAIL_STUB_MODE=false and add SENDGRID_API_KEY to send real emails.",
        }
    
    # --- REAL SENDGRID SEND ---
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent
    except ImportError:
        return {
            "success": False,
            "error": "sendgrid package not installed. Run: pip install sendgrid",
            "message_id": None,
            "status_code": None,
        }
    
    # Build the email body from our AI-generated JSON
    body = email_data.get("body", {})
    
    # Compose HTML email body
    html_body = _compose_html_email(email_data, customer)
    
    # Plain text fallback (for email clients that don't render HTML)
    plain_text = (
        f"{body.get('greeting', '')}\n\n"
        f"{body.get('opening', '')}\n\n"
        f"{body.get('main_content', '')}\n\n"
        f"{body.get('call_to_action', '')} → {body.get('cta_url', '')}\n\n"
        f"{body.get('closing', '')}"
    )
    
    # Create the SendGrid mail object
    message = Mail(
        from_email=Email(FROM_EMAIL, FROM_NAME),
        to_emails=To(recipient_email, recipient_name),
        subject=email_data.get("subject_line", "Hello from us"),
        plain_text_content=Content("text/plain", plain_text),
        html_content=HtmlContent(html_body),
    )
    
    # Optional: Add preview text via custom header
    preview_text = email_data.get("preview_text", "")
    if preview_text:
        # Preview text trick: hidden text at top of email body
        # Email clients show this as the "preview" in inbox view
        pass  # Already included in _compose_html_email
    
    # Send it!
    loop = asyncio.get_event_loop()
    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        
        response = await loop.run_in_executor(
            None,
            lambda: sg.send(message)
        )
        
        if response.status_code == 202:
            logger.info(
                f"[OK] Email sent via SendGrid to {customer['email']} "
                f"(message_id: {response.headers.get('X-Message-Id', 'unknown')})"
            )
            return {
                "success": True,
                "message_id": response.headers.get("X-Message-Id", ""),
                "status_code": response.status_code,
                "error": None,
                "stub_mode": False,
            }
        else:
            logger.error(f"SendGrid returned status {response.status_code}: {response.body}")
            return {
                "success": False,
                "message_id": None,
                "status_code": response.status_code,
                "error": f"SendGrid returned status {response.status_code}",
            }
            
    except Exception as e:
        logger.error(f"SendGrid send failed: {e}")
        return {
            "success": False,
            "message_id": None,
            "status_code": None,
            "error": str(e),
        }


def _compose_html_email(email_data: Dict, customer: Dict) -> str:
    """
    Composes a beautiful, campaign-type-aware HTML email from AI-generated JSON parts.

    Key design decisions:
    - Campaign-type-specific gradient colors so each email type looks distinct
    - Inline CSS only (Gmail strips <head> styles but preserves inline)
    - Table-based layout (most compatible across ALL email clients)
    - Preview text hidden trick for inbox snippet
    - Stylistic suggestions box for rewrite/custom campaigns
    """
    body         = email_data.get("body", {})
    preview_txt  = email_data.get("preview_text", "")
    campaign_type = email_data.get("campaign_type", "welcome")
    cta_text     = body.get("call_to_action", "Learn More")
    cta_url      = body.get("cta_url", "https://example.com/start")
    main_content = body.get("main_content", "").replace("\n\n", "</p><p>").replace("\n", "<br>")
    metadata     = email_data.get("metadata", {})

    # Campaign-type-specific colors and banner labels
    campaign_themes = {
        "welcome": {
            "gradient": "linear-gradient(135deg,#0ea5e9,#6366f1)",
            "accent":   "#6366f1",
            "badge_bg": "#e0e7ff",
            "badge_txt": "#4338ca",
            "banner_label": "NEW MEMBER",
            "banner_title": f"Welcome to the Family, {customer.get('first_name', 'there')}!",
        },
        "reengagement": {
            "gradient": "linear-gradient(135deg,#f59e0b,#ef4444)",
            "accent":   "#ef4444",
            "badge_bg": "#fef9c3",
            "badge_txt": "#92400e",
            "banner_label": "WE MISS YOU",
            "banner_title": "We Saved Something Special for You",
        },
        "followup": {
            "gradient": "linear-gradient(135deg,#10b981,#0ea5e9)",
            "accent":   "#10b981",
            "badge_bg": "#d1fae5",
            "badge_txt": "#065f46",
            "banner_label": "FOLLOWING UP",
            "banner_title": "Just Checking In",
        },
        "rewrite": {
            "gradient": "linear-gradient(135deg,#8b5cf6,#ec4899)",
            "accent":   "#8b5cf6",
            "badge_bg": "#ede9fe",
            "badge_txt": "#5b21b6",
            "banner_label": "REWRITTEN",
            "banner_title": "Enhanced Email Version",
        },
        "custom": {
            "gradient": "linear-gradient(135deg,#14b8a6,#6366f1)",
            "accent":   "#14b8a6",
            "badge_bg": "#ccfbf1",
            "badge_txt": "#115e59",
            "banner_label": "CUSTOM CAMPAIGN",
            "banner_title": "A Personal Message for You",
        },
        "variant_test": {
            "gradient": "linear-gradient(135deg,#f97316,#8b5cf6)",
            "accent":   "#f97316",
            "badge_bg": "#ffedd5",
            "badge_txt": "#9a3412",
            "banner_label": "A/B TEST VARIANT",
            "banner_title": "Optimized Email Experience",
        },
        "cold_outreach": {
            "gradient": "linear-gradient(135deg,#4f46e5,#06b6d4)",
            "accent":   "#4f46e5",
            "badge_bg": "#e0e7ff",
            "badge_txt": "#4338ca",
            "banner_label": "COLD OUTREACH",
            "banner_title": "Personalized Outreach Proposal",
        },
        "newsletter": {
            "gradient": "linear-gradient(135deg,#10b981,#3b82f6)",
            "accent":   "#10b981",
            "badge_bg": "#d1fae5",
            "badge_txt": "#065f46",
            "banner_label": "WEEKLY NEWSLETTER",
            "banner_title": "Your Interest Insights & Updates",
        },
        "product_launch": {
            "gradient": "linear-gradient(135deg,#ec4899,#f43f5e)",
            "accent":   "#ec4899",
            "badge_bg": "#fce7f3",
            "badge_txt": "#be185d",
            "banner_label": "NEW PRODUCT RELEASE",
            "banner_title": "Introducing Our Latest Innovation",
        },
        "sales_pitch": {
            "gradient": "linear-gradient(135deg,#f59e0b,#ea580c)",
            "accent":   "#ea580c",
            "badge_bg": "#fef3c7",
            "badge_txt": "#d97706",
            "banner_label": "EXCLUSIVE OFFER",
            "banner_title": "Unlock Your Custom Discount Inside",
        },
    }
    theme = campaign_themes.get(campaign_type, campaign_themes["welcome"])
    gradient  = theme["gradient"]
    accent    = theme["accent"]
    badge_bg  = theme["badge_bg"]
    badge_txt = theme["badge_txt"]
    banner_label = theme["banner_label"]
    banner_title = theme["banner_title"]

    # Stylistic suggestions block (shown only for rewrite/custom)
    style_block = ""
    stylistic = metadata.get("stylistic_suggestions", {})
    if stylistic and campaign_type in ("rewrite", "custom"):
        fig = stylistic.get("figure_of_speech_used", "")
        pos = stylistic.get("parts_of_speech_adjustments", "")
        hooks = stylistic.get("alternative_hooks", [])
        hooks_html = "".join(
            f'<li style="margin:4px 0;font-size:13px;color:#374151;">{h}</li>'
            for h in hooks
        )
        style_block = f"""
          <!-- Stylistic Suggestions Box -->
          <tr>
            <td style="padding:0 40px 28px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:{badge_bg};border-left:4px solid {accent};border-radius:8px;padding:18px 20px;">
                <tr>
                  <td>
                    <div style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:{accent};text-transform:uppercase;margin-bottom:10px;">
                      Writing Style Insights
                    </div>
                    {"<p style='margin:0 0 6px;font-size:13px;color:#374151;'><strong>Figure of speech:</strong> " + fig + "</p>" if fig else ""}
                    {"<p style='margin:0 0 6px;font-size:13px;color:#374151;'><strong>Language style:</strong> " + pos + "</p>" if pos else ""}
                    {"<p style='margin:4px 0 4px;font-size:13px;color:#374151;'><strong>Alternative subject lines:</strong></p><ul style='margin:4px 0 0 0;padding-left:18px;'>" + hooks_html + "</ul>" if hooks else ""}
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""

    # Build Attachments block
    attachments = email_data.get("attachments", [])
    attachments_html = ""
    if attachments:
        cards = []
        for a in attachments:
            a_type = a.get("type", "link").lower()
            title = a.get("title", "Resource Attachment")
            url = a.get("url", "https://example.com")
            thumb = a.get("thumbnail_url")

            # Fallback placeholder images for demo clarity
            if a_type == "image" and not thumb:
                thumb = "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=600&q=80"
            elif a_type == "video" and not thumb:
                thumb = "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?auto=format&fit=crop&w=600&q=80"

            if a_type == "pdf":
                cards.append(f"""
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;border:1px solid #e2e8f0;border-radius:10px;background-color:#f8fafc;padding:12px 16px;">
                  <tr>
                    <td width="36" style="font-size:24px;text-align:center;line-height:1;color:#ef4444;vertical-align:middle;">📕</td>
                    <td style="padding-left:12px;vertical-align:middle;">
                      <div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:2px;">{title}</div>
                      <div style="font-size:11px;color:#64748b;">PDF Document • Direct Download</div>
                    </td>
                    <td align="right" style="vertical-align:middle;">
                      <a href="{url}" style="font-size:12px;font-weight:700;color:#ffffff;background:{gradient};text-decoration:none;padding:8px 14px;border-radius:6px;display:inline-block;box-shadow:0 2px 4px rgba(0,0,0,0.05);">Download</a>
                    </td>
                  </tr>
                </table>
                """)
            elif a_type == "video":
                thumb_block = ""
                if thumb:
                    thumb_block = f"""
                    <tr>
                      <td style="position:relative;background:#000000;">
                        <a href="{url}" style="display:block;text-align:center;">
                          <img src="{thumb}" width="100%" style="display:block;opacity:0.85;border-bottom:1px solid #e2e8f0;max-height:180px;object-fit:cover;" alt="{title}" />
                          <div style="position:absolute;top:50%;left:50%;margin-top:-22px;margin-left:-22px;width:44px;height:44px;background:#ef4444;border-radius:50%;text-align:center;line-height:44px;color:#ffffff;font-size:18px;font-weight:bold;box-shadow:0 4px 10px rgba(239,68,68,0.4);">▶</div>
                        </a>
                      </td>
                    </tr>
                    """
                cards.append(f"""
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;border:1px solid #e2e8f0;border-radius:10px;background-color:#f8fafc;overflow:hidden;">
                  {thumb_block}
                  <tr>
                    <td style="padding:12px 16px;">
                      <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                          <td style="vertical-align:middle;">
                            <div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:2px;">🎬 {title}</div>
                            <div style="font-size:11px;color:#64748b;">Video Walkthrough • Watch Demo</div>
                          </td>
                          <td align="right" style="vertical-align:middle;">
                            <a href="{url}" style="font-size:12px;font-weight:700;color:#ffffff;background:{gradient};text-decoration:none;padding:8px 14px;border-radius:6px;display:inline-block;box-shadow:0 2px 4px rgba(0,0,0,0.05);">Watch</a>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
                """)
            elif a_type == "calendar":
                cards.append(f"""
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;border:1px solid #e2e8f0;border-radius:10px;background-color:#f8fafc;padding:12px 16px;">
                  <tr>
                    <td width="36" style="font-size:24px;text-align:center;line-height:1;color:#2563eb;vertical-align:middle;">📅</td>
                    <td style="padding-left:12px;vertical-align:middle;">
                      <div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:2px;">{title}</div>
                      <div style="font-size:11px;color:#64748b;">Calendar Invite • Add to Schedule</div>
                    </td>
                    <td align="right" style="vertical-align:middle;">
                      <a href="{url}" style="font-size:12px;font-weight:700;color:#ffffff;background:{gradient};text-decoration:none;padding:8px 14px;border-radius:6px;display:inline-block;box-shadow:0 2px 4px rgba(0,0,0,0.05);">Add Event</a>
                    </td>
                  </tr>
                </table>
                """)
            elif a_type == "image":
                img_src = thumb if thumb else url
                cards.append(f"""
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;background-color:#ffffff;">
                  <tr>
                    <td>
                      <a href="{url}" style="display:block;">
                        <img src="{img_src}" width="100%" style="display:block;max-height:220px;object-fit:cover;" alt="{title}" />
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:10px 14px;background-color:#f8fafc;border-top:1px solid #e2e8f0;">
                      <div style="font-size:13px;font-weight:600;color:#475569;text-align:center;">📷 {title}</div>
                    </td>
                  </tr>
                </table>
                """)
            else: # link
                cards.append(f"""
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;border:1px solid #e2e8f0;border-radius:10px;background-color:#f8fafc;padding:12px 16px;">
                  <tr>
                    <td width="28" style="font-size:20px;text-align:center;vertical-align:middle;">🔗</td>
                    <td style="padding-left:12px;vertical-align:middle;">
                      <div style="margin-bottom:2px;"><a href="{url}" style="font-size:14px;font-weight:700;color:{accent};text-decoration:none;">{title}</a></div>
                      <div style="font-size:11px;color:#64748b;">Useful Link • Visit Web Resource</div>
                    </td>
                  </tr>
                </table>
                """)
        
        cards_html = "".join(cards)
        attachments_html = f"""
        <!-- === ATTACHMENTS SECTION === -->
        <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin-top:8px;margin-bottom:24px;">
          <tr>
            <td>
              <div style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#94a3b8;text-transform:uppercase;margin-bottom:12px;border-bottom:1px solid #f1f5f9;padding-bottom:6px;">
                Campaign Attachments
              </div>
              {cards_html}
            </td>
          </tr>
        </table>
        """

    # Recommended send time badge
    send_time = metadata.get("recommended_send_time", "")
    open_boost = metadata.get("estimated_open_rate_boost", "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{email_data.get('subject_line', '')}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased;">

  <!-- Preview text (invisible — appears in inbox snippet) -->
  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
    {preview_txt}&nbsp;&#847;&nbsp;&#847;&nbsp;&#847;&nbsp;&#847;&nbsp;&#847;&nbsp;&#847;&nbsp;&#847;
  </div>

  <!-- Outer wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background-color:#f1f5f9;padding:40px 20px;">
    <tr>
      <td align="center">
        <!-- Email card (max 600px) -->
        <table width="600" cellpadding="0" cellspacing="0" role="presentation"
               style="background-color:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);border:1px solid #e2e8f0;max-width:600px;">

          <!-- === BANNER === -->
          <tr>
            <td style="background:{gradient};padding:48px 40px 40px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
                <tr>
                  <td>
                    <!-- Campaign label pill -->
                    <table cellpadding="0" cellspacing="0" role="presentation" style="margin-bottom:16px;">
                      <tr>
                        <td style="background:rgba(255,255,255,0.2);border-radius:100px;padding:5px 14px;">
                          <span style="font-size:10px;font-weight:800;letter-spacing:2px;color:#ffffff;text-transform:uppercase;">
                            {banner_label}
                          </span>
                        </td>
                      </tr>
                    </table>
                    <!-- Banner headline -->
                    <h1 style="margin:0 0 8px 0;font-size:28px;font-weight:800;color:#ffffff;line-height:1.2;letter-spacing:-0.5px;">
                      {banner_title}
                    </h1>
                    <p style="margin:0;font-size:14px;color:rgba(255,255,255,0.85);line-height:1.5;">
                      {preview_txt[:80] + '...' if len(preview_txt) > 80 else preview_txt}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- === BRAND BAR === -->
          <tr>
            <td style="padding:20px 40px;border-bottom:1px solid #f1f5f9;">
              <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
                <tr>
                  <td>
                    <span style="font-size:13px;font-weight:700;letter-spacing:1px;color:{accent};text-transform:uppercase;">
                      AI Campaign Agent
                    </span>
                  </td>
                  <td align="right">
                    <span style="font-size:12px;color:#94a3b8;">
                      {datetime.now(timezone.utc).strftime('%B %d, %Y')}
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- === BODY CONTENT === -->
          <tr>
            <td style="padding:32px 40px 8px 40px;">
              <!-- Subject as headline -->
              <h2 style="margin:0 0 20px 0;font-size:20px;color:#0f172a;font-weight:700;line-height:1.35;letter-spacing:-0.3px;">
                {email_data.get('subject_line', 'Important Update')}
              </h2>
              <!-- Greeting -->
              <p style="margin:0 0 16px 0;font-size:16px;color:#1e293b;font-weight:600;line-height:1.5;">
                {body.get('greeting', 'Hi there,')}
              </p>
              <!-- Opening paragraph -->
              <p style="margin:0 0 18px 0;font-size:15px;color:#475569;line-height:1.75;">
                {body.get('opening', '')}
              </p>
              <!-- Main content -->
              <p style="margin:0 0 28px 0;font-size:15px;color:#475569;line-height:1.75;">
                {main_content}
              </p>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" role="presentation" style="margin:8px 0 32px 0;">
                <tr>
                  <td style="border-radius:10px;background:{gradient};" align="center">
                    <a href="{cta_url}"
                       style="display:inline-block;padding:16px 36px;font-size:15px;font-weight:700;
                              color:#ffffff;text-decoration:none;border-radius:10px;letter-spacing:0.4px;
                              white-space:nowrap;">
                      {cta_text}
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- === CLOSING === -->
          <tr>
            <td style="padding:0 40px 28px 40px;">
              <p style="margin:0;font-size:14px;color:#64748b;line-height:1.7;font-style:italic;">
                {body.get('closing', 'Warm regards,<br>The Team')}
              </p>
            </td>
          </tr>

          {style_block}

          {attachments_html}

          <!-- === METADATA BADGES (send time + open rate) === -->
          {"<tr><td style='padding:0 40px 28px 40px;'><table width='100%' cellpadding='0' cellspacing='0'><tr>" + ("<td style='padding:8px 16px;background:" + badge_bg + ";border-radius:8px;margin-right:8px;'><span style='font-size:12px;font-weight:600;color:" + badge_txt + ";'>Best send time: " + send_time + "</span></td>" if send_time else "") + ("<td align='right'><span style='font-size:12px;font-weight:600;color:#059669;'>Predicted open rate boost: " + open_boost + "</span></td>" if open_boost else "") + "</tr></table></td></tr>" if send_time or open_boost else ""}

          <!-- === FOOTER === -->
          <tr>
            <td style="background-color:#f8fafc;border-top:1px solid #e2e8f0;padding:28px 40px;text-align:center;">
              <p style="margin:0 0 10px 0;font-size:13px;color:#64748b;font-weight:600;">
                Connect with us
              </p>
              <p style="margin:0 0 16px 0;font-size:12px;color:#94a3b8;">
                <a href="#" style="color:{accent};text-decoration:none;font-weight:600;margin:0 8px;">Website</a>&nbsp;•&nbsp;
                <a href="#" style="color:{accent};text-decoration:none;font-weight:600;margin:0 8px;">Support</a>&nbsp;•&nbsp;
                <a href="#" style="color:{accent};text-decoration:none;font-weight:600;margin:0 8px;">Privacy</a>
              </p>
              <p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.6;">
                You are receiving this based on your profile interests.<br>
                &copy; {datetime.now(timezone.utc).year} AI Campaign Agent. All rights reserved.<br>
                <a href="#" style="color:#94a3b8;text-decoration:underline;">Unsubscribe</a>&nbsp;&nbsp;|&nbsp;&nbsp;
                <a href="#" style="color:#94a3b8;text-decoration:underline;">Manage preferences</a>
              </p>
            </td>
          </tr>

        </table>
        <!-- End email card -->
      </td>
    </tr>
  </table>
</body>
</html>""".strip()


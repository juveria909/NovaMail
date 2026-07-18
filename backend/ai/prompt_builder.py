"""
prompt_builder.py — PART 2: Dynamic Prompt Assembly
=====================================================
This file is the CONDUCTOR of the AI operation.

It takes:
  - A customer profile (from the dataset)
  - A campaign type (welcome, reengagement, etc.)
  - Optional parameters (number of variants, previous email, feedback)

And produces:
  - A complete, ready-to-send prompt for the Gemini API
  - Structured as: [system_prompt, user_message]

WHY TWO-PART STRUCTURE? (system_prompt vs user_message)
--------------------------------------------------------
Most modern AI APIs accept two separate message types:

SYSTEM PROMPT: "Instructions to the AI — who you are, what rules you follow"
  → Set once. The AI's "job description".
  
USER MESSAGE: "The specific task for THIS request"
  → Changes every time. The actual request.

Think of it like hiring an expert:
  System prompt = "You are a plumber. Always wear safety gear. Always give quotes."
  User message = "Fix the sink in apartment 4B."

The expert (AI) combines both to know HOW to work AND WHAT to do this time.

Keeping them separate:
  1. Makes prompts cleaner and easier to debug
  2. Some AI APIs cache system prompts for speed (Gemini supports this)
  3. Allows us to vary user messages without rewriting the whole system prompt

RETURNED FORMAT:
----------------
Every build_*() function returns a dict:
{
    "system_prompt": "str — combined relevant system blocks",
    "user_message": "str — specific task for this request",
    "campaign_type": "str — for logging/tracking",
    "customer_id": "str — for response correlation",
    "is_multi_variant": bool — whether to expect a JSON array response
}
"""

from typing import Optional
import logging

from backend.ai.system_prompts import (
    core_identity_block,
    output_format_block,
    ml_predictions_block,
    customer_profile_block,
    welcome_campaign_block,
    reengagement_campaign_block,
    ab_variant_campaign_block,
    followup_campaign_block,
    rewrite_campaign_block,
    custom_campaign_block,
    cold_outreach_campaign_block,
    newsletter_campaign_block,
    product_launch_campaign_block,
    sales_pitch_campaign_block,
    quality_constraints_block,
)
from backend.config import DEFAULT_VARIANT_COUNT

logger = logging.getLogger(__name__)


# =============================================================================
# INTERNAL HELPER — Assembles system prompt from selected blocks
# =============================================================================

def _assemble_system_prompt(*blocks: str) -> str:
    """
    Joins prompt blocks with clear section separators.
    
    The "===" separator lines help the AI visually parse sections.
    Without separators, a long prompt becomes one wall of text 
    and the AI may miss instructions buried in the middle.
    
    Parameters:
    -----------
    *blocks : str
        Any number of prompt block strings to join
        
    Returns:
    --------
    Single combined system prompt string
    """
    separator = "\n\n" + "="*60 + "\n\n"
    return separator.join(block.strip() for block in blocks if block.strip())


def _build_base_system_prompt(
    customer: dict,
    campaign_block: str,
    ml_predictions: Optional[dict] = None,
) -> str:
    """
    Builds the standard system prompt used by most campaign types.
    Every prompt gets: identity + customer profile + ML signals + campaign block + quality + output format.

    ml_predictions: if provided (from XGBoost + CF models), a ML intelligence
    block is injected between the customer profile and the campaign instructions.
    The output format block is ALWAYS LAST.
    """
    return _assemble_system_prompt(
        core_identity_block(),
        customer_profile_block(customer),
        ml_predictions_block(ml_predictions) if ml_predictions else "",
        campaign_block,
        quality_constraints_block(),
        output_format_block(),
    )


# =============================================================================
# PUBLIC FUNCTIONS — One per campaign type
# =============================================================================

def build_welcome_email_prompt(customer: dict, ml_predictions: Optional[dict] = None) -> dict:
    system_prompt = _build_base_system_prompt(customer, welcome_campaign_block(), ml_predictions)
    user_message = f"""
Write a welcome email for {customer.get('first_name', 'this customer')}.

They just signed up {customer.get('account_age_days', 0)} days ago.
Their top interests are: {', '.join(customer.get('interests', [])[:3])}.

Make them feel excited, seen, and welcomed.
Remember: output ONLY the JSON object, nothing else.
""".strip()
    logger.debug(f"Built welcome prompt for customer: {customer.get('id', 'unknown')}")
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "welcome",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": False,
    }


def build_reengagement_prompt(customer: dict, ml_predictions: Optional[dict] = None) -> dict:
    system_prompt = _build_base_system_prompt(customer, reengagement_campaign_block(), ml_predictions)
    from datetime import datetime, timezone
    last_active_str = customer.get("last_active", "")
    try:
        last_active = datetime.fromisoformat(last_active_str.replace("Z", "+00:00"))
        days_inactive = (datetime.now(timezone.utc) - last_active).days
        inactive_context = f"They haven't been active for approximately {days_inactive} days."
    except (ValueError, AttributeError):
        inactive_context = "They have been inactive for some time."
    purchase_history = customer.get("purchase_history", [])
    purchase_context = ""
    if purchase_history:
        last_purchase = purchase_history[-1]
        purchase_context = (
            f"Their last purchase was a '{last_purchase['item']}' "
            f"on {last_purchase['date']} — you can reference this naturally."
        )
    user_message = f"""
Write a re-engagement email for {customer.get('first_name', 'this customer')}.

{inactive_context}
Their email open rate has been {customer.get('email_behavior', {}).get('open_rate', 0) * 100:.0f}% — 
this needs to be a compelling subject line they actually open.

{purchase_context}

Interests to reference: {', '.join(customer.get('interests', [])[:2])}.

Approach with empathy. Make them curious. Give them a reason to come back.
Output ONLY the JSON object, nothing else.
""".strip()
    logger.debug(f"Built reengagement prompt for customer: {customer.get('id', 'unknown')}")
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "reengagement",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": False,
    }


def build_variant_test_prompt(
    customer: dict, 
    base_campaign_type: str = "reengagement",
    num_variants: int = DEFAULT_VARIANT_COUNT
) -> dict:
    """
    Builds a prompt to generate multiple email variants for A/B testing.
    
    Parameters:
    -----------
    customer : dict
        Enriched customer profile
    base_campaign_type : str
        The underlying campaign type to base variants on.
        Options: "welcome", "reengagement", "custom"
    num_variants : int
        How many variants to generate (default: 3 from config)
        
    Returns:
    --------
    Dict with is_multi_variant=True — tells json_extractor to expect a JSON array
    """
    
    # Include the base campaign context AND the variant instructions
    base_block = {
        "welcome": welcome_campaign_block(),
        "reengagement": reengagement_campaign_block(),
    }.get(base_campaign_type, reengagement_campaign_block())
    
    system_prompt = _assemble_system_prompt(
        core_identity_block(),
        customer_profile_block(customer),
        base_block,
        ab_variant_campaign_block(num_variants=num_variants),
        quality_constraints_block(),
        output_format_block(),
    )
    
    user_message = f"""
Generate {num_variants} distinctly different email variants for {customer.get('first_name', 'this customer')}.

Each variant must take a noticeably different approach:
  - Variant A: Lead with clear benefits/value
  - Variant B: Lead with emotion/story  
  - Variant C: Create urgency or FOMO
  {'- Variants D+: Creative/experimental angles' if num_variants > 3 else ''}

All variants target the same customer and goal but use completely different hooks, 
tone, and framing.

Output ONLY a JSON array of {num_variants} email objects. Nothing else.
""".strip()
    
    logger.debug(f"Built {num_variants}-variant prompt for customer: {customer.get('id', 'unknown')}")
    
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "variant_test",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": True,
        "expected_variant_count": num_variants,
    }


def build_followup_prompt(
    customer: dict,
    previous_email_subject: str,
    outcome: str,
    ml_predictions: Optional[dict] = None,
) -> dict:
    valid_outcomes = ["opened_no_click", "not_opened", "clicked_no_convert", "converted"]
    if outcome not in valid_outcomes:
        logger.warning(f"Invalid outcome '{outcome}' — defaulting to 'not_opened'")
        outcome = "not_opened"
    system_prompt = _build_base_system_prompt(
        customer,
        followup_campaign_block(previous_email_subject, outcome),
        ml_predictions,
    )
    outcome_user_guidance = {
        "opened_no_click": "Address potential objections. Make the value proposition crystal clear.",
        "not_opened": "Use a completely fresh angle. Different subject, different hook, same goal.",
        "clicked_no_convert": "Remove friction. Address doubts. Offer an easier path to yes.",
        "converted": "Celebrate their decision. Set expectations. Introduce the next step.",
    }
    user_message = f"""
Write a follow-up email for {customer.get('first_name', 'this customer')}.

Previous email subject: "{previous_email_subject}"
What happened: {outcome.replace('_', ' ').upper()}

Your strategy for this follow-up: {outcome_user_guidance.get(outcome, '')}

Keep it short (under 150 words body) — follow-up emails should be punchy, not exhaustive.
Output ONLY the JSON object, nothing else.
""".strip()
    logger.debug(f"Built followup prompt — outcome: {outcome}, customer: {customer.get('id', 'unknown')}")
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "followup",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": False,
        "followup_outcome": outcome,
    }


def build_rewrite_prompt(
    customer: dict,
    original_email: str,
    feedback: str,
    ml_predictions: Optional[dict] = None,
) -> dict:
    system_prompt = _build_base_system_prompt(
        customer,
        rewrite_campaign_block(original_email, feedback),
        ml_predictions,
    )
    user_message = f"""
Rewrite the email above for {customer.get('first_name', 'this customer')}.

Apply this feedback precisely: {feedback}

Don't explain what you changed. Just output the rewritten email as a JSON object.
Output ONLY the JSON object, nothing else.
""".strip()
    logger.debug(f"Built rewrite prompt for customer: {customer.get('id', 'unknown')}")
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "rewrite",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": False,
        "rewrite_feedback": feedback,
    }


def build_custom_campaign_prompt(
    customer: dict,
    user_instructions: str,
    ml_predictions: Optional[dict] = None,
) -> dict:
    system_prompt = _build_base_system_prompt(customer, custom_campaign_block(user_instructions), ml_predictions)
    user_message = f"""
Write a custom campaign email for {customer.get('first_name', 'this customer')}.

Follow the campaign instructions exactly while personalizing using the customer profile above.
Output ONLY the JSON object, nothing else.
""".strip()
    logger.debug(f"Built custom campaign prompt for customer: {customer.get('id', 'unknown')}")
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "custom",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": False,
        "user_instructions": user_instructions,
    }


def build_cold_outreach_prompt(customer: dict, ml_predictions: Optional[dict] = None) -> dict:
    system_prompt = _build_base_system_prompt(customer, cold_outreach_campaign_block(), ml_predictions)
    user_message = f"""
Write a B2B cold outreach email for {customer.get('first_name', 'this customer')} personalization.
Address their interest in: {', '.join(customer.get('interests', [])[:3])}.
Establish quick value and offer a useful download/view asset.
Output ONLY the JSON object, nothing else.
""".strip()
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "cold_outreach",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": False,
    }


def build_newsletter_prompt(customer: dict, ml_predictions: Optional[dict] = None) -> dict:
    system_prompt = _build_base_system_prompt(customer, newsletter_campaign_block(), ml_predictions)
    user_message = f"""
Write a newsletter for {customer.get('first_name', 'this customer')}.
Incorporate their interests in: {', '.join(customer.get('interests', [])[:3])}.
Include 2-3 links or PDF/video recommendations in the attachments.
Output ONLY the JSON object, nothing else.
""".strip()
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "newsletter",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": False,
    }


def build_product_launch_prompt(customer: dict, ml_predictions: Optional[dict] = None) -> dict:
    system_prompt = _build_base_system_prompt(customer, product_launch_campaign_block(), ml_predictions)
    user_message = f"""
Write a product launch email for {customer.get('first_name', 'this customer')}.
Connect the product release benefit to their interest: {', '.join(customer.get('interests', [])[:3])}.
Provide an image and a video walkthrough in the attachments.
Output ONLY the JSON object, nothing else.
""".strip()
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "product_launch",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": False,
    }


def build_sales_pitch_prompt(customer: dict, ml_predictions: Optional[dict] = None) -> dict:
    system_prompt = _build_base_system_prompt(customer, sales_pitch_campaign_block(), ml_predictions)
    user_message = f"""
Write a promotional sales pitch email for {customer.get('first_name', 'this customer')}.
Leverage their previous purchase history or interests to present a custom discount or offer.
Create urgency, and include a claim link in the attachments.
Output ONLY the JSON object, nothing else.
""".strip()
    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "campaign_type": "sales_pitch",
        "customer_id": customer.get("id", ""),
        "is_multi_variant": False,
    }


# =============================================================================
# PROMPT REGISTRY — Maps campaign type strings to builder functions
# Used by email_generator.py to dispatch the right builder
# =============================================================================

PROMPT_BUILDERS = {
    "welcome":        build_welcome_email_prompt,
    "reengagement":   build_reengagement_prompt,
    "variant_test":   build_variant_test_prompt,
    "followup":       build_followup_prompt,
    "rewrite":        build_rewrite_prompt,
    "custom":         build_custom_campaign_prompt,
    "cold_outreach":  build_cold_outreach_prompt,
    "newsletter":     build_newsletter_prompt,
    "product_launch": build_product_launch_prompt,
    "sales_pitch":    build_sales_pitch_prompt,
}


def get_builder(campaign_type: str):
    """
    Returns the right prompt builder function for a given campaign type.
    
    Parameters:
    -----------
    campaign_type : str
        One of: "welcome", "reengagement", "variant_test", "followup", "rewrite", "custom"
        
    Returns:
    --------
    The builder function, or None if campaign_type is not recognized
    
    Example:
    --------
    builder = get_builder("welcome")
    prompt_data = builder(customer)
    """
    builder = PROMPT_BUILDERS.get(campaign_type)
    if builder is None:
        logger.warning(
            f"Unknown campaign type: '{campaign_type}'. "
            f"Valid types: {list(PROMPT_BUILDERS.keys())}"
        )
    return builder

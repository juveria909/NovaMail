"""
validators.py — Input Validation Helpers
==========================================
Centralizes all validation logic so main.py stays clean.

WHY SEPARATE VALIDATION?
--------------------------
FastAPI's Pydantic models validate DATA TYPES (str, int, bool).
But they can't validate BUSINESS RULES like:
  - "Is this email address actually a valid format?"
  - "Is this customer segment name one we support?"
  - "Is this campaign outcome string one the AI understands?"

This file handles those business-rule validations.

Each function either:
  - Returns True/False (for simple checks)
  - Raises ValueError with a clear message (for critical failures)
"""

import re
from typing import Optional


# =============================================================================
# CONSTANTS — Valid values for all enum-like fields
# =============================================================================

VALID_CAMPAIGN_TYPES = {
    "welcome",
    "reengagement",
    "variant_test",
    "followup",
    "rewrite",
    "custom",
}

VALID_SEGMENTS = {
    "new_signup",
    "new",
    "active",
    "inactive",
    "high_value",
    "at_risk",
}

VALID_FOLLOWUP_OUTCOMES = {
    "opened_no_click",
    "not_opened",
    "clicked_no_convert",
    "converted",
}

VALID_AI_TONES = {
    "warm",
    "urgent",
    "playful",
    "professional",
    "empathetic",
}

# Email regex — not perfect (no regex is) but catches obvious mistakes
# Valid: user@example.com, user.name+tag@sub.domain.co.uk
# Invalid: @example.com, user@, user@.com
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_campaign_type(campaign_type: str) -> str:
    """
    Validates and normalizes campaign type string.
    
    Parameters:
    -----------
    campaign_type : str
        Raw campaign type from request
        
    Returns:
    --------
    Lowercased, validated campaign type
    
    Raises:
    -------
    ValueError — with a helpful message listing valid options
    """
    normalized = campaign_type.lower().strip()
    
    if normalized not in VALID_CAMPAIGN_TYPES:
        raise ValueError(
            f"Invalid campaign_type: '{campaign_type}'. "
            f"Must be one of: {sorted(VALID_CAMPAIGN_TYPES)}"
        )
    
    return normalized


def validate_segment(segment: str) -> str:
    """
    Validates a customer segment name.
    
    Parameters:
    -----------
    segment : str
        Raw segment name from request
        
    Returns:
    --------
    Lowercased, validated segment name
    
    Raises:
    -------
    ValueError — with a helpful message listing valid options
    """
    normalized = segment.lower().strip()
    
    if normalized not in VALID_SEGMENTS:
        raise ValueError(
            f"Invalid segment: '{segment}'. "
            f"Must be one of: {sorted(VALID_SEGMENTS)}"
        )
    
    return normalized


def validate_followup_outcome(outcome: str) -> str:
    """
    Validates a follow-up email outcome string.
    
    Parameters:
    -----------
    outcome : str
        Raw outcome string from request
        
    Returns:
    --------
    Validated outcome string
    
    Raises:
    -------
    ValueError — with valid options listed
    """
    normalized = outcome.lower().strip()
    
    if normalized not in VALID_FOLLOWUP_OUTCOMES:
        raise ValueError(
            f"Invalid outcome: '{outcome}'. "
            f"Must be one of: {sorted(VALID_FOLLOWUP_OUTCOMES)}"
        )
    
    return normalized


def validate_email_address(email: str) -> bool:
    """
    Checks if an email address has a valid format.
    
    Parameters:
    -----------
    email : str
        Email address to validate
        
    Returns:
    --------
    True if valid format, False if not
    
    NOTE: This only checks FORMAT, not deliverability.
    An email can pass this check and still bounce.
    For real deliverability checking, use SendGrid's Email Validation API.
    """
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_user_instructions(instructions: str, min_length: int = 10) -> str:
    """
    Validates free-form user instructions for custom campaigns.
    
    Parameters:
    -----------
    instructions : str
        The raw instructions from the user
    min_length : int
        Minimum character count (default: 10)
        Prevents empty or meaninglessly short instructions like "email"
        
    Returns:
    --------
    Stripped, validated instructions string
    
    Raises:
    -------
    ValueError — if instructions are too short or empty
    """
    if not instructions or not instructions.strip():
        raise ValueError("user_instructions cannot be empty")
    
    stripped = instructions.strip()
    
    if len(stripped) < min_length:
        raise ValueError(
            f"user_instructions is too short ({len(stripped)} chars). "
            f"Please provide at least {min_length} characters describing your campaign."
        )
    
    # Safety: cap at 2000 characters to prevent prompt injection via huge instructions
    if len(stripped) > 2000:
        stripped = stripped[:2000]
    
    return stripped


def validate_batch_limit(limit: int) -> int:
    """
    Validates the batch size limit.
    
    Why cap at 20?
    - Gemini free tier: 15 req/min
    - 20 emails would take ~1.5 minutes
    - More than 20 risks hitting rate limits mid-batch
    
    Parameters:
    -----------
    limit : int
        Requested batch size
        
    Returns:
    --------
    Validated limit (capped at 20)
    
    Raises:
    -------
    ValueError — if limit is <= 0
    """
    if limit <= 0:
        raise ValueError("Batch limit must be at least 1")
    
    if limit > 20:
        # Cap silently and log — don't error, just reduce
        import logging
        logging.getLogger(__name__).warning(
            f"Batch limit {limit} exceeds maximum of 20 — capping at 20"
        )
        return 20
    
    return limit


def validate_customer_id(customer_id: Optional[str]) -> Optional[str]:
    """
    Validates a customer UUID format.
    
    UUIDs look like: "550e8400-e29b-41d4-a716-446655440000"
    
    Parameters:
    -----------
    customer_id : str or None
        Customer UUID to validate. None is valid (means "pick random").
        
    Returns:
    --------
    Validated UUID string or None
    
    Raises:
    -------
    ValueError — if provided but clearly not a UUID format
    """
    if customer_id is None:
        return None
    
    stripped = customer_id.strip()
    
    # Basic UUID format check: 8-4-4-4-12 hex chars with dashes
    uuid_pattern = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )
    
    if not uuid_pattern.match(stripped):
        raise ValueError(
            f"Invalid customer_id format: '{customer_id}'. "
            "Expected a UUID like: '550e8400-e29b-41d4-a716-446655440000'"
        )
    
    return stripped

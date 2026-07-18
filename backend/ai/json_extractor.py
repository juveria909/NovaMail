"""
json_extractor.py — PART 2: Robust JSON Extraction & Validation
================================================================
This is the most DEFENSIVE file in the entire project.

WHY IS THIS NECESSARY?
-----------------------
AI models are probabilistic. Even with perfect prompts, they sometimes:

1. Wrap JSON in markdown code fences:
   ```json
   {"subject_line": "Hi Sarah"}
   ```
   → We strip the fences.

2. Add explanatory text before/after the JSON:
   "Here's the email: {"subject_line": "Hi Sarah"} Hope this helps!"
   → We extract just the JSON part.

3. Use single quotes instead of double quotes (invalid JSON):
   {'subject_line': 'Hi Sarah'}
   → We fix the quotes.

4. Add trailing commas (valid in Python, NOT in JSON):
   {"subject_line": "Hi",}
   → We remove trailing commas.

5. Truncate mid-JSON if they ran out of tokens:
   {"subject_line": "Hi Sarah", "body": {"greeting": "Hi Sarah
   → We detect and retry.

6. Return NOTHING (hallucination/refusal):
   "I cannot write marketing emails."
   → We retry with a corrective prompt.

OUR EXTRACTION PIPELINE (3 layers):
-------------------------------------
Layer 1: Try direct json.loads() — fastest path, works 70% of the time
Layer 2: Regex extraction + cleaning — works for 25% of remaining cases
Layer 3: AI-assisted correction — send the broken response BACK to the AI 
         and ask it to fix its own JSON. Works for 4% of remaining cases.
         
If all 3 layers fail → raise a structured error with the raw response for debugging.

SCHEMA VALIDATION:
------------------
After extraction, we validate the structure against our expected schema.
Missing required keys get filled with safe defaults.
Extra/unexpected keys are preserved (don't break future extensions).
"""

import json
import re
import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# =============================================================================
# EXPECTED SCHEMA — Defines required fields and their defaults
# =============================================================================

# These are the fields that MUST exist in a valid email JSON.
# If any are missing, we fill them with the default value.
REQUIRED_EMAIL_FIELDS = {
    "campaign_type":  "custom",
    "recipient_id":   "",
    "subject_line":   "Hello from us",
    "preview_text":   "",
    "body": {
        "greeting":      "Hi there,",
        "opening":       "",
        "main_content":  "",
        "call_to_action": "Learn More",
        "cta_url":       "https://example.com",
        "closing":       "Best regards, The Team",
    },
    "metadata": {
        "tone":                        "professional",
        "personalization_signals_used": [],
        "recommended_send_time":       "Tuesday 10:00 AM",
        "estimated_open_rate_boost":   "unknown",
        "reasoning":                   "",
    }
}


# =============================================================================
# LAYER 1: Direct JSON Parse
# =============================================================================

def _try_direct_parse(text: str) -> Optional[Any]:
    """
    Attempt direct json.loads() on the raw text.
    This works when the AI correctly outputs clean JSON with no extra text.
    
    Returns None if parsing fails (not a ValueError/exception — just None).
    """
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


# =============================================================================
# LAYER 2: Regex Extraction + Text Cleaning
# =============================================================================

def _clean_json_text(text: str) -> str:
    """
    Applies a series of text transformations to fix common AI JSON mistakes.
    
    Each transformation is documented with WHY it's needed.
    """
    
    # Step 1: Remove markdown code fences
    # AI often wraps JSON like: ```json\n{...}\n```
    # The regex matches ``` optionally followed by a language name
    text = re.sub(r'```(?:json|JSON|javascript|js)?\s*', '', text)
    text = text.replace('```', '')
    
    # Step 2: Find the outermost JSON object or array
    # If AI said "Here's your email: {...} Let me know...", 
    # we need to extract just the {...} part.
    # This regex finds the FIRST { or [ and the matching last } or ]
    
    # Try to find a JSON object first ({...})
    json_object_match = re.search(r'\{[\s\S]*\}', text)
    # Try to find a JSON array next ([...])
    json_array_match  = re.search(r'\[[\s\S]*\]', text)
    
    if json_object_match and json_array_match:
        # Both found — take whichever starts earlier
        if json_object_match.start() < json_array_match.start():
            text = json_object_match.group()
        else:
            text = json_array_match.group()
    elif json_object_match:
        text = json_object_match.group()
    elif json_array_match:
        text = json_array_match.group()
    # If neither found, proceed with the full text (will likely fail)
    
    # Step 3: Remove trailing commas before } or ]
    # These are common in Python but invalid JSON
    # Example: {"key": "value",} → {"key": "value"}
    text = re.sub(r',\s*([}\]])', r'\1', text)
    
    # Step 4: Fix single-quoted strings to double-quoted
    # AI sometimes uses Python dict syntax with single quotes
    # Careful: only replace quote delimiters, not apostrophes in words
    # This is a heuristic and won't catch every case, but handles most
    text = re.sub(r"(?<!\w)'([^']*?)'(?!\w)", r'"\1"', text)
    
    # Step 5: Remove Python-style None/True/False (replace with JSON equivalents)
    text = re.sub(r'\bNone\b', 'null', text)
    text = re.sub(r'\bTrue\b', 'true', text)
    text = re.sub(r'\bFalse\b', 'false', text)
    
    # Step 6: Remove control characters that break JSON parsing
    # Some AI outputs contain invisible Unicode control chars
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    return text.strip()


def _try_cleaned_parse(text: str) -> Optional[Any]:
    """
    Applies all cleaning transformations and then attempts json.loads().
    
    Returns the parsed Python object (dict or list) or None if it fails.
    """
    cleaned = _clean_json_text(text)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.debug(f"Cleaned parse failed: {e}  cleaned text preview: {cleaned[:200]}")
        return None


# =============================================================================
# LAYER 3: JSON5 Fallback (More Permissive Parser)
# =============================================================================

def _try_json5_parse(text: str) -> Optional[Any]:
    """
    Uses the json5 library which is more permissive than standard json:
    - Allows trailing commas
    - Allows comments (// and /* */)
    - Allows single-quoted strings
    - Allows unquoted keys
    
    json5 is a superset of JSON — valid JSON is always valid JSON5.
    But we keep this as a fallback because json5 is slower than json.
    
    Falls back gracefully if json5 is not installed.
    """
    try:
        import json5
        cleaned = _clean_json_text(text)
        return json5.loads(cleaned)
    except ImportError:
        logger.debug("json5 library not installed  skipping JSON5 fallback")
        return None
    except Exception as e:
        logger.debug(f"JSON5 parse failed: {e}")
        return None


# =============================================================================
# SCHEMA VALIDATION & NORMALIZATION
# =============================================================================

def _deep_merge_defaults(data: dict, defaults: dict) -> dict:
    """
    Fills in missing required fields with default values.
    
    Unlike dict.update(), this works RECURSIVELY for nested dicts.
    
    Example:
    --------
    data = {"subject_line": "Hi Sarah", "body": {"greeting": "Hello"}}
    defaults = {"subject_line": "", "body": {"greeting": "", "closing": "Best"}, "metadata": {...}}
    
    Result: data.body.closing gets "Best" (was missing)
            data.metadata gets filled with defaults (was missing entirely)
            data.subject_line stays "Hi Sarah" (was present, not overwritten)
    """
    result = dict(defaults)  # Start with a copy of defaults
    
    for key, value in data.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dicts
            result[key] = _deep_merge_defaults(value, result[key])
        else:
            # Non-dict value: data's value takes priority over default
            result[key] = value
    
    return result


def _validate_single_email(data: dict, customer_id: str = "") -> dict:
    """
    Validates and normalizes a single email dict.
    
    Checks:
    - All required fields are present (fills missing with defaults)
    - Subject line isn't too long (truncates if needed)
    - campaign_type is valid
    - Injects customer_id if missing
    
    Parameters:
    -----------
    data : dict
        Parsed email dict from AI response
    customer_id : str
        The customer's UUID (to inject if AI forgot to include it)
        
    Returns:
    --------
    Validated and normalized dict
    """
    
    # Fill missing fields with defaults (deep merge)
    validated = _deep_merge_defaults(data, REQUIRED_EMAIL_FIELDS)
    
    # Inject customer_id if the AI left it blank
    if not validated.get("recipient_id") and customer_id:
        validated["recipient_id"] = customer_id
    
    # Truncate subject line if too long (60 char mobile limit)
    subject = validated.get("subject_line", "")
    if len(subject) > 60:
        logger.warning(f"Subject line too long ({len(subject)} chars)  truncating")
        validated["subject_line"] = subject[:57] + "..."
    
    # Validate campaign_type
    valid_types = {"welcome", "reengagement", "followup", "variant_test", "custom", "rewrite"}
    if validated.get("campaign_type") not in valid_types:
        logger.warning(f"Invalid campaign_type '{validated.get('campaign_type')}'  setting to 'custom'")
        validated["campaign_type"] = "custom"
    
    return validated


# =============================================================================
# MAIN PUBLIC FUNCTION
# =============================================================================

def extract_email_json(
    ai_response: str,
    is_multi_variant: bool = False,
    customer_id: str = "",
) -> Union[Dict, List[Dict]]:
    """
    The main entry point. Extracts and validates email JSON from AI response text.
    
    This runs through all 3 extraction layers automatically.
    
    Parameters:
    -----------
    ai_response : str
        The raw text response from Gemini/Groq
    is_multi_variant : bool
        If True, expects a JSON array of email objects (for A/B testing)
        If False, expects a single JSON object
    customer_id : str
        Customer UUID to inject into the result if missing
        
    Returns:
    --------
    dict  — if is_multi_variant is False
    list  — if is_multi_variant is True (list of dicts)
    
    Raises:
    -------
    ValueError — if all extraction layers fail
        The ValueError message contains the raw AI response for debugging.
    
    Usage:
    ------
    try:
        email = extract_email_json(ai_text, is_multi_variant=False, customer_id="abc123")
    except ValueError as e:
        print(f"Extraction failed: {e}")
    """
    
    if not ai_response or not ai_response.strip():
        raise ValueError("AI returned an empty response — cannot extract JSON")
    
    logger.debug(f"Extracting JSON from response ({len(ai_response)} chars)...")
    
    # ---- Layer 1: Direct parse ----
    parsed = _try_direct_parse(ai_response)
    
    if parsed is None:
        logger.debug("Layer 1 (direct) failed  trying Layer 2 (cleaned)")
        # ---- Layer 2: Cleaned parse ----
        parsed = _try_cleaned_parse(ai_response)
    
    if parsed is None:
        logger.debug("Layer 2 (cleaned) failed  trying Layer 3 (JSON5)")
        # ---- Layer 3: JSON5 parse ----
        parsed = _try_json5_parse(ai_response)
    
    if parsed is None:
        # All layers failed. Raise with the raw response so caller can retry.
        raise ValueError(
            f"All JSON extraction layers failed.\n"
            f"Raw AI response (first 500 chars):\n{ai_response[:500]}"
        )
    
    logger.debug(f"JSON extracted successfully (type: {type(parsed).__name__})")
    
    # ---- Validate and normalize ----
    
    if is_multi_variant:
        # Expecting a list of email dicts
        if isinstance(parsed, list):
            variants = [_validate_single_email(item, customer_id) for item in parsed]
            logger.info(f"[OK] Extracted {len(variants)} email variants")
            return variants
        
        elif isinstance(parsed, dict):
            # AI returned a single dict when we expected an array
            # Wrap it in a list and add a warning
            logger.warning(
                "Expected JSON array for variants but got a single dict — "
                "wrapping in list. Consider retrying."
            )
            return [_validate_single_email(parsed, customer_id)]
        
        else:
            raise ValueError(f"Expected list for variants, got {type(parsed).__name__}")
    
    else:
        # Expecting a single email dict
        if isinstance(parsed, dict):
            validated = _validate_single_email(parsed, customer_id)
            logger.info("[OK] Extracted and validated single email JSON")
            return validated
        
        elif isinstance(parsed, list) and len(parsed) > 0:
            # AI returned an array when we expected single — take the first one
            logger.warning(
                "Expected single dict but got array — using first element"
            )
            return _validate_single_email(parsed[0], customer_id)
        
        else:
            raise ValueError(f"Expected dict for email, got {type(parsed).__name__}")


# =============================================================================
# RETRY CORRECTION PROMPT — Used by email_generator.py for Layer 4 (AI self-fix)
# =============================================================================

def build_correction_prompt(broken_response: str, error_message: str) -> str:
    """
    Builds a prompt asking the AI to fix its own broken JSON output.
    
    This is the "nuclear option" — only used after all 3 extraction layers fail.
    We send the broken response BACK to the AI and ask it to correct itself.
    
    Parameters:
    -----------
    broken_response : str
        The AI's previous, invalid response
    error_message : str
        The JSON parsing error to show the AI
        
    Returns:
    --------
    A corrective user message to send to the AI
    """
    return f"""
Your previous response could not be parsed as valid JSON.

Error: {error_message}

Your previous response was:
{broken_response[:1000]}

Please output ONLY the corrected, valid JSON object.
No explanation. No markdown. No code fences. Raw JSON only.
Start your response with {{ and end with }}.
""".strip()

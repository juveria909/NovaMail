"""
data_enricher.py — PART 1: Behavioral Data Enrichment
=======================================================
This file takes raw user data from the API and transforms it into
a RICH customer profile that the AI can actually use to write personalized emails.

What RandomUser.me gives us (raw):
    name, email, location, age, gender, registered date, photo

What the AI NEEDS to personalize emails:
    - Customer segment (new/active/inactive/high-value/at-risk)
    - Purchase history (what did they buy? how much did they spend?)
    - Email behavior (do they open emails? when? do they click?)
    - Interests (fitness? tech? travel? food?)
    - Optimal send time (when are they most likely to open?)
    - Tags (what campaign types apply to them?)

This file bridges that gap by generating REALISTIC behavioral data
based on the user's actual attributes (age, location, registration date).

KEY PRINCIPLE: The behavioral data is NOT random noise.
It's generated using patterns that mirror real customer behavior:
    - Older accounts → more purchase history
    - High open rate → send more emails
    - Recent signup → welcome sequence
    - Long-inactive → re-engagement needed
"""

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# INTEREST CATEGORIES — Realistic customer interest pools
# =============================================================================

INTEREST_POOLS = {
    "fitness":    ["yoga", "running", "gym", "cycling", "nutrition", "mindfulness"],
    "tech":       ["AI", "gadgets", "gaming", "software", "productivity", "crypto"],
    "travel":     ["backpacking", "luxury travel", "road trips", "photography", "culture"],
    "food":       ["cooking", "baking", "restaurants", "vegan", "meal prep", "wine"],
    "fashion":    ["streetwear", "sustainable fashion", "luxury", "sneakers", "vintage"],
    "education":  ["online courses", "books", "podcasts", "career growth", "languages"],
    "home":       ["interior design", "DIY", "gardening", "smart home", "minimalism"],
    "finance":    ["investing", "budgeting", "crypto", "real estate", "side hustles"],
}

# Map age ranges to most likely interest categories
AGE_INTEREST_MAP = {
    (18, 24): ["fitness", "tech", "education", "fashion"],
    (25, 34): ["fitness", "tech", "travel", "finance", "food"],
    (35, 44): ["finance", "home", "food", "travel", "education"],
    (45, 60): ["home", "finance", "food", "travel", "education"],
    (60, 99): ["home", "food", "education", "travel"],
}

# Realistic product categories for purchase history
PRODUCT_CATEGORIES = {
    "fitness": [
        {"item": "Yoga Mat", "price_range": (25, 80)},
        {"item": "Protein Powder", "price_range": (30, 70)},
        {"item": "Workout App Subscription", "price_range": (10, 30)},
        {"item": "Running Shoes", "price_range": (80, 180)},
        {"item": "Resistance Bands", "price_range": (15, 40)},
    ],
    "tech": [
        {"item": "Wireless Earbuds", "price_range": (50, 200)},
        {"item": "Phone Stand", "price_range": (15, 40)},
        {"item": "SaaS Tool Subscription", "price_range": (10, 50)},
        {"item": "Smart Watch", "price_range": (100, 400)},
    ],
    "home": [
        {"item": "Scented Candle Set", "price_range": (20, 60)},
        {"item": "Planter", "price_range": (15, 45)},
        {"item": "Organization Box Set", "price_range": (25, 75)},
    ],
    "food": [
        {"item": "Coffee Subscription", "price_range": (20, 50)},
        {"item": "Spice Kit", "price_range": (25, 60)},
        {"item": "Meal Kit (1 month)", "price_range": (60, 120)},
    ],
    "travel": [
        {"item": "Travel Pillow", "price_range": (20, 50)},
        {"item": "Luggage Tag Set", "price_range": (10, 25)},
        {"item": "Travel Insurance Plan", "price_range": (30, 100)},
    ],
    "default": [
        {"item": "Gift Card", "price_range": (25, 100)},
        {"item": "Premium Membership", "price_range": (10, 50)},
        {"item": "Starter Kit", "price_range": (30, 80)},
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_interests_for_age(age: int) -> List[str]:
    """Pick 2-4 realistic interest TOPICS based on customer age."""
    for (min_age, max_age), categories in AGE_INTEREST_MAP.items():
        if min_age <= age <= max_age:
            # Pick 2-3 categories for this age group
            num_categories = random.randint(2, min(3, len(categories)))
            chosen_categories = random.sample(categories, num_categories)
            
            # From each category, pick 1-2 specific interests
            interests = []
            for cat in chosen_categories:
                pool = INTEREST_POOLS.get(cat, [])
                if pool:
                    interests.extend(random.sample(pool, min(2, len(pool))))
            
            return interests[:5]  # Cap at 5 interests
    
    return ["productivity", "online shopping"]  # Safe fallback


def _generate_purchase_history(
    interests: List[str], 
    signup_date: datetime,
    account_age_days: int
) -> List[Dict[str, Any]]:
    """
    Generate realistic purchase history.
    
    Logic:
    - Newer accounts (< 30 days) → 0-1 purchases
    - Medium accounts (30-180 days) → 1-3 purchases
    - Older accounts (180+ days) → 2-6 purchases
    - Purchases are spread across account lifetime, not clustered
    """
    # Determine how many purchases based on account age
    if account_age_days < 30:
        num_purchases = random.randint(0, 1)
    elif account_age_days < 180:
        num_purchases = random.randint(1, 3)
    else:
        num_purchases = random.randint(2, 6)
    
    if num_purchases == 0:
        return []
    
    # Find relevant product category from interests
    purchase_category = "default"
    for interest in interests:
        for category in PRODUCT_CATEGORIES:
            if category in interest.lower():
                purchase_category = category
                break
    
    products = PRODUCT_CATEGORIES.get(purchase_category, PRODUCT_CATEGORIES["default"])
    
    purchases = []
    for _ in range(num_purchases):
        product = random.choice(products)
        
        # Purchase date: random day between signup and today
        days_after_signup = random.randint(1, max(1, account_age_days - 1))
        purchase_date = signup_date + timedelta(days=days_after_signup)
        
        # Price: random within product's realistic range
        price = round(random.uniform(*product["price_range"]), 2)
        
        purchases.append({
            "item": product["item"],
            "date": purchase_date.strftime("%Y-%m-%d"),
            "amount": price,
            "currency": "USD",
        })
    
    # Sort by date (oldest first)
    purchases.sort(key=lambda x: x["date"])
    return purchases


def _generate_email_behavior(account_age_days: int, segment: str) -> Dict[str, Any]:
    """
    Generate realistic email engagement metrics.
    
    Industry averages (real data):
    - Average email open rate: 20-30%
    - Average click rate: 2-5%
    - "Good" open rate: > 40%
    - "At risk": open rate < 15%
    
    We use the segment to make behavior CONSISTENT with the label.
    An "active" user should have high open rate. An "inactive" user shouldn't.
    """
    
    # Base metrics depend on segment
    segment_profiles = {
        "new":       {"open_rate": (0.30, 0.70), "click_rate": (0.05, 0.20), "emails_received": (1, 5)},
        "active":    {"open_rate": (0.35, 0.65), "click_rate": (0.08, 0.25), "emails_received": (10, 50)},
        "inactive":  {"open_rate": (0.02, 0.15), "click_rate": (0.00, 0.05), "emails_received": (5, 30)},
        "high_value":{"open_rate": (0.40, 0.75), "click_rate": (0.10, 0.35), "emails_received": (15, 60)},
        "at_risk":   {"open_rate": (0.08, 0.20), "click_rate": (0.01, 0.08), "emails_received": (5, 25)},
        "new_signup":{"open_rate": (0.40, 0.80), "click_rate": (0.10, 0.30), "emails_received": (1, 3)},
    }
    
    profile = segment_profiles.get(segment, segment_profiles["active"])
    
    open_rate  = round(random.uniform(*profile["open_rate"]), 2)
    click_rate = round(random.uniform(
        profile["click_rate"][0],
        min(profile["click_rate"][1], open_rate * 0.5)  # Click rate can't exceed half of open rate
    ), 2)
    
    emails_received = random.randint(*profile["emails_received"])
    
    # Last opened: depends on how active they are
    if segment == "inactive":
        days_since_open = random.randint(60, 180)
    elif segment == "new" or segment == "new_signup":
        days_since_open = random.randint(0, 7)
    else:
        days_since_open = random.randint(1, 30)
    
    last_opened = datetime.now(timezone.utc) - timedelta(days=days_since_open)
    
    # Optimal send time: based on common real-world patterns
    send_time_options = [
        "Tuesday 10:00 AM", "Wednesday 2:00 PM", "Thursday 10:00 AM",
        "Monday 9:00 AM", "Friday 11:00 AM", "Wednesday 7:00 PM",
    ]
    
    return {
        "open_rate": open_rate,
        "click_rate": click_rate,
        "emails_received": emails_received,
        "last_opened": last_opened.isoformat(),
        "preferred_send_time": random.choice(send_time_options),
        "unsubscribed": False,
        "bounced": False,
    }


def _determine_segment(
    account_age_days: int,
    purchase_count: int,
    days_since_last_active: int
) -> str:
    """
    Classify a customer into one of 6 segments based on their behavior.
    
    These segments are what the AI uses to decide email TYPE:
    - new_signup → welcome sequence
    - active → feature updates, upsell
    - inactive → re-engagement
    - high_value → VIP treatment
    - at_risk → retention urgency
    - new → gentle nurture
    """
    
    if account_age_days < 7:
        return "new_signup"      # Just joined this week
    
    if account_age_days < 30:
        return "new"             # Less than a month old
    
    if days_since_last_active > 90:
        return "inactive"        # Haven't been seen in 3 months
    
    if purchase_count >= 4 and days_since_last_active < 30:
        return "high_value"      # Frequent buyer, recently active
    
    if days_since_last_active > 45:
        return "at_risk"         # Starting to go quiet
    
    return "active"              # Normal engaged customer


def _generate_tags(segment: str, interests: List[str], purchase_count: int) -> List[str]:
    """Generate campaign tags that help the AI understand what to send."""
    
    tags = [segment]
    
    if purchase_count == 0:
        tags.append("never-purchased")
    elif purchase_count >= 4:
        tags.append("frequent-buyer")
    
    if segment == "inactive":
        tags.append("re-engage")
    elif segment == "new_signup":
        tags.append("welcome-sequence")
    elif segment == "high_value":
        tags.append("vip")
        tags.append("upsell-candidate")
    
    # Add interest-based tags
    for interest in interests[:2]:  # Only first 2 to keep tags clean
        tags.append(f"interest-{interest.lower().replace(' ', '-')}")
    
    return list(set(tags))  # Remove duplicates


# =============================================================================
# MAIN ENRICHMENT FUNCTION
# =============================================================================

def enrich_user(raw_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms a raw RandomUser.me user dict into a full customer profile.
    
    This is the CORE function of this file. Called once per user record.
    
    Parameters:
    -----------
    raw_user : Dict
        A single user dict directly from RandomUser.me API response
        
    Returns:
    --------
    A complete customer profile dict matching our schema:
    {
        "id": "uuid",
        "name": "Sarah Johnson",
        "email": "...",
        "segment": "inactive",
        "interests": [...],
        "purchase_history": [...],
        "email_behavior": {...},
        "tags": [...],
        ...
    }
    """
    
    # --- Extract raw fields ---
    name_data     = raw_user.get("name", {})
    location_data = raw_user.get("location", {})
    dob_data      = raw_user.get("dob", {})
    registered    = raw_user.get("registered", {})
    
    full_name = f"{name_data.get('first', 'User')} {name_data.get('last', '')}"
    raw_email = raw_user.get("email", "")
    if raw_email and "@example.com" in raw_email:
        username = raw_email.split("@")[0]
        domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]
        email = f"{username}@{random.choice(domains)}"
    elif raw_email:
        email = raw_email
    else:
        domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]
        email = f"user_{uuid.uuid4().hex[:8]}@{random.choice(domains)}"
        
    age       = dob_data.get("age", random.randint(22, 55))
    gender    = raw_user.get("gender", "other")
    
    # Parse signup date from the API's date string
    registered_str = registered.get("date", "")
    try:
        signup_date = datetime.fromisoformat(registered_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        signup_date = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 730))
    
    # Account age in days
    now = datetime.now(timezone.utc)
    account_age_days = (now - signup_date).days
    
    # Days since last active (simulated)
    days_since_active = random.choices(
        population=[random.randint(0, 7), random.randint(8, 30), random.randint(31, 90), random.randint(91, 365)],
        weights=[30, 35, 20, 15],  # 30% very recent, 35% this month, 20% this quarter, 15% very old
        k=1
    )[0]
    last_active_date = now - timedelta(days=days_since_active)
    
    # --- Generate behavioral data ---
    interests = _get_interests_for_age(age)
    
    # Determine segment FIRST (before purchase history, so we can use it)
    segment = _determine_segment(
        account_age_days=account_age_days,
        purchase_count=0,  # Placeholder — updated after purchase history generation
        days_since_last_active=days_since_active
    )
    
    purchase_history = _generate_purchase_history(
        interests=interests,
        signup_date=signup_date,
        account_age_days=account_age_days
    )
    
    # Re-determine segment now that we have actual purchase count
    segment = _determine_segment(
        account_age_days=account_age_days,
        purchase_count=len(purchase_history),
        days_since_last_active=days_since_active
    )
    
    email_behavior = _generate_email_behavior(account_age_days, segment)
    tags = _generate_tags(segment, interests, len(purchase_history))
    
    # Calculate lifetime value from purchase history
    total_spent = sum(p["amount"] for p in purchase_history)
    
    # --- Assemble final customer profile ---
    return {
        # Core identity
        "id": str(uuid.uuid4()),
        "name": full_name.strip(),
        "first_name": name_data.get("first", "there"),  # Used in AI: "Hi {first_name},"
        "email": email,
        "phone": raw_user.get("phone", ""),
        "gender": gender,
        "age": age,
        
        # Location (used for send-time optimization)
        "location": {
            "city": location_data.get("city", ""),
            "state": location_data.get("state", ""),
            "country": location_data.get("country", "United States"),
            "timezone": location_data.get("timezone", {}).get("description", "UTC"),
        },
        
        # Account information
        "signup_date": signup_date.strftime("%Y-%m-%d"),
        "account_age_days": account_age_days,
        "last_active": last_active_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "subscription_status": "active",
        
        # Behavioral intelligence
        "segment": segment,
        "interests": interests,
        "purchase_history": purchase_history,
        "total_spent_usd": round(total_spent, 2),
        "purchase_count": len(purchase_history),
        "email_behavior": email_behavior,
        
        # Campaign metadata
        "tags": tags,
        "profile_picture": raw_user.get("picture", {}).get("thumbnail", ""),
        
        # Timestamp of when this record was created/enriched
        "enriched_at": now.isoformat(),
    }


def enrich_batch(raw_users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enriches a list of raw users. Called after fetch_random_users().
    
    Simply maps enrich_user() over the list.
    Skips any user that fails enrichment (logs the error) rather than
    crashing the whole batch.
    """
    enriched = []
    
    for i, raw_user in enumerate(raw_users):
        try:
            enriched.append(enrich_user(raw_user))
        except Exception as e:
            logger.warning(f"Failed to enrich user {i}: {e} — skipping")
            continue  # Skip bad records, keep going
    
    logger.info(f"Enriched {len(enriched)}/{len(raw_users)} users successfully")
    return enriched

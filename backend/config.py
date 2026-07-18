"""
config.py — Central Configuration File
=======================================
This is the SINGLE SOURCE OF TRUTH for all settings in the project.
Every other file imports from here. Never hardcode API keys anywhere else.

Why this pattern?
-----------------
If you ever need to change the Gemini model or switch from Gemini to Groq,
you only change ONE value here and it propagates everywhere automatically.
"""

import os
from dotenv import load_dotenv

# Load all key=value pairs from the .env file into environment variables
# This must be called BEFORE reading any os.getenv() values
load_dotenv()


# =============================================================================
# AI MODEL CONFIGURATION
# =============================================================================

# Which AI provider to use by default.
# Options: "gemini" or "groq"
# Change this ONE variable to switch the entire backend's AI provider.
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")

# --- Gemini Settings ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# The specific Gemini model to use.
# "gemini-2.0-flash" is fast and free on Google AI Studio.
# "gemini-1.5-pro" is more powerful but slower.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# --- Groq Settings (fallback / alternative) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Groq serves open-source models at insane speed for free.
# "llama-3.3-70b-versatile" is their best general-purpose model.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


# =============================================================================
# LIVE DATASET CONFIGURATION (Part 1)
# =============================================================================

# How many customer records to keep in memory at one time.
# 200 records is plenty for a live demo — fast startup, still impressive.
# In production you'd increase this to 5000+ backed by a real DB.
DATASET_SIZE = int(os.getenv("DATASET_SIZE", "200"))

# How many records to fetch per API call to RandomUser.me
# 50 per batch keeps each HTTP call fast (~300ms vs ~800ms for 100)
FETCH_BATCH_SIZE = int(os.getenv("FETCH_BATCH_SIZE", "50"))

# How often (in seconds) to refresh/update a portion of the live dataset.
# 8 seconds keeps it visibly live without hammering the API or CPU.
DATASET_REFRESH_INTERVAL = int(os.getenv("DATASET_REFRESH_INTERVAL", "8"))

# The live public API for random realistic user data (completely free, no key needed)
RANDOM_USER_API = "https://randomuser.me/api/"

# Open-Meteo API for timezone-aware send-time recommendations (free, no key needed)
OPEN_METEO_API = "https://api.open-meteo.com/v1/forecast"


# =============================================================================
# AI GENERATION SETTINGS
# =============================================================================

# Maximum number of tokens the AI can use for its response.
# 2048 is enough for a complete email with metadata.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))

# Temperature controls creativity vs consistency.
# 0.0 = robotic, always same output
# 1.0 = highly creative, unpredictable
# 0.7 is the sweet spot for email writing — creative but professional
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))

# How many times to retry if the AI returns broken/invalid JSON
JSON_RETRY_LIMIT = int(os.getenv("JSON_RETRY_LIMIT", "3"))

# How many email variants to generate for A/B testing by default
DEFAULT_VARIANT_COUNT = int(os.getenv("DEFAULT_VARIANT_COUNT", "3"))


# =============================================================================
# EMAIL SERVICE CONFIGURATION (Stubbed — no real service connected yet)
# =============================================================================

# When this is True, emails are NOT actually sent — just logged and returned.
# Set to False when you're ready to connect a real email service.
EMAIL_STUB_MODE = os.getenv("EMAIL_STUB_MODE", "true").lower() == "true"

# When you're ready: set EMAIL_SERVICE to "sendgrid" or "mailgun"
EMAIL_SERVICE = os.getenv("EMAIL_SERVICE", "stub")

# SendGrid API key (get free at sendgrid.com — 100 emails/day free)
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

# Mailgun API key (get free at mailgun.com — 100 emails/day free for 3 months)
MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY", "")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN", "")

# The "From" address on all outgoing emails
FROM_EMAIL = os.getenv("FROM_EMAIL", "campaigns@yourbrand.com")
FROM_NAME = os.getenv("FROM_NAME", "Your Brand")


# =============================================================================
# SERVER CONFIGURATION
# =============================================================================

# The port FastAPI will run on. http://localhost:8000
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))


# =============================================================================
# VALIDATION — Fail loudly at startup if critical keys are missing
# =============================================================================

def validate_config():
    """
    Call this once at startup to catch missing API keys early.
    Better to crash at startup with a clear message than to fail mid-request
    with a confusing error.
    """
    errors = []

    if AI_PROVIDER == "gemini" and not GEMINI_API_KEY:
        errors.append(
            "GEMINI_API_KEY is missing! "
            "Get it free at: https://aistudio.google.com/app/apikey"
        )

    if AI_PROVIDER == "groq" and not GROQ_API_KEY:
        errors.append(
            "GROQ_API_KEY is missing! "
            "Get it free at: https://console.groq.com/keys"
        )

    if errors:
        print("\n" + "="*60)
        print("CONFIGURATION ERROR -- Please fix your .env file:")
        for e in errors:
            print(f"  [ERROR] {e}")
        print("="*60 + "\n")
        raise EnvironmentError("Missing required API keys. See errors above.")

    print(f"[OK] Config loaded -- Using {AI_PROVIDER.upper()} | Dataset: {DATASET_SIZE} records")

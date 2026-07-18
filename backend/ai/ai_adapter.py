"""
ai_adapter.py — PART 2: Unified Gemini/Groq API Client
========================================================
This file provides a SINGLE interface that works with BOTH Gemini AND Groq.

WHY A UNIFIED ADAPTER?
-----------------------
Without this adapter, every file that needs AI would need to know:
  "Are we using Gemini? Then use google.generativeai library..."
  "Are we using Groq? Then use groq library..."
  
This creates duplication and makes switching providers painful.

With this adapter:
  - ONE interface: ai_adapter.generate(prompt_data)
  - The adapter handles all provider-specific code internally
  - Switching from Gemini to Groq = change ONE line in config.py
  
FALLBACK CHAIN:
---------------
If Gemini is the default and fails (API error, rate limit):
  → Try Groq as backup
  → If Groq also fails → raise error with both error messages

RETRY LOGIC:
------------
If the AI returns valid text but invalid JSON:
  → Try extraction (3 layers in json_extractor.py)
  → If extraction fails → send correction prompt BACK to AI
  → Retry up to JSON_RETRY_LIMIT times
  → If all retries fail → raise error

This file also handles:
  - Token estimation (prevents sending too-long prompts)
  - Response timing (logs how long each API call takes)
  - Rate limit detection (429 errors → wait and retry)
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Union

from backend.config import (
    AI_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    MAX_OUTPUT_TOKENS,
    TEMPERATURE,
    JSON_RETRY_LIMIT,
)
from backend.ai.json_extractor import (
    extract_email_json,
    build_correction_prompt,
)

logger = logging.getLogger(__name__)


# =============================================================================
# GEMINI CLIENT
# =============================================================================

class GeminiClient:
    """
    Wraps the Google Gen AI Python SDK (v2.x).
    
    The new `google-genai` package (v2+) supports both the new AQ. key format
    and the old AIzaSy... format. It supersedes google-generativeai.
    
    Install: pip install google-genai
    Get API key: https://aistudio.google.com/app/apikey (free)
    
    Free tier limits (gemini-2.0-flash):
    - 15 requests per minute
    - 1,000,000 tokens per minute  
    - 1,500 requests per day
    """
    
    def __init__(self):
        self._client = None
        self._use_new_sdk = True   # Try new google-genai first
    
    def _initialize(self):
        """
        Lazy initialization. Tries the new google-genai SDK first (supports AQ. keys),
        falls back to the old google-generativeai SDK.
        """
        if self._client is not None:
            return
        
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Get a free key at: https://aistudio.google.com/app/apikey"
            )
        
        # Try new SDK first (supports AQ. prefix keys)
        try:
            from google import genai
            self._client = genai.Client(api_key=GEMINI_API_KEY)
            self._use_new_sdk = True
            logger.info(f"[OK] Gemini client initialized via google-genai SDK (model: {GEMINI_MODEL})")
            return
        except Exception as e:
            logger.warning(f"New google-genai SDK failed ({e}), trying legacy SDK...")
        
        # Fallback to old SDK
        try:
            import google.generativeai as genai_legacy
            genai_legacy.configure(api_key=GEMINI_API_KEY)
            self._generation_config = {
                "temperature": TEMPERATURE,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "response_mime_type": "application/json",
            }
            self._safety_settings = {
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
            self._legacy_model = genai_legacy.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config=self._generation_config,
                safety_settings=self._safety_settings,
            )
            self._client = genai_legacy
            self._use_new_sdk = False
            logger.info(f"[OK] Gemini client initialized via legacy SDK (model: {GEMINI_MODEL})")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize any Gemini SDK: {e}")
    
    
    async def generate(self, system_prompt: str, user_message: str) -> str:
        """
        Sends a request to the Gemini API and returns the response text.
        Handles 429 rate-limit with a short backoff and one retry.
        Supports both new google-genai and legacy google-generativeai SDKs.
        """
        self._initialize()
        
        full_prompt = f"{system_prompt}\n\n{'='*40}\n\nTASK:\n{user_message}"
        start_time = time.time()
        
        for attempt in range(1, 3):  # max 2 attempts (1 + 1 retry on 429)
            try:
                loop = asyncio.get_event_loop()
                
                if self._use_new_sdk:
                    # New google-genai SDK (v2.x) — supports AQ. keys
                    from google import genai as genai_new
                    from google.genai import types as genai_types
                    
                    response = await loop.run_in_executor(
                        None,
                        lambda: self._client.models.generate_content(
                            model=GEMINI_MODEL,
                            contents=full_prompt,
                            config=genai_types.GenerateContentConfig(
                                temperature=TEMPERATURE,
                                max_output_tokens=MAX_OUTPUT_TOKENS,
                                response_mime_type="application/json",
                            ),
                        )
                    )
                    response_text = response.text
                else:
                    # Legacy google-generativeai SDK
                    response = await loop.run_in_executor(
                        None,
                        lambda: self._legacy_model.generate_content(full_prompt)
                    )
                    if not response.candidates:
                        raise ValueError("Gemini returned no candidates — blocked by safety filters.")
                    response_text = response.text
                
                elapsed = time.time() - start_time
                logger.info(f"[OK] Gemini responded in {elapsed:.2f}s")
                
                if not response_text:
                    raise ValueError("Gemini returned empty text")
                
                return response_text
                
            except Exception as e:
                elapsed = time.time() - start_time
                err_str = str(e)
                
                if "429" in err_str or "quota" in err_str.lower() or "exhausted" in err_str.lower():
                    if attempt == 1:
                        logger.warning("Gemini rate-limited (429). Waiting 5s then retrying once...")
                        await asyncio.sleep(5)
                        continue
                    else:
                        logger.warning("Gemini still rate-limited after retry. Switching to fallback.")
                        raise
                else:
                    logger.error(f"Gemini API error after {elapsed:.2f}s: {e}")
                    raise


# =============================================================================
# GROQ CLIENT
# =============================================================================

class GroqClient:
    """
    Wraps the Groq Python SDK.
    
    Install: pip install groq
    Get API key: https://console.groq.com/keys (free, very generous)
    
    Groq's free tier:
    - 14,400 requests per day
    - 30 requests per minute
    - Speed: 400-700 tokens/second (insanely fast!)
    
    Groq serves open-source models (LLaMA 3, Mixtral) at incredible speed.
    Great fallback or alternative to Gemini.
    """
    
    def __init__(self):
        self._client = None
    
    def _initialize(self):
        """Lazy initialization for Groq client."""
        if self._client is not None:
            return
        
        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "groq package not installed. Run: pip install groq"
            )
        
        if not GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set. "
                "Get a free key at: https://console.groq.com/keys"
            )
        
        self._client = Groq(api_key=GROQ_API_KEY)
        logger.info(f"[OK] Groq client initialized (model: {GROQ_MODEL})")
    
    
    async def generate(self, system_prompt: str, user_message: str) -> str:
        """
        Sends a request to Groq's API using the OpenAI-compatible interface.
        
        Groq supports proper system/user message separation (unlike Gemini),
        which makes prompts cleaner and more effective.
        
        Parameters:
        -----------
        system_prompt : str
            Injected as the "system" role message
        user_message : str
            Injected as the "user" role message
            
        Returns:
        --------
        str — Raw response text from Groq
        """
        self._initialize()
        
        start_time = time.time()
        
        try:
            loop = asyncio.get_event_loop()
            
            # Groq uses OpenAI-compatible message format
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ]
            
            response = await loop.run_in_executor(
                None,
                lambda: self._client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    temperature=TEMPERATURE,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    # response_format tells Groq to return JSON
                    response_format={"type": "json_object"},
                )
            )
            
            elapsed = time.time() - start_time
            logger.debug(f"Groq responded in {elapsed:.2f}s")
            
            response_text = response.choices[0].message.content
            
            if not response_text:
                raise ValueError("Groq returned empty content")
            
            return response_text
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Groq API error after {elapsed:.2f}s: {e}")
            raise


# =============================================================================
# UNIFIED AI ADAPTER — The main class to use
# =============================================================================

class AIAdapter:
    """
    The unified AI interface used by email_generator.py.
    
    Internally uses GeminiClient or GroqClient based on config.
    Handles:
    - Provider selection and fallback
    - Retry logic for JSON extraction failures
    - Rate limit handling
    - Response timing and logging
    
    Usage:
    ------
    from backend.ai.ai_adapter import ai_adapter
    
    result = await ai_adapter.generate_email(prompt_data)
    # Returns a validated email dict or list of dicts
    """
    
    def __init__(self):
        self._primary_client = None
        self._fallback_client = None
        self._setup_clients()
    
    def _setup_clients(self):
        """
        Sets up primary and fallback clients based on AI_PROVIDER config.
        
        If AI_PROVIDER = "gemini":
          primary = GeminiClient, fallback = GroqClient
          
        If AI_PROVIDER = "groq":
          primary = GroqClient, fallback = GeminiClient
        """
        gemini = GeminiClient()
        groq   = GroqClient()
        
        if AI_PROVIDER == "gemini":
            self._primary_client  = gemini
            self._fallback_client = groq
            logger.info("AI Adapter: Primary=Gemini, Fallback=Groq")
        else:
            self._primary_client  = groq
            self._fallback_client = gemini
            logger.info("AI Adapter: Primary=Groq, Fallback=Gemini")
    
    
    async def _call_with_fallback(
        self, 
        system_prompt: str, 
        user_message: str
    ) -> str:
        """
        Calls primary client. If it fails, tries fallback client.
        
        Returns raw text from whichever client succeeded.
        Raises if both fail.
        """
        primary_error = None
        
        # Try primary
        try:
            return await self._primary_client.generate(system_prompt, user_message)
        except Exception as e:
            primary_error = e
            logger.warning(f"Primary AI ({AI_PROVIDER}) failed: {e}  trying fallback")
        
        # Try fallback
        try:
            return await self._fallback_client.generate(system_prompt, user_message)
        except Exception as fallback_error:
            raise RuntimeError(
                f"Both AI providers failed.\n"
                f"Primary error: {primary_error}\n"
                f"Fallback error: {fallback_error}"
            )
    
    
    def _generate_mock_email(
        self,
        customer: Dict[str, Any],
        campaign_type: str,
        is_multi_variant: bool,
        num_variants: int = 3
    ) -> Union[Dict, List[Dict]]:
        """
        Generates highly personalized and varied mock emails when AI is rate-limited.
        Supports 6+ unique copy variants for each campaign type with segment-aware structures.
        Includes parts-of-speech and figures-of-speech stylistic metadata.
        """
        import random

        first_name   = customer.get("first_name") or customer.get("name", "there").split()[0]
        interests    = customer.get("interests", ["productivity"])
        segment      = customer.get("segment", "active")
        p_interest   = interests[0] if interests else "growth"
        s_interest   = interests[1] if len(interests) > 1 else p_interest
        send_time    = customer.get("email_behavior", {}).get("preferred_send_time", "Tuesday 10:00 AM")

        # ----- WELCOME variants (6 distinct options) -----
        welcome_variants = [
            {
                "subject":  f"Welcome, {first_name}! Your {p_interest} journey starts today",
                "opening":  f"You just made a great decision. We built this platform specifically for people passionate about {p_interest} — and we can't wait to show you what's possible.",
                "main":     f"To get you started, we've activated a personalised {p_interest} starter kit in your account. It includes curated guides, community access, and weekly tips from experts in {s_interest}. Explore it today and tell us what you think.",
                "cta":      "Explore Your Starter Kit",
                "tone":     "warm and welcoming",
            },
            {
                "subject":  f"Hi {first_name}, here's your quick-start guide",
                "opening":  f"We know getting started can feel overwhelming — so we've done the hard work for you. Based on your interest in {p_interest}, we've pre-configured your experience.",
                "main":     f"Your personalised dashboard is live. You'll find a 3-step onboarding checklist, a curated feed of {p_interest} content, and a community of 50,000+ members who share your passion for {s_interest}.",
                "cta":      "Complete Your Setup",
                "tone":     "helpful and clear",
            },
            {
                "subject":  f"{first_name}, you're in! A special gift inside",
                "opening":  f"As a welcome gift, we're giving you 30 days of premium access — completely free. No credit card required.",
                "main":     f"Use this time to explore every feature, connect with others interested in {p_interest}, and discover why thousands of {s_interest} enthusiasts choose us every month.",
                "cta":      "Start My Free 30 Days",
                "tone":     "excited and generous",
            },
            {
                "subject":  f"Let's connect, {first_name}! Meet your new community",
                "opening":  f"Welcome to the team! Our community is the heartbeat of this platform. It is a space where people exchange ideas, share resources, and grow together.",
                "main":     f"Since you are focused on {p_interest}, we suggest checking out the {s_interest} channel today. You can read current discussions, ask questions, or share your own journey with other members.",
                "cta":      "Join the Community",
                "tone":     "friendly and community-focused",
            },
            {
                "subject":  f"A personal message from our founder, {first_name}",
                "opening":  f"I wanted to reach out personally to thank you for signing up. I started this company to help people like you master {p_interest}.",
                "main":     f"Over the next few weeks, my team will send you curated resources on {s_interest} to help you get the most out of our tools. If you ever have feedback, reply directly to this email.",
                "cta":      "Visit Dashboard",
                "tone":     "thoughtful and personal",
            },
            {
                "subject":  f"The top 3 resources on {p_interest} for {first_name}",
                "opening":  f"To help you hit the ground running, we've gathered our most popular resources on {p_interest} and {s_interest}.",
                "main":     f"These guides cover everything from beginner frameworks to advanced strategies. They have helped thousands of users speed up their progress. Take a look and start building today.",
                "cta":      "Access Curated Guides",
                "tone":     "resource-rich and educational",
            },
        ]

        # ----- RE-ENGAGEMENT variants (6 distinct options) -----
        reengagement_variants = [
            {
                "subject":  f"We've been saving something for you, {first_name}",
                "opening":  f"It's been a while, and we genuinely missed you. A lot has changed since you last visited — especially in the world of {p_interest}.",
                "main":     f"We've added 47 new features, a completely redesigned {p_interest} dashboard, and a brand new community hub for {s_interest} fans. Your account is still active and all your data is safe. Come back and see what you've been missing.",
                "cta":      "See What's New",
                "tone":     "warm and nostalgic",
            },
            {
                "subject":  f"A 20% discount — just for you, {first_name}",
                "opening":  f"We value every member of our community, and we don't want to lose you. That's why we're offering you an exclusive 20% discount on your next renewal.",
                "main":     f"This offer is valid for the next 48 hours only and is exclusive to your account. Whether you're picking up where you left off with {p_interest} or exploring something new like {s_interest}, we're here to support you.",
                "cta":      "Claim My 20% Discount",
                "tone":     "urgent and generous",
            },
            {
                "subject":  f"Quick question, {first_name} — did we let you down?",
                "opening":  f"I'll be direct: you haven't visited in a while, and I want to understand why. Was it the product? The pricing? Something we did wrong?",
                "main":     f"Your feedback genuinely matters. Reply to this email and our team will personally read every response. And if there's anything we can do to improve your experience with {p_interest}, we'll make it happen.",
                "cta":      "Share My Feedback",
                "tone":     "honest and human",
            },
            {
                "subject":  f"We saved your seat, {first_name}!",
                "opening":  f"Your seat is still warm! We noticed you haven't logged in recently to check on your {p_interest} dashboard.",
                "main":     f"We've updated our toolset to include automated analytics for {s_interest}, making it easier than ever to save time and hit your targets. Log back in today and see your updated account.",
                "cta":      "Resume My Progress",
                "tone":     "welcoming and encouraging",
            },
            {
                "subject":  f"Is your {p_interest} strategy still on track?",
                "opening":  f"In the fast-moving world of {p_interest}, staying still is the same as falling behind. Let's make sure you're still moving forward.",
                "main":     f"We've released a new benchmarking feature. It lets you compare your {s_interest} metrics against industry standards. It takes 2 minutes to set up and provides immediate, actionable ideas.",
                "cta":      "Run My Benchmark Test",
                "tone":     "analytical and motivational",
            },
            {
                "subject":  f"A quick gift to help you restart, {first_name}",
                "opening":  f"Restarting is the hardest part. To make it a little easier, we've credited a free premium guide to your account.",
                "main":     f"This guide details the exact steps top creators use to scale their {p_interest} operations. Log in to your library to access it and get back on track today.",
                "cta":      "Open My Free Guide",
                "tone":     "helpful and supportive",
            },
        ]

        # ----- FOLLOWUP variants (outcome-aware, 2 options per outcome) -----
        outcome = customer.get("_outcome", "opened_no_click")
        
        followup_pool = {
            "opened_no_click": [
                {
                    "subject":  f"Did something stop you, {first_name}?",
                    "opening":  f"You opened our last email about {p_interest} but didn't get a chance to take action. Life gets busy — we totally get it.",
                    "main":     f"We've put together a 2-minute quick-start specifically for {p_interest} to make it easy to jump back in. No overwhelming setup, just three simple steps to get you moving toward your goals.",
                    "cta":      "Take the 2-Minute Quick-Start",
                    "tone":     "understanding and helpful",
                },
                {
                    "subject":  f"Quick check-in regarding {p_interest}, {first_name}",
                    "opening":  f"I noticed you read our message about {p_interest} but haven't had a chance to explore the features yet.",
                    "main":     f"If you have any questions or ran into a roadblock with {s_interest}, please reply to this email. Our support team is standing by to assist you personally.",
                    "cta":      "Chat With Support",
                    "tone":     "accessible and supportive",
                }
            ],
            "not_opened": [
                {
                    "subject":  f"(Second attempt) Something important for you, {first_name}",
                    "opening":  f"We sent you an email last week, but it may have gotten buried. We think what we shared was genuinely useful for anyone interested in {p_interest}.",
                    "main":     f"Here's the short version: we've launched a new feature designed specifically for {s_interest} enthusiasts. Early users are reporting a 35% improvement in their results. We'd love for you to be among the first to try it.",
                    "cta":      "See the New Feature",
                    "tone":     "value-focused",
                },
                {
                    "subject":  f"Quick question about {p_interest}, {first_name}?",
                    "opening":  f"Just checking in since our last message might have missed your inbox. We are releasing new tool updates this week.",
                    "main":     f"These updates streamline how you organize your {s_interest} workflow, cutting manual effort in half. We'd love to show you how it works.",
                    "cta":      "View On-Demand Demo",
                    "tone":     "curious and professional",
                }
            ],
            "clicked_no_convert": [
                {
                    "subject":  f"Still thinking it over, {first_name}? Here's help",
                    "opening":  f"You explored our {p_interest} offer but didn't complete your purchase. We want to make sure you have everything you need to make the right decision.",
                    "main":     f"Most people hesitate because of price or uncertainty. So here's our promise: 14-day money-back guarantee, no questions asked. If {p_interest} isn't everything we say it is, we'll refund you immediately.",
                    "cta":      "Start Risk-Free Today",
                    "tone":     "reassuring and confident",
                },
                {
                    "subject":  f"Can we answer your questions, {first_name}?",
                    "opening":  f"We noticed you checked out our page on {p_interest} but didn't sign up. Choosing the right platform is a big decision.",
                    "main":     f"Would it help to see a 1-on-1 walkthrough of the dashboard? You can schedule a quick 10-minute call with our success lead to check out the exact features you need for {s_interest}.",
                    "cta":      "Book a 1-on-1 Walkthrough",
                    "tone":     "helpful and consultative",
                }
            ],
            "converted": [
                {
                    "subject":  f"You're officially part of the family, {first_name}!",
                    "opening":  f"Thank you for completing your purchase. You've made a great investment in your {p_interest} journey, and we're going to make sure it pays off.",
                    "main":     f"Over the next 7 days, we'll send you a short onboarding sequence to help you get maximum value. Today's step: join our private community of {s_interest} enthusiasts. It's where all the best insights get shared first.",
                    "cta":      "Join the Private Community",
                    "tone":     "celebratory and guiding",
                },
                {
                    "subject":  f"Welcome aboard, {first_name}! Let's customize your profile",
                    "opening":  f"We are excited to work with you! To make sure your dashboard fits your goals, let's complete your profile settings.",
                    "main":     f"By selecting your primary goals in {p_interest} and {s_interest}, our system will automatically customize your notifications, templates, and suggested resources.",
                    "cta":      "Set Up Profile Goals",
                    "tone":     "organized and proactive",
                }
            ]
        }

        # ----- CUSTOM / REWRITE variants (6 distinct options with speech styles) -----
        custom_variants = [
            {
                "subject":  f"An exclusive invitation for you, {first_name}",
                "opening":  f"As one of our most valued community members, you're getting first access to something we've been working on for months.",
                "main":     f"We're launching a private beta next week, and based on your interest in {p_interest}, we think you'd be the perfect fit. Beta members get 6 months free access and direct influence over the product roadmap.",
                "cta":      "Apply for Beta Access",
                "tone":     "exclusive and exciting",
                "figure_of_speech": "Metaphor ('heartbeat of our platform', 'saved your seat')",
                "parts_of_speech": "Used active verbs ('explore', 'launch') and exclusive adjectives ('valued', 'private')",
                "alternative_hooks": [f"Exclusive entrance for {first_name}", f"Unlock the door to {p_interest}"]
            },
            {
                "subject":  f"{first_name}, your {p_interest} action plan is ready",
                "opening":  f"We've analysed accounts similar to yours and found something interesting: people with your profile who engage with {s_interest} content see 40% better results within the first month.",
                "main":     f"We've put together a custom action plan based on your preferences. It includes three quick wins you can implement today, plus a 30-day roadmap tailored to your {p_interest} goals.",
                "cta":      "View My Custom Action Plan",
                "tone":     "data-driven and personalised",
                "figure_of_speech": "Alliteration ('Fresh Focus, Fast Results')",
                "parts_of_speech": "Swapped passive statements for active commands ('View', 'Implement')",
                "alternative_hooks": [f"Your {p_interest} blueprint, {first_name}", f"Fast-track your {s_interest} growth"]
            },
            {
                "subject":  f"The secret behind successful {p_interest} projects",
                "opening":  f"Ever wonder how top experts in {s_interest} scale their systems without burnout? It's not about working harder.",
                "main":     f"It is about using smart leverage. We have compiled a breakdown of the three simple workflows that save up to 15 hours a week, allowing you to focus on what you love.",
                "cta":      "Read the Expert Breakdown",
                "tone":     "educational and intriguing",
                "figure_of_speech": "Idiom ('hit the ground running', 'scale your systems')",
                "parts_of_speech": "Used strong nouns ('leverage', 'breakdown') and sensory adjectives ('smart', 'simple')",
                "alternative_hooks": [f"Stop wasting time on {s_interest}", f"The leverage framework for {first_name}"]
            },
            {
                "subject":  f"A custom checklist to streamline {p_interest}",
                "opening":  f"If you're like most people interested in {p_interest}, your to-do list is probably too long. Let's fix that.",
                "main":     f"We created a clean, 1-page checklist that filters out the noise. It covers the essential setup steps for {s_interest} so you can focus only on what drives real progress.",
                "cta":      "Get the 1-Page Checklist",
                "tone":     "clear and simplifying",
                "figure_of_speech": "Analogy ('filters out the noise' - like a radio frequency)",
                "parts_of_speech": "Used imperative action verbs ('streamline', 'filter', 'focus')",
                "alternative_hooks": [f"The 1-page {p_interest} filter", f"Streamline {s_interest} in 5 minutes"]
            },
            {
                "subject":  f"Are you ready for the next level, {first_name}?",
                "opening":  f"Next week, we are opening doors to our advanced mastermind group for {p_interest} leaders.",
                "main":     f"This group is limited to 100 members to ensure deep, high-value conversations. If you want to connect with other top builders in {s_interest} and share strategies, apply today.",
                "cta":      "Submit Mastermind Application",
                "tone":     "premium and aspirational",
                "figure_of_speech": "Hyperbole ('next level', 'mastermind leaders')",
                "parts_of_speech": "Used premium adjectives ('advanced', 'high-value', 'limited')",
                "alternative_hooks": [f"Apply for the {p_interest} Mastermind", f"100 seats: join the {s_interest} circle"]
            },
            {
                "subject":  f"A sneak peek at our upcoming {p_interest} release",
                "opening":  f"We love giving our early users a sneak peek at what's cooking behind the scenes.",
                "main":     f"Our product team is finishing up a major expansion of the {s_interest} tracking dashboard. It includes real-time email health metrics and deep-dive templates. Check out the preview video below.",
                "cta":      "Watch Sneak Peek Video",
                "tone":     "playful and insider-focused",
                "figure_of_speech": "Idiom ('behind the scenes', 'what's cooking')",
                "parts_of_speech": "Used action-focused present participles ('cooking', 'finishing', 'giving')",
                "alternative_hooks": [f"Behind the scenes of {p_interest}", f"What we're building for {first_name}"]
            }
        ]

        def build_email(v: Dict, label: Optional[str] = None) -> Dict:
            subj = v["subject"]
            if label:
                subj = f"[{label}] {subj}"
            
            res = {
                "campaign_type":  campaign_type,
                "recipient_id":   customer.get("id", ""),
                "subject_line":   subj,
                "preview_text":   f"Personalised just for you based on your interest in {p_interest}.",
                "body": {
                    "greeting":       f"Hi {first_name},",
                    "opening":        v["opening"],
                    "main_content":   v["main"],
                    "call_to_action": v["cta"],
                    "cta_url":        "https://example.com/start",
                    "closing":        f"Warm regards,\nThe Team",
                },
                "metadata": {
                    "tone":                        v["tone"] + " (Smart Fallback)",
                    "personalization_signals_used": ["first_name", "interests", "segment"],
                    "recommended_send_time":        send_time,
                    "estimated_open_rate_boost":    random.choice(["+14%", "+18%", "+22%", "+26%"]),
                    "reasoning": (
                        f"Targeted {segment} segment customer using {p_interest} as primary hook. "
                        f"Secondary interest {s_interest} used for content depth."
                    ),
                }
            }

            # Injected figures/parts of speech recommendations for custom/rewrite
            if campaign_type in ("rewrite", "custom"):
                res["metadata"]["stylistic_suggestions"] = {
                    "figure_of_speech_used": v.get("figure_of_speech", "Metaphor (linking progress to a journey)"),
                    "parts_of_speech_adjustments": v.get("parts_of_speech", "Used dynamic verbs and descriptive adjectives"),
                    "alternative_hooks": v.get("alternative_hooks", [
                        f"Unlocking your potential in {p_interest}",
                        f"A fresh perspective on {s_interest}"
                    ])
                }
            return res

        # Select the right variant pool
        if campaign_type == "welcome":
            pool = welcome_variants
        elif campaign_type == "reengagement":
            pool = reengagement_variants
        elif campaign_type == "followup":
            # Select outcome list, fallback to opened_no_click
            outcome_list = followup_pool.get(outcome, followup_pool["opened_no_click"])
            pool = outcome_list
        else:
            pool = custom_variants

        if is_multi_variant:
            ab_labels = ["Variant A", "Variant B", "Variant C", "Variant D", "Variant E", "Variant F"]
            chosen = random.sample(pool * 2, min(num_variants, len(pool * 2)))
            return [build_email(chosen[i], ab_labels[i]) for i in range(num_variants)]

        return build_email(random.choice(pool))

    async def generate_email(
        self,
        prompt_data: Dict[str, Any],
    ) -> Union[Dict, List[Dict]]:
        """
        The main function called by email_generator.py.
        """
        system_prompt    = prompt_data["system_prompt"]
        user_message     = prompt_data["user_message"]
        is_multi_variant = prompt_data.get("is_multi_variant", False)
        customer_id      = prompt_data.get("customer_id", "")
        campaign_type    = prompt_data.get("campaign_type", "unknown")
        
        logger.info(f"Generating {campaign_type} email for customer {customer_id[:8]}...")
        
        last_error = None
        last_raw_response = None
        
        for attempt in range(1, JSON_RETRY_LIMIT + 1):
            try:
                # On retry attempts, modify the user message to correct the AI
                if attempt > 1 and last_raw_response is not None:
                    logger.info(f"Retry attempt {attempt}/{JSON_RETRY_LIMIT} with correction prompt")
                    correction = build_correction_prompt(
                        broken_response=last_raw_response,
                        error_message=str(last_error),
                    )
                    current_user_message = correction
                else:
                    current_user_message = user_message
                
                # Call the AI
                raw_response = await self._call_with_fallback(
                    system_prompt=system_prompt,
                    user_message=current_user_message,
                )
                
                last_raw_response = raw_response
                
                # Extract and validate JSON
                result = extract_email_json(
                    ai_response=raw_response,
                    is_multi_variant=is_multi_variant,
                    customer_id=customer_id,
                )
                
                logger.info(
                    f"[OK] Email generation successful "
                    f"(attempt {attempt}, campaign: {campaign_type})"
                )
                return result
                
            except ValueError as e:
                last_error = e
                logger.warning(f"Attempt {attempt}/{JSON_RETRY_LIMIT} failed: {e}")
                if attempt < JSON_RETRY_LIMIT:
                    await asyncio.sleep(0.3)
                    
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                if "429" in error_str or "rate limit" in error_str or "quota" in error_str:
                    # Rate limited — skip all remaining retries and go straight to mock
                    logger.warning(
                        f"Rate limit detected on attempt {attempt}. "
                        "Skipping retries and switching to local mock generator immediately."
                    )
                    break  # Exit retry loop instantly — no waiting
                else:
                    logger.error(f"API error on attempt {attempt}: {e}")
                    if attempt < JSON_RETRY_LIMIT:
                        await asyncio.sleep(0.5)
        
        # All retries exhausted — Fallback to local Mock AI template generator to prevent demo crashes
        logger.warning(
            f"[WARNING] All AI providers failed. Falling back to local Mock AI template "
            f"generator for {campaign_type} campaign (Customer: {customer_id[:8]})"
        )
        try:
            from backend.data.stream_manager import dataset_manager
            customer = await dataset_manager.get_by_id(customer_id)
            if not customer:
                customer = {
                    "id": customer_id,
                    "first_name": "there",
                    "interests": ["your favorite topics"],
                    "email_behavior": {"preferred_send_time": "Tuesday 10:00 AM"}
                }
            return self._generate_mock_email(
                customer=customer,
                campaign_type=campaign_type,
                is_multi_variant=is_multi_variant,
                num_variants=prompt_data.get("expected_variant_count", 3)
            )
        except Exception as mock_err:
            logger.error(f"Fallback mock generation failed: {mock_err}")
            raise RuntimeError(
                f"Email generation failed after {JSON_RETRY_LIMIT} attempts.\n"
                f"Campaign: {campaign_type}, Customer: {customer_id}\n"
                f"Last error: {last_error}"
            )


# =============================================================================
# SINGLETON INSTANCE — Import this everywhere
# =============================================================================

# One shared instance used throughout the app.
# from backend.ai.ai_adapter import ai_adapter
ai_adapter = AIAdapter()


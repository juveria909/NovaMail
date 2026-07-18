"""
main.py — FastAPI Application Entry Point
==========================================
This is the SERVER. It starts everything up and handles HTTP requests.

HOW FASTAPI WORKS (Simple explanation):
-----------------------------------------
FastAPI is a Python web framework. When you run this file:
1. A server starts at http://localhost:8000
2. It listens for HTTP requests (from Postman, browser, your frontend, etc.)
3. Based on the URL path, it calls the right function
4. That function returns data as JSON

ROUTES WE DEFINE:
-----------------
GET  /                           → Health check (is the server alive?)
GET  /api/dataset                → Get live dataset records
GET  /api/dataset/stats          → Get dataset statistics
GET  /api/dataset/segments       → Get records by segment
GET  /api/dataset/search         → Search customers by name/email/interest
POST /api/email/generate         → Generate email(s) for one customer
POST /api/email/batch            → Generate emails for many customers
POST /api/email/rewrite          → Rewrite an existing email
POST /api/email/followup         → Generate follow-up email

LIFESPAN (startup/shutdown):
-----------------------------
FastAPI's lifespan context manager lets us:
  - At startup: Load the dataset, validate config, check APIs
  - At shutdown: Stop the refresh loop cleanly

This is better than @app.on_event("startup") which is deprecated in newer FastAPI.

CORS:
-----
Cross-Origin Resource Sharing — allows your frontend (different port/domain)
to make requests to this backend. Without CORS headers, browsers block the request.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Import our modules
from backend.config import validate_config, SERVER_HOST, SERVER_PORT
from backend.data.live_fetcher import check_api_health
from backend.data.stream_manager import dataset_manager
from backend.ai.email_generator import (
    generate_welcome_email,
    generate_reengagement_email,
    generate_ab_variants,
    generate_followup_email,
    generate_rewrite,
    generate_custom_campaign,
    generate_batch_campaign,
    generate_campaign_email,
)

# Set up logging — all log messages go to console with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# =============================================================================
# STARTUP / SHUTDOWN (Lifespan)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Everything in the `try` block runs at STARTUP.
    Everything after `yield` runs at SHUTDOWN.
    
    We use `yield` as the dividing line — it means "now handle requests".
    """
    
    # ---- STARTUP ----
    logger.info("=" * 50)
    logger.info("AI Email Campaign Agent -- Starting up")
    logger.info("=" * 50)
    
    # Step 1: Validate configuration (crash early if API keys missing)
    try:
        validate_config()
    except EnvironmentError as e:
        logger.error(f"Config validation failed: {e}")
        # Don't prevent startup — let the app run with warnings
        # This allows testing dataset endpoints even without AI keys
    
    # Step 2 + 3: Run health check AND dataset init IN PARALLEL
    # This cuts startup time — no reason to wait for one before the other
    logger.info("Initializing dataset + checking API connectivity (parallel)...")
    
    health_result = [None]
    init_error = [None]
    
    async def _health():
        h = await check_api_health()
        health_result[0] = h
    
    async def _init():
        try:
            await dataset_manager.initialize()
        except Exception as e:
            init_error[0] = e
    
    await asyncio.gather(_health(), _init())
    
    # Log results
    health = health_result[0]
    if health and health["healthy"]:
        logger.info(f"[OK] RandomUser.me API: reachable ({health['latency_ms']}ms)")
    elif health:
        logger.warning(f"[WARNING]  RandomUser.me API: unreachable  {health['error']}")
    
    if init_error[0]:
        logger.error(f"Dataset initialization failed: {init_error[0]}")
    else:
        logger.info("[OK] Dataset initialized and live refresh started")
    
    logger.info("=" * 50)
    logger.info(f"[OK] Server ready at http://{SERVER_HOST}:{SERVER_PORT}")
    logger.info(f"   Docs: http://localhost:{SERVER_PORT}/docs")
    logger.info("=" * 50)
    
    yield  # <--- Server is now handling requests
    
    # ---- SHUTDOWN ----
    logger.info("Shutting down...")
    await dataset_manager.shutdown()
    logger.info("[OK] Shutdown complete")


# =============================================================================
# FASTAPI APP INSTANCE
# =============================================================================

app = FastAPI(
    title="AI Email Campaign Automation Agent",
    description=(
        "Generates highly personalized email campaigns using Gemini AI. "
        "Features a live 1000-record customer dataset refreshed from the web."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",       # Swagger UI at /docs
    redoc_url="/redoc",     # ReDoc at /redoc
)

# Allow all origins in development
# In production: replace "*" with your specific frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
import os
os.makedirs(os.path.join("backend", "static"), exist_ok=True)
app.mount("/static", StaticFiles(directory="backend/static"), name="static")


# =============================================================================
# REQUEST / RESPONSE MODELS (Pydantic)
# =============================================================================
# Pydantic models define what JSON the API accepts and returns.
# FastAPI uses these for automatic validation — if the client sends the wrong
# data type, FastAPI returns a clear error message instead of crashing.

class GenerateEmailRequest(BaseModel):
    """Request body for POST /api/email/generate"""
    
    campaign_type: str = Field(
        default="welcome",
        description="Type of email: welcome | reengagement | variant_test | custom | cold_outreach | newsletter | product_launch | sales_pitch"
    )
    customer_id: Optional[str] = Field(
        default=None,
        description="Specific customer UUID. If not provided, a random customer is chosen."
    )
    send: bool = Field(
        default=False,
        description="If true, sends the email via SendGrid after generating."
    )
    to_override: Optional[str] = Field(
        default=None,
        description="Send to this real email address instead of the customer's fake one. Useful for demo."
    )
    # For variant_test campaigns
    num_variants: int = Field(
        default=3,
        ge=2, le=5,
        description="Number of A/B variants to generate (2-5). Only for variant_test."
    )
    base_campaign_type: str = Field(
        default="reengagement",
        description="Base campaign type for variant testing: welcome | reengagement"
    )
    # For custom campaigns
    user_instructions: Optional[str] = Field(
        default=None,
        description="Free-form instructions for custom campaigns."
    )


class FollowupEmailRequest(BaseModel):
    """Request body for POST /api/email/followup"""
    
    customer_id: Optional[str] = Field(
        default=None,
        description="UUID of the customer to follow up with. If not provided, a random customer is chosen."
    )
    previous_email_subject: Optional[str] = Field(
        default="Welcome to our platform!",
        description="Subject line of the email we're following up on"
    )
    outcome: Optional[str] = Field(
        default="opened_no_click",
        description=(
            "What happened with the previous email: "
            "opened_no_click | not_opened | clicked_no_convert | converted"
        )
    )
    send: bool = Field(default=False)
    to_override: Optional[str] = Field(
        default=None,
        description="Send to this real email address instead of the customer's dataset email. Use for demos."
    )


class RewriteEmailRequest(BaseModel):
    """Request body for POST /api/email/rewrite"""
    
    customer_id: Optional[str] = Field(
        default=None,
        description="UUID of the customer. If not provided, a random customer is chosen."
    )
    original_email: Optional[str] = Field(
        default="Hi, welcome to our company. Let us know if you need anything.",
        description="The original email content to rewrite"
    )
    feedback: Optional[str] = Field(
        default="make it more professional and engaging",
        description="What to change: 'make it shorter', 'more urgent', etc."
    )


class BatchCampaignRequest(BaseModel):
    """Request body for POST /api/email/batch"""
    
    campaign_type: str = Field(
        default="reengagement",
        description="Campaign type to generate for all customers"
    )
    segment: Optional[str] = Field(
        default=None,
        description="Target segment. If None, uses best segment for campaign type."
    )
    limit: int = Field(
        default=5,
        ge=1, le=20,
        description="How many customers to generate emails for (max 20 per call)"
    )
    send: bool = Field(
        default=False,
        description="Send all generated emails via SendGrid"
    )


# =============================================================================
# ROUTES — SYSTEM
# =============================================================================

@app.get("/", tags=["System"], response_class=HTMLResponse)
async def root():
    """Informs the user that the UI has migrated to Streamlit."""
    return HTMLResponse(content="""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 80px auto; padding: 40px; border-radius: 12px; background-color: #0f172a; color: #f8fafc; box-shadow: 0 4px 20px rgba(0,0,0,0.3); border: 1px solid #1e293b; text-align: center;">
        <h1 style="color: #38bdf8; font-size: 24px; margin-bottom: 20px;">🌌 Antigravity AI Email Suite</h1>
        <p style="color: #94a3b8; font-size: 15px; line-height: 1.6; margin-bottom: 30px;">
            The email campaign platform frontend has been successfully migrated to <strong>Streamlit</strong> for a more professional, interactive dashboard experience.
        </p>
        <div style="margin-bottom: 30px;">
            <a href="http://localhost:8501" target="_blank" style="display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #6366f1, #a855f7); color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 15px; box-shadow: 0 4px 10px rgba(99, 102, 241, 0.4);">
                Open Streamlit App (Port 8501)
            </a>
        </div>
        <p style="font-size: 13px; color: #64748b;">
            To access the interactive API docs, visit <a href="/docs" style="color: #38bdf8; text-decoration: underline;">Swagger API Docs</a>.
        </p>
    </div>
    """)


@app.get("/api/health", tags=["System"])
async def health_check():
    """Detailed health check — checks dataset and external APIs."""
    api_health = await check_api_health()
    dataset_stats = await dataset_manager.get_stats()
    
    return {
        "server": "healthy",
        "randomuser_api": "healthy" if api_health["healthy"] else "unreachable",
        "randomuser_latency_ms": api_health.get("latency_ms"),
        "dataset": {
            "initialized": dataset_stats.get("is_initialized"),
            "total_records": dataset_stats.get("total_records"),
            "last_refresh": dataset_stats.get("last_refresh"),
            "refresh_count": dataset_stats.get("refresh_count"),
        }
    }


# =============================================================================
# ROUTES — DATASET (Part 1)
# =============================================================================

@app.get("/api/dataset", tags=["Dataset"])
async def get_dataset(
    limit: int = Query(default=50, ge=1, le=1000, description="Number of records to return"),
    segment: Optional[str] = Query(default=None, description="Filter by segment"),
):
    """
    Returns records from the live dataset.
    
    The dataset is continuously updated from RandomUser.me — 
    data changes every few seconds automatically.
    """
    if segment:
        records = await dataset_manager.get_by_segment(segment, limit=limit)
    else:
        records = await dataset_manager.get_all(limit=limit)
    
    return {
        "total_returned": len(records),
        "segment_filter": segment,
        "records": records,
    }


@app.get("/api/dataset/stats", tags=["Dataset"])
async def get_dataset_stats():
    """Returns statistics about the live dataset."""
    stats = await dataset_manager.get_stats()
    return stats


@app.get("/api/dataset/customer/{customer_id}", tags=["Dataset"])
async def get_customer(customer_id: str):
    """Returns a single customer record by their UUID."""
    customer = await dataset_manager.get_by_id(customer_id)
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer with ID '{customer_id}' not found in dataset."
        )
    return customer


@app.get("/api/dataset/search", tags=["Dataset"])
async def search_customers(
    q: str = Query(description="Search query — matches name, email, or interests"),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Searches customers by name, email, or interests."""
    if len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    results = await dataset_manager.search(q, limit=limit)
    return {
        "query": q,
        "total_found": len(results),
        "results": results,
    }


@app.get("/api/dataset/segments", tags=["Dataset"])
async def get_segments():
    """
    Returns counts for each customer segment.
    
    Segments: new_signup, new, active, inactive, high_value, at_risk
    """
    stats = await dataset_manager.get_stats()
    return {
        "segments": stats.get("segment_distribution", {}),
        "description": {
            "new_signup":  "Signed up in the last 7 days",
            "new":         "Signed up 8-30 days ago",
            "active":      "Engaged, regular customer",
            "inactive":    "No activity in 90+ days",
            "high_value":  "Frequent buyer, recently active",
            "at_risk":     "Starting to disengage (45-90 days inactive)",
        }
    }


# =============================================================================
# ROUTES — EMAIL GENERATION (Part 2)
# =============================================================================

@app.post("/api/email/generate", tags=["Email Generation"])
async def generate_email(request: GenerateEmailRequest):
    """
    Generates a personalized email using Gemini AI.
    
    Supports all campaign types:
    - welcome: New customer welcome
    - reengagement: Win back inactive users
    - variant_test: Generate A/B test variants
    - custom: Free-form user-defined campaign
    
    Returns the AI-generated email as structured JSON.
    Optionally sends it via SendGrid if send=true.
    """
    try:
        campaign_type = request.campaign_type.lower()
        
        # Sanitize Swagger placeholders ("string" or empty values)
        customer_id = request.customer_id
        if customer_id and customer_id.strip().lower() in ("string", ""):
            customer_id = None
            
        to_override = request.to_override
        if to_override and to_override.strip().lower() in ("string", ""):
            to_override = None
            
        base_campaign_type = request.base_campaign_type
        if base_campaign_type and base_campaign_type.strip().lower() in ("string", ""):
            base_campaign_type = "reengagement"
            
        user_instructions = request.user_instructions
        if user_instructions and user_instructions.strip().lower() in ("string", ""):
            user_instructions = None
        
        if campaign_type == "variant_test":
            result = await generate_ab_variants(
                customer_id=customer_id,
                base_campaign_type=base_campaign_type,
                num_variants=request.num_variants,
            )
        
        elif campaign_type == "custom":
            if not user_instructions:
                raise HTTPException(
                    status_code=400,
                    detail="user_instructions is required for custom campaigns"
                )
            result = await generate_custom_campaign(
                customer_id=customer_id,
                user_instructions=user_instructions,
                send=request.send,
                to_override=to_override,
            )
        
        elif campaign_type in ("welcome", "reengagement", "cold_outreach", "newsletter", "product_launch", "sales_pitch"):
            result = await generate_campaign_email(
                campaign_type=campaign_type,
                customer_id=customer_id,
                send=request.send,
                to_override=to_override,
            )
        
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown campaign_type '{campaign_type}'. "
                       f"Valid: welcome, reengagement, variant_test, custom, cold_outreach, newsletter, product_launch, sales_pitch"
            )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/email/preview", tags=["Email Generation"])
async def preview_campaign_email(
    campaign_type: str = Query(default="welcome", description="welcome | reengagement | cold_outreach | newsletter | product_launch | sales_pitch | custom"),
    customer_id: Optional[str] = Query(default=None),
    user_instructions: Optional[str] = Query(default=None),
):
    """
    Generates a campaign email and returns it directly as rendered HTML for preview.
    """
    try:
        if campaign_type == "custom":
            if not user_instructions:
                raise HTTPException(status_code=400, detail="user_instructions required for custom campaigns")
            res = await generate_custom_campaign(customer_id=customer_id, user_instructions=user_instructions)
        else:
            res = await generate_campaign_email(campaign_type=campaign_type, customer_id=customer_id)
        
        return HTMLResponse(content=res["html_content"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/email/download", tags=["Email Generation"])
async def download_campaign_email(
    campaign_type: str = Query(default="welcome"),
    customer_id: Optional[str] = Query(default=None),
    user_instructions: Optional[str] = Query(default=None),
):
    """
    Generates the HTML email and prompts the browser to download it as a .html file.
    """
    try:
        if campaign_type == "custom":
            if not user_instructions:
                raise HTTPException(status_code=400, detail="user_instructions required for custom campaigns")
            res = await generate_custom_campaign(customer_id=customer_id, user_instructions=user_instructions)
        else:
            res = await generate_campaign_email(campaign_type=campaign_type, customer_id=customer_id)
        
        headers = {
            "Content-Disposition": f"attachment; filename=\"{campaign_type}_email.html\""
        }
        return HTMLResponse(content=res["html_content"], headers=headers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/email/followup", tags=["Email Generation"])
async def create_followup_email(request: FollowupEmailRequest):
    """
    Generates a follow-up email based on how the previous email performed.
    
    outcome options:
    - opened_no_click: They opened but didn't click the CTA
    - not_opened: They didn't open at all
    - clicked_no_convert: Clicked CTA but didn't complete the action
    - converted: They completed the action (post-conversion follow-up)
    """
    try:
        customer_id = request.customer_id
        if customer_id and customer_id.strip().lower() in ("string", ""):
            customer_id = None

        to_override = request.to_override
        if to_override and to_override.strip().lower() in ("string", ""):
            to_override = None

        previous_email_subject = request.previous_email_subject
        if previous_email_subject and previous_email_subject.strip().lower() in ("string", ""):
            previous_email_subject = "Important Update Regarding Your Account"

        outcome = request.outcome
        if outcome and outcome.strip().lower() in ("string", ""):
            outcome = "opened_no_click"

        result = await generate_followup_email(
            customer_id=customer_id,
            previous_email_subject=previous_email_subject,
            outcome=outcome,
            send=request.send,
            to_override=to_override,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/email/rewrite", tags=["Email Generation"])
async def rewrite_email(request: RewriteEmailRequest):
    """
    Rewrites an existing email based on feedback.
    """
    try:
        customer_id = request.customer_id
        if customer_id and customer_id.strip().lower() in ("string", ""):
            customer_id = None

        original_email = request.original_email
        if original_email and original_email.strip().lower() in ("string", ""):
            original_email = "Subject: Hello\n\nHi there, just wanted to check in."

        feedback = request.feedback
        if feedback and feedback.strip().lower() in ("string", ""):
            feedback = "make it more urgent and compelling, add active verbs"

        result = await generate_rewrite(
            customer_id=customer_id,
            original_email=original_email,
            feedback=feedback,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/email/batch", tags=["Email Generation"])
async def run_batch_campaign(request: BatchCampaignRequest):
    """
    Generates emails for multiple customers in one call.
    
    [WARNING] Keep limit under 10 during development to avoid rate limits.
    Each email = 1 Gemini API call.
    """
    try:
        result = await generate_batch_campaign(
            campaign_type=request.campaign_type,
            segment=request.segment,
            limit=request.limit,
            send=request.send,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENTRY POINT — Run the server
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "backend.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,       # Auto-restart when you save code changes (dev only!)
        log_level="info",
    )

# Reloader trigger: Groq and Google SDKs upgraded


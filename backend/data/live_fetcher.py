"""
live_fetcher.py — PART 1: Live JSON Dataset Fetcher
=====================================================
This file is responsible for fetching REAL, LIVE data from public web APIs.

The main source: https://randomuser.me/api/
What it gives us: Realistic names, emails, locations, ages, genders, 
                  registered dates — all randomly generated but realistic.
                  No API key needed. Completely free.

Why RandomUser.me?
------------------
- It's a REAL external API (not us generating data locally)
- Returns different data every call (truly live/random)
- Provides structured JSON we can work with directly
- 5000+ unique results per request possible
- Trusted by developers worldwide for realistic test data

This file ONLY handles fetching. Enrichment (adding behavioral signals)
is handled separately in data_enricher.py — keeping responsibilities clean.
"""

import aiohttp          # Async HTTP client — doesn't block while waiting for API response
import asyncio          # Python's async/await engine
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from backend.config import (
    RANDOM_USER_API,
    FETCH_BATCH_SIZE,
    DATASET_SIZE
)

# Set up logging — every major action gets logged so you can trace what happened
logger = logging.getLogger(__name__)


# =============================================================================
# CORE FETCH FUNCTION
# =============================================================================

async def fetch_random_users(
    count: int = FETCH_BATCH_SIZE,
    session: Optional[aiohttp.ClientSession] = None
) -> List[Dict[str, Any]]:
    """
    Fetches `count` random user records from randomuser.me API.
    
    Parameters:
    -----------
    count : int
        How many users to fetch in this call. Max ~5000 per call.
    session : aiohttp.ClientSession, optional
        Reuse an existing HTTP session for efficiency. If None, creates a new one.
        
    Returns:
    --------
    List of raw user dicts from the API. Each dict looks like:
    {
        "gender": "female",
        "name": {"title": "Ms", "first": "Sarah", "last": "Johnson"},
        "location": {"city": "Austin", "country": "United States", ...},
        "email": "sarah.johnson@example.com",
        "dob": {"date": "1997-03-15T...", "age": 29},
        "registered": {"date": "2023-09-12T..."},
        ...
    }
    
    Raises:
    -------
    aiohttp.ClientError — if the network request fails
    ValueError — if the API returns unexpected data format
    """
    
    # Build query parameters for the RandomUser.me API
    params = {
        "results": count,       # Number of users to return
        "nat": "us,gb,ca,au",  # Nationalities: US, UK, Canada, Australia (realistic diversity)
        "inc": "gender,name,location,email,dob,registered,picture,phone",  # Only fetch fields we need
        "noinfo": "1",          # Exclude API metadata we don't need
    }
    
    # If a session was provided, use it. Otherwise create a temporary one.
    # Using an existing session is MUCH faster because it reuses the TCP connection.
    should_close_session = False
    if session is None:
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8)  # 8-second timeout — fail fast
        )
        should_close_session = True
    
    try:
        logger.info(f"Fetching {count} users from RandomUser.me API...")
        
        async with session.get(RANDOM_USER_API, params=params) as response:
            # Check HTTP status — 200 means success
            if response.status != 200:
                logger.error(f"RandomUser.me returned status {response.status}")
                raise aiohttp.ClientResponseError(
                    response.request_info,
                    response.history,
                    status=response.status,
                    message=f"API returned {response.status}"
                )
            
            # Parse the JSON response
            data = await response.json()
            
            # The API wraps results in a "results" key
            if "results" not in data:
                raise ValueError(f"Unexpected API response format: {data.keys()}")
            
            users = data["results"]
            logger.info(f"[OK] Fetched {len(users)} users successfully")
            return users
            
    except aiohttp.ClientConnectorError:
        # Network is down or API is unreachable
        logger.error("Cannot connect to RandomUser.me  check your internet connection")
        raise
        
    except asyncio.TimeoutError:
        # API took too long to respond
        logger.error("RandomUser.me request timed out after 8 seconds")
        raise
        
    finally:
        # Only close the session if WE created it (not if the caller passed one in)
        if should_close_session and not session.closed:
            await session.close()


# =============================================================================
# FULL DATASET BOOTSTRAP
# =============================================================================

async def fetch_full_dataset(target_size: int = DATASET_SIZE) -> List[Dict[str, Any]]:
    """
    Fetches a complete initial dataset of `target_size` users.
    
    Since RandomUser.me can return up to 5000 per request, we may need
    multiple calls if target_size > 5000. For 1000 records, this is one call.
    
    Parameters:
    -----------
    target_size : int
        Total number of user records to fetch (default: 1000 from config)
        
    Returns:
    --------
    List of raw user dicts from the API
    
    Why async?
    ----------
    If we ever need multiple batches (e.g., target_size=10000),
    we can fetch them CONCURRENTLY instead of sequentially.
    This turns 10 sequential 15-second calls into 1 concurrent 15-second call.
    """
    
    MAX_PER_REQUEST = 5000  # RandomUser.me hard limit per request
    
    if target_size <= MAX_PER_REQUEST:
        # Simple case: everything in one request
        return await fetch_random_users(count=target_size)
    
    # Complex case: need multiple requests, run them concurrently
    logger.info(f"Dataset size {target_size} > {MAX_PER_REQUEST}, fetching in parallel batches...")
    
    # Split into batches of MAX_PER_REQUEST
    batches_needed = (target_size + MAX_PER_REQUEST - 1) // MAX_PER_REQUEST
    batch_sizes = []
    remaining = target_size
    for _ in range(batches_needed):
        batch_size = min(remaining, MAX_PER_REQUEST)
        batch_sizes.append(batch_size)
        remaining -= batch_size
    
    # Create ONE shared session for all concurrent requests (efficient!)
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=15)
    ) as session:
        # Launch all batch requests at the same time
        tasks = [
            fetch_random_users(count=size, session=session)
            for size in batch_sizes
        ]
        
        # Wait for ALL of them to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Flatten results from [[user1, user2], [user3, user4]] to [user1, user2, user3, user4]
    all_users = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Batch {i+1} failed: {result}")
            # Don't crash — just skip the failed batch and continue
            continue
        all_users.extend(result)
    
    logger.info(f"[OK] Full dataset fetched: {len(all_users)} records")
    return all_users


# =============================================================================
# REFRESH BATCH — Used for live updates
# =============================================================================

async def fetch_refresh_batch(
    batch_size: int = 20
) -> List[Dict[str, Any]]:
    """
    Fetches a small batch of NEW users to replace stale records in the dataset.
    
    This is called repeatedly by stream_manager.py every few seconds to 
    simulate live data changes. The dataset gets a "rolling window" effect:
    old records are evicted and fresh records stream in continuously.
    
    Parameters:
    -----------
    batch_size : int
        How many records to refresh at once. Default 20 = 2% of 1000 records.
        
    Returns:
    --------
    Fresh list of raw user dicts
    """
    logger.debug(f"Fetching refresh batch of {batch_size} users...")
    
    # Add a small random jitter to batch size (18-22) to make it feel more organic/live
    import random
    actual_size = batch_size + random.randint(-2, 2)
    actual_size = max(1, actual_size)  # Never fetch 0
    
    return await fetch_random_users(count=actual_size)


# =============================================================================
# HEALTH CHECK — Verify the API is reachable before starting the server
# =============================================================================

async def check_api_health() -> Dict[str, Any]:
    """
    Pings RandomUser.me with a single-user request to verify connectivity.
    
    Call this at server startup. If it fails, alert the user immediately
    rather than letting the server start and fail mysteriously later.
    
    Returns:
    --------
    Dict with keys:
        "healthy": bool — True if API is reachable
        "latency_ms": float — How long the ping took in milliseconds
        "error": str or None — Error message if not healthy
    """
    start_time = datetime.now(timezone.utc)
    
    try:
        # Minimal request — just 1 user with bare minimum fields
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)  # Quick timeout for health
        ) as session:
            params = {"results": 1, "inc": "name", "noinfo": "1"}
            async with session.get(RANDOM_USER_API, params=params) as resp:
                healthy = resp.status == 200
        
        latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        return {
            "healthy": healthy,
            "latency_ms": round(latency_ms, 2),
            "error": None
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "latency_ms": None,
            "error": str(e)
        }

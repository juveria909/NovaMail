"""
stream_manager.py — PART 1: Live Dataset Stream Manager
=========================================================
This file manages the IN-MEMORY dataset of 1000 customer records.

It does three things:
1. BOOTSTRAP — Builds the initial 1000-record dataset at startup
2. REFRESH — Continuously replaces old records with fresh ones from the API
3. SERVE — Provides the rest of the app with read access to the live dataset

Think of it like a fishbowl:
- The fishbowl holds 1000 fish (records)
- Every 5 seconds, 20 old fish are removed and 20 new fish are added
- Anyone can look at the fishbowl at any time and see different fish

WHY IN-MEMORY?
--------------
For 1000 records, an in-memory list is the fastest option.
No database latency, no disk I/O — just pure Python dict access.
A 1000-record list of rich dicts is about 2-3 MB in memory, totally fine.

THREAD SAFETY:
--------------
Because FastAPI can handle multiple requests at the same time (concurrent),
we use asyncio.Lock() to make sure the dataset isn't modified mid-read.
Without this, a request could read a record while it's being replaced — 
resulting in corrupted data. The lock prevents that.
"""

import asyncio
import logging
import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from backend.config import DATASET_SIZE, DATASET_REFRESH_INTERVAL
from backend.data.live_fetcher import fetch_full_dataset, fetch_refresh_batch
from backend.data.data_enricher import enrich_batch

logger = logging.getLogger(__name__)


# =============================================================================
# THE LIVE DATASET — This is the single source of truth
# =============================================================================

class LiveDatasetManager:
    """
    Manages a continuously-updating pool of customer records.
    
    This is a SINGLETON — only one instance should exist for the whole app.
    It's instantiated once at the bottom of this file and imported everywhere.
    
    Usage:
        from backend.data.stream_manager import dataset_manager
        
        # Get all records
        all_records = await dataset_manager.get_all()
        
        # Get 10 records by segment
        inactive_users = await dataset_manager.get_by_segment("inactive", limit=10)
        
        # Get a single record by ID
        user = await dataset_manager.get_by_id("some-uuid-here")
    """
    
    def __init__(self, target_size: int = DATASET_SIZE):
        self.target_size = target_size
        
        # The actual list of customer dicts
        self._dataset: List[Dict[str, Any]] = []
        
        # Lock prevents simultaneous read/write corruption
        self._lock = asyncio.Lock()
        
        # Track whether the initial load is done
        self._initialized = False
        
        # Stats for monitoring
        self._stats = {
            "total_records": 0,
            "last_refresh": None,
            "refresh_count": 0,
            "bootstrap_time_seconds": None,
        }
        
        # Background task reference (so we can cancel it cleanly)
        self._refresh_task: Optional[asyncio.Task] = None
    
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    async def initialize(self):
        """
        Bootstraps the dataset with `target_size` records.
        
        This is called ONCE at server startup (in main.py lifespan).
        It blocks until the full initial dataset is loaded.
        
        Sequence:
        1. Fetch raw users from RandomUser.me
        2. Enrich them with behavioral data
        3. Store in memory
        4. Start the background refresh loop
        """
        if self._initialized:
            logger.warning("DatasetManager.initialize() called more than once  skipping")
            return
        
        logger.info(f"[START] Bootstrapping dataset with {self.target_size} records...")
        start_time = datetime.now(timezone.utc)
        
        try:
            # Step 1: Fetch raw data from the web
            raw_users = await fetch_full_dataset(target_size=self.target_size)
            
            # Step 2: Enrich with behavioral data
            # Note: enrich_batch is synchronous (CPU work, not I/O)
            # We run it in an executor so it doesn't block the async event loop
            loop = asyncio.get_event_loop()
            enriched_users = await loop.run_in_executor(
                None,  # Use default thread pool
                enrich_batch,
                raw_users
            )
            
            # Step 3: Store in memory under the lock
            async with self._lock:
                self._dataset = enriched_users
                self._stats["total_records"] = len(enriched_users)
                self._stats["bootstrap_time_seconds"] = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()
            
            self._initialized = True
            logger.info(
                f"[OK] Dataset ready: {len(enriched_users)} records loaded in "
                f"{self._stats['bootstrap_time_seconds']:.1f}s"
            )
            
            # Step 4: Start background refresh loop
            self._refresh_task = asyncio.create_task(self._refresh_loop())
            logger.info(f" Live refresh started (every {DATASET_REFRESH_INTERVAL}s)")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to initialize dataset: {e}")
            # Don't crash the server — operate with empty dataset
            # API endpoints will return empty results rather than 500 errors
            self._initialized = True  # Mark as "initialized" to prevent retry loops
            raise
    
    
    # =========================================================================
    # BACKGROUND REFRESH LOOP
    # =========================================================================
    
    async def _refresh_loop(self):
        """
        Runs forever in the background.
        
        Every DATASET_REFRESH_INTERVAL seconds:
        1. Fetch 20 fresh users from RandomUser.me
        2. Enrich them
        3. Replace 20 random old records with the fresh ones
        
        This is what creates the "live dataset" effect — 
        records are continuously cycling in and out.
        
        Why 20 records per refresh?
        - 20 records = 2% of 1000 total
        - At 5-second intervals = 240 records replaced per minute
        - Full dataset turnover in ~4 minutes
        - Feels organic and live without hammering the API
        """
        
        # Refresh ~4% of dataset each cycle (keeps it visibly live)
        refresh_batch_size = max(5, self.target_size // 25)
        
        while True:
            try:
                # Wait for the refresh interval
                await asyncio.sleep(DATASET_REFRESH_INTERVAL)
                
                # Fetch fresh users
                raw_new_users = await fetch_refresh_batch(batch_size=refresh_batch_size)
                
                if not raw_new_users:
                    logger.warning("Refresh batch returned empty  skipping this cycle")
                    continue
                
                # Enrich them
                loop = asyncio.get_event_loop()
                new_enriched = await loop.run_in_executor(
                    None, enrich_batch, raw_new_users
                )
                
                if not new_enriched:
                    continue
                
                # Replace random old records with fresh ones
                async with self._lock:
                    current_size = len(self._dataset)
                    
                    if current_size == 0:
                        self._dataset = new_enriched
                    else:
                        # Pick random indices to replace
                        num_to_replace = min(len(new_enriched), current_size)
                        indices_to_replace = random.sample(
                            range(current_size), num_to_replace
                        )
                        
                        for i, idx in enumerate(indices_to_replace):
                            if i < len(new_enriched):
                                self._dataset[idx] = new_enriched[i]
                    
                    # Sort dataset by enriched_at descending so newly enriched records appear at the top
                    self._dataset.sort(key=lambda x: x.get("enriched_at", ""), reverse=True)
                    
                    self._stats["last_refresh"] = datetime.now(timezone.utc).isoformat()
                    self._stats["refresh_count"] += 1
                
                logger.debug(
                    f"🔄 Refresh #{self._stats['refresh_count']}: "
                    f"replaced {len(new_enriched)} records"
                )
                
            except asyncio.CancelledError:
                # Server is shutting down — exit cleanly
                logger.info("Refresh loop cancelled  shutting down")
                break
                
            except Exception as e:
                # Log but DON'T crash the loop — try again next interval
                logger.error(f"Refresh cycle failed: {e}  retrying in {DATASET_REFRESH_INTERVAL}s")
    
    
    # =========================================================================
    # READ METHODS — Called by API routes and the AI generator
    # =========================================================================
    
    async def get_all(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Returns all records (or a limited slice).
        
        Parameters:
        -----------
        limit : int, optional
            If provided, returns only this many records (most recently enriched first)
        """
        async with self._lock:
            data = list(self._dataset)  # Copy to avoid mutation issues
        
        if limit is not None:
            return data[:limit]
        return data
    
    
    async def get_by_segment(
        self, 
        segment: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns records filtered by segment.
        
        Parameters:
        -----------
        segment : str
            One of: "new_signup", "new", "active", "inactive", "high_value", "at_risk"
        limit : int, optional
            Maximum records to return
            
        Example:
        --------
        inactive_users = await manager.get_by_segment("inactive", limit=50)
        """
        async with self._lock:
            filtered = [r for r in self._dataset if r.get("segment") == segment]
        
        if limit is not None:
            return filtered[:limit]
        return filtered
    
    
    async def get_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns a single record by its UUID.
        Returns None if not found.
        """
        async with self._lock:
            for record in self._dataset:
                if record.get("id") == record_id:
                    return dict(record)  # Return a copy
        return None
    
    
    async def get_by_tag(
        self, 
        tag: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns records that have a specific tag.
        
        Example: tag="high-value" returns all VIP customers.
        """
        async with self._lock:
            filtered = [
                r for r in self._dataset 
                if tag in r.get("tags", [])
            ]
        
        if limit is not None:
            return filtered[:limit]
        return filtered
    
    
    async def get_random(self, count: int = 1) -> List[Dict[str, Any]]:
        """
        Returns `count` random records from the dataset.
        Useful for testing AI generation without specifying a segment.
        """
        async with self._lock:
            if len(self._dataset) == 0:
                return []
            
            sample_size = min(count, len(self._dataset))
            return random.sample(self._dataset, sample_size)
    
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Returns current dataset statistics.
        Called by the /api/dataset/stats endpoint.
        """
        async with self._lock:
            segment_counts = {}
            for record in self._dataset:
                seg = record.get("segment", "unknown")
                segment_counts[seg] = segment_counts.get(seg, 0) + 1
        
        return {
            **self._stats,
            "segment_distribution": segment_counts,
            "is_initialized": self._initialized,
        }
    
    
    async def search(
        self, 
        query: str, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Simple text search across name, email, and interests.
        
        Parameters:
        -----------
        query : str
            Search string (case-insensitive)
        limit : int
            Maximum results to return
        """
        query_lower = query.lower()
        
        async with self._lock:
            results = []
            for record in self._dataset:
                # Check name and email
                if (query_lower in record.get("name", "").lower() or
                    query_lower in record.get("email", "").lower()):
                    results.append(record)
                    continue
                
                # Check interests
                interests = record.get("interests", [])
                if any(query_lower in interest.lower() for interest in interests):
                    results.append(record)
                
                if len(results) >= limit:
                    break
        
        return results
    
    
    # =========================================================================
    # LIFECYCLE MANAGEMENT
    # =========================================================================
    
    async def shutdown(self):
        """
        Gracefully stops the refresh loop.
        Called at server shutdown (main.py lifespan cleanup).
        """
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        logger.info(" Dataset manager shut down cleanly")


# =============================================================================
# SINGLETON INSTANCE — Import this everywhere else in the app
# =============================================================================

# This is the one and only dataset manager instance.
# Import it like: from backend.data.stream_manager import dataset_manager
dataset_manager = LiveDatasetManager(target_size=DATASET_SIZE)

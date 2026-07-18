"""
backend/ml/recommender.py
==========================
Collaborative Filtering — Product Recommender

What it does:
- Builds a customer × interest/product matrix from the live pool.
- Uses Truncated SVD (Matrix Factorization) to find latent similarity patterns.
- Given a customer, finds the most similar other customers, and recommends
  a product they purchased that the target customer hasn't seen yet.
- Falls back to a rule-based recommender if not enough data is available.

Why Collaborative Filtering?
- "People who share your interests also bought X" — same logic used by
  Amazon, Netflix, and Spotify recommendation engines.
"""

import logging
import threading
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ─── Catalogue of products the platform sells ────────────────────────────────
PRODUCT_CATALOGUE = [
    "Starter Workspace Plan",
    "Professional Email Suite",
    "Premium Workspace Pro",
    "Enterprise Campaign Manager",
    "AI Personalization Add-on",
    "Analytics & Reporting Dashboard",
    "Smart Follow-up Automation",
    "Team Collaboration Bundle",
]

# Interest → most relevant product mapping (used in rule-based fallback)
INTEREST_PRODUCT_MAP = {
    "coding":         "AI Personalization Add-on",
    "open-source":    "Starter Workspace Plan",
    "web design":     "Professional Email Suite",
    "investing":      "Analytics & Reporting Dashboard",
    "budgeting":      "Analytics & Reporting Dashboard",
    "crypto":         "Analytics & Reporting Dashboard",
    "fitness":        "Smart Follow-up Automation",
    "nutrition":      "Smart Follow-up Automation",
    "running":        "Smart Follow-up Automation",
    "music":          "Enterprise Campaign Manager",
    "travel":         "Enterprise Campaign Manager",
    "photography":    "Premium Workspace Pro",
    "cooking":        "Team Collaboration Bundle",
    "baking":         "Team Collaboration Bundle",
    "fine dining":    "Premium Workspace Pro",
    "gardening":      "Starter Workspace Plan",
    "sustainability": "Starter Workspace Plan",
    "books":          "Professional Email Suite",
    "podcasts":       "Professional Email Suite",
    "culture":        "Enterprise Campaign Manager",
}

# ─── Module-level cache ───────────────────────────────────────────────────────
_customer_matrix: Optional[np.ndarray] = None
_customer_ids:    List[str] = []
_product_labels:  List[str] = []
_svd_components:  Optional[np.ndarray] = None
_rec_lock = threading.Lock()


def _build_matrix(customers: List[Dict[str, Any]]) -> None:
    """
    Build a customer × product binary matrix and factorise with TruncatedSVD.
    Each row = one customer. Each column = one product in PRODUCT_CATALOGUE.
    Value = 1 if the customer purchased that product, 0 otherwise.
    """
    global _customer_matrix, _customer_ids, _product_labels, _svd_components

    if len(customers) < 5:
        return

    try:
        from sklearn.decomposition import TruncatedSVD

        prod_index = {p: i for i, p in enumerate(PRODUCT_CATALOGUE)}
        n_customers = len(customers)
        n_products  = len(PRODUCT_CATALOGUE)

        matrix = np.zeros((n_customers, n_products), dtype=np.float32)
        ids    = []

        for row, cust in enumerate(customers):
            ids.append(cust.get("id", str(row)))
            for purchase in cust.get("purchase_history", []):
                item = purchase.get("item", "")
                if item in prod_index:
                    matrix[row, prod_index[item]] = 1.0

        # TruncatedSVD: reduces the matrix to latent factors
        n_components = min(10, n_customers - 1, n_products - 1)
        if n_components < 1:
            return

        svd = TruncatedSVD(n_components=n_components, random_state=42)
        latent = svd.fit_transform(matrix)  # shape: (n_customers, n_components)

        with _rec_lock:
            _customer_matrix = latent
            _customer_ids    = ids
            _product_labels  = PRODUCT_CATALOGUE[:]
            _svd_components  = svd.components_  # shape: (n_components, n_products)

        logger.info(
            f"[Recommender] SVD matrix built: {n_customers} customers × "
            f"{n_products} products, {n_components} latent factors."
        )

    except Exception as exc:
        logger.error(f"[Recommender] Matrix build failed: {exc}")


def recommend_product(customer: Dict[str, Any], all_customers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Return the best product recommendation for a given customer.

    Strategy:
    1. Try Collaborative Filtering (SVD cosine similarity).
    2. Fall back to interest-based rule mapping if CF is unavailable.
    3. Fall back to the top-value product if nothing matches.

    Returns
    -------
    dict with keys:
        recommended_product : str
        recommendation_type : str ("collaborative_filtering" | "interest_based" | "default")
        reason              : str  — human-readable explanation for the email prompt
    """
    global _customer_matrix, _customer_ids

    customer_id = customer.get("id", "")

    # ── Try Collaborative Filtering ──────────────────────────────────────────
    with _rec_lock:
        matrix  = _customer_matrix
        id_list = _customer_ids[:]

    if matrix is not None and customer_id in id_list:
        try:
            target_idx = id_list.index(customer_id)
            target_vec = matrix[target_idx]  # latent vector

            # Cosine similarity with all other customers
            norms = np.linalg.norm(matrix, axis=1) + 1e-9
            sims  = (matrix @ target_vec) / (norms * (np.linalg.norm(target_vec) + 1e-9))
            sims[target_idx] = -1  # exclude self

            # Get top-5 most similar customers
            top_indices = np.argsort(sims)[::-1][:5]

            # Collect products they purchased that this customer hasn't bought
            cust_purchases = {
                p.get("item") for p in customer.get("purchase_history", [])
            }
            candidate_scores: Dict[str, float] = {}

            for idx in top_indices:
                sim_score = float(sims[idx])
                if sim_score <= 0:
                    continue
                sim_cust = next(
                    (c for c in all_customers if c.get("id") == id_list[idx]), None
                )
                if not sim_cust:
                    continue
                for purchase in sim_cust.get("purchase_history", []):
                    prod = purchase.get("item", "")
                    if prod and prod not in cust_purchases and prod in PRODUCT_CATALOGUE:
                        candidate_scores[prod] = candidate_scores.get(prod, 0) + sim_score

            if candidate_scores:
                best = max(candidate_scores, key=candidate_scores.get)
                return {
                    "recommended_product": best,
                    "recommendation_type": "collaborative_filtering",
                    "reason": (
                        f"Customers with similar interests and purchase patterns to "
                        f"{customer.get('first_name', 'this customer')} frequently upgrade to '{best}'."
                    ),
                }
        except Exception as exc:
            logger.warning(f"[Recommender] CF lookup failed ({exc}), using fallback.")

    # ── Interest-Based Fallback ───────────────────────────────────────────────
    interests = customer.get("interests", [])
    for interest in interests:
        if interest.lower() in INTEREST_PRODUCT_MAP:
            product = INTEREST_PRODUCT_MAP[interest.lower()]
            return {
                "recommended_product": product,
                "recommendation_type": "interest_based",
                "reason": (
                    f"Based on {customer.get('first_name', 'the customer')}'s interest in "
                    f"'{interest}', '{product}' is the most relevant upgrade."
                ),
            }

    # ── Default ───────────────────────────────────────────────────────────────
    return {
        "recommended_product": "Premium Workspace Pro",
        "recommendation_type": "default",
        "reason": "Premium Workspace Pro is our most popular plan for growing teams.",
    }


def train_recommender(customers: List[Dict[str, Any]]) -> None:
    """Public entry point: (re)build the SVD recommendation matrix."""
    _build_matrix(customers)

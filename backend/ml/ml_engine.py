"""
backend/ml/ml_engine.py
========================
Unified ML Predictions Entry Point

This is the ONE function the rest of the codebase calls.
It orchestrates both models and returns a single predictions dict
that gets injected directly into the Gemini AI prompt.

Usage (from email_generator.py):
    from backend.ml.ml_engine import run_ml_predictions, train_ml_models
    predictions = run_ml_predictions(customer, all_customers)
"""

import logging
from typing import Any, Dict, List, Optional

from backend.ml.churn_predictor import predict_churn, train_churn_model
from backend.ml.recommender import recommend_product, train_recommender

logger = logging.getLogger(__name__)

# ─── Track whether models have been trained in this session ──────────────────
_models_trained = False


def train_ml_models(customers: List[Dict[str, Any]]) -> None:
    """
    Train both ML models on the current live customer pool.
    Call this once after the dataset is loaded (e.g., on app startup
    or when the sidebar fetches the full customer list).

    Parameters
    ----------
    customers : list of enriched customer dicts from LiveDatasetManager
    """
    global _models_trained

    if len(customers) < 5:
        logger.warning("[MLEngine] Fewer than 5 customers — skipping model training.")
        return

    logger.info(f"[MLEngine] Training ML models on {len(customers)} customers…")
    train_churn_model(customers)
    train_recommender(customers)
    _models_trained = True
    logger.info("[MLEngine] ✅ Both models trained successfully.")


def run_ml_predictions(
    customer: Dict[str, Any],
    all_customers: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Run both ML models for a single customer and return a combined
    predictions dict ready for injection into a Gemini prompt.

    Parameters
    ----------
    customer      : The target customer dict (enriched profile)
    all_customers : Optional list of all customers (needed for CF recommender).
                    If None, the recommender uses its last-trained matrix.

    Returns
    -------
    dict:
        churn_score          : float 0.0–1.0
        churn_label          : str ("High Risk" | "Moderate Risk" | "Healthy")
        churn_pct            : str e.g. "72%"
        recommended_product  : str
        recommendation_type  : str
        recommendation_reason: str
        models_trained       : bool
    """
    # Churn prediction
    churn = predict_churn(customer)

    # Product recommendation
    rec = recommend_product(customer, all_customers or [])

    result = {
        "churn_score":           churn["churn_score"],
        "churn_label":           churn["churn_label"],
        "churn_pct":             churn["churn_pct"],
        "recommended_product":   rec["recommended_product"],
        "recommendation_type":   rec["recommendation_type"],
        "recommendation_reason": rec["reason"],
        "models_trained":        _models_trained,
    }

    logger.info(
        f"[MLEngine] {customer.get('name','?')} → "
        f"Churn: {result['churn_label']} ({result['churn_pct']}) | "
        f"Rec: {result['recommended_product']} [{result['recommendation_type']}]"
    )
    return result

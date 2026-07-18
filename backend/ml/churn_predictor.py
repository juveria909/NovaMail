"""
backend/ml/churn_predictor.py
==============================
XGBoost Churn Risk Predictor

What it does:
- Trains a lightweight XGBoost binary classifier on the live in-memory
  customer pool using each customer's behavioral signals.
- Predicts a churn_score (0.0 → 1.0) for any given customer.

Features used (all available on every enriched customer record):
  - email_open_rate       : How often they open emails
  - click_rate            : How often they click email links
  - account_age_days      : How long they've been a customer
  - emails_received       : Total emails received so far
  - days_since_last_active: Days since last engagement (derived)

Label generation (self-supervised):
  Since we have no real churn ground truth, we derive synthetic labels:
  - HIGH risk (1): open_rate < 0.25 AND click_rate < 0.08
  - LOW risk  (0): otherwise
  This mirrors real-world churn logic used in marketing analytics.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ─── Module-level model cache (train once, reuse) ───────────────────────────
_model = None
_model_lock = threading.Lock()
_feature_names = [
    "email_open_rate",
    "click_rate",
    "account_age_days",
    "emails_received",
    "days_since_last_active",
]


def _extract_features(customer: Dict[str, Any]) -> np.ndarray:
    """Extract a feature vector from one enriched customer dict."""
    behavior = customer.get("email_behavior", {})
    open_rate       = float(behavior.get("open_rate",        0.35))
    click_rate      = float(behavior.get("click_rate",       0.10))
    acct_age        = float(customer.get("account_age_days", 90))
    emails_received = float(behavior.get("emails_received",  10))

    # Derive days_since_last_active from ISO timestamp
    last_active_raw = customer.get("last_active", "")
    try:
        last_dt = datetime.fromisoformat(last_active_raw.replace("Z", "+00:00"))
        days_inactive = (datetime.now(timezone.utc) - last_dt).days
    except Exception:
        days_inactive = 30  # sensible default

    return np.array(
        [open_rate, click_rate, acct_age, emails_received, days_inactive],
        dtype=np.float32,
    )


def _derive_label(customer: Dict[str, Any]) -> int:
    """Synthetic churn label: 1 = at risk, 0 = healthy."""
    behavior = customer.get("email_behavior", {})
    open_rate  = float(behavior.get("open_rate",  0.35))
    click_rate = float(behavior.get("click_rate", 0.10))
    segment    = customer.get("segment", "active")

    if segment in ("inactive", "at_risk"):
        return 1
    if open_rate < 0.25 and click_rate < 0.08:
        return 1
    return 0


def train_churn_model(customers: List[Dict[str, Any]]) -> None:
    """
    Train (or retrain) the XGBoost churn classifier on the current customer pool.
    Uses XGBoost's native DMatrix API (no sklearn dependency).
    Thread-safe — uses a lock so parallel requests don't race.
    """
    global _model

    if len(customers) < 5:
        logger.warning("[ChurnPredictor] Not enough customers to train (need ≥ 5). Skipping.")
        return

    try:
        import xgboost as xgb

        X = np.array([_extract_features(c) for c in customers], dtype=np.float32)
        y = np.array([_derive_label(c)     for c in customers], dtype=np.float32)

        # XGBoost native DMatrix
        dtrain = xgb.DMatrix(X, label=y, feature_names=_feature_names)

        # Class balance weight
        n_neg = max(1, int(np.sum(y == 0)))
        n_pos = max(1, int(np.sum(y == 1)))
        scale = n_neg / n_pos

        params = {
            "objective":        "binary:logistic",
            "eval_metric":      "logloss",
            "max_depth":        4,
            "eta":              0.15,
            "scale_pos_weight": scale,
            "seed":             42,
            "verbosity":        0,
        }

        new_model = xgb.train(params, dtrain, num_boost_round=60)

        with _model_lock:
            _model = new_model

        logger.info(
            f"[ChurnPredictor] Model trained on {len(customers)} customers "
            f"(pos={n_pos}, neg={n_neg}, scale={scale:.2f})"
        )

    except Exception as exc:
        logger.error(f"[ChurnPredictor] Training failed: {exc}")


def predict_churn(customer: Dict[str, Any]) -> Dict[str, Any]:
    """
    Predict churn risk for a single customer.

    Returns
    -------
    dict with keys:
        churn_score  : float 0.0–1.0
        churn_label  : str  ("High Risk" | "Moderate Risk" | "Healthy")
        churn_pct    : str  e.g. "72%"
    """
    global _model

    # Fallback: if model not yet trained, use heuristic
    if _model is None:
        score = _heuristic_score(customer)
    else:
        try:
            import xgboost as xgb
            features = _extract_features(customer).reshape(1, -1)
            dtest    = xgb.DMatrix(features, feature_names=_feature_names)
            with _model_lock:
                score = float(_model.predict(dtest)[0])
        except Exception as exc:
            logger.warning(f"[ChurnPredictor] Predict failed ({exc}), using heuristic.")
            score = _heuristic_score(customer)


    # Classify into bands
    if score >= 0.65:
        label = "High Risk"
    elif score >= 0.35:
        label = "Moderate Risk"
    else:
        label = "Healthy"

    return {
        "churn_score": round(score, 3),
        "churn_label": label,
        "churn_pct":   f"{int(score * 100)}%",
    }


def _heuristic_score(customer: Dict[str, Any]) -> float:
    """Simple rule-based fallback when XGBoost model is not available."""
    behavior = customer.get("email_behavior", {})
    open_rate  = float(behavior.get("open_rate",  0.35))
    click_rate = float(behavior.get("click_rate", 0.10))
    segment    = customer.get("segment", "active")

    score = 0.2  # baseline
    if segment in ("inactive", "at_risk"):
        score += 0.5
    if open_rate < 0.20:
        score += 0.2
    elif open_rate < 0.35:
        score += 0.1
    if click_rate < 0.05:
        score += 0.15

    return min(score, 0.99)

"""
backend/texture_thresholds.py

PALF-Vision AI: Candidate Texture Threshold Evaluation Module
============================================================
Evaluates image-derived PALF bundle texture metrics against experimentally
derived candidate thresholds (54-image inspector-labeled study aligned with PNS/BAFS 318:2021).

Important Research Context & Scope Boundaries:
- Classifies bundle texture into three categories:
    * Soft         -> Associated Cleaning Grade: Excellent (PNS reference: PID-1)
    * Medium-soft  -> Associated Cleaning Grade: Good      (PNS reference: PID-2)
    * Medium-coarse-> Associated Cleaning Grade: Fair      (PNS reference: PID-3 / PID-4)
- PID-3 and PID-4 are both Fair and share the Medium-coarse texture description.
- Image-derived texture metrics quantify spatial grayscale distributions and directional
  coherence; they do NOT measure tactile hand or microscopic strand roughness.
- Candidate thresholds are experimental and do NOT alter or overwrite the deep learning
  classification.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("palf_texture_thresholds")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "palf_texture_threshold_rules.json")

CLASS_METADATA = {
    0: {
        "predicted_texture": "soft",
        "display_name": "Soft",
        "associated_grade": "Excellent",
        "pns_code": "PID-1",
    },
    1: {
        "predicted_texture": "medium-soft",
        "display_name": "Medium-soft",
        "associated_grade": "Good",
        "pns_code": "PID-2",
    },
    2: {
        "predicted_texture": "medium-coarse",
        "display_name": "Medium-coarse",
        "associated_grade": "Fair",
        "pns_code": "PID-3 / PID-4",
    },
}

_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def load_texture_rules_config() -> Dict[str, Any]:
    """Loads the threshold configuration file with caching."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                _CONFIG_CACHE = json.load(f)
                return _CONFIG_CACHE
        except Exception as e:
            logger.error(f"Failed to load texture threshold config from {CONFIG_PATH}: {e}")

    # Fallback default configuration if JSON file is missing
    _CONFIG_CACHE = {
        "version": "1.0",
        "primary_rule": "orientation_spread_deg_regional_mean",
        "fallback_rule": "orientation_spread_deg",
    }
    return _CONFIG_CACHE


def evaluate_texture_thresholds(
    features: Dict[str, Any],
    mask_coverage_pct: float = 0.0,
    valid_regions: int = 0,
    laplacian_variance: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluates extracted bundle texture features against the candidate threshold rules.

    Parameters:
    - features: Dictionary of calculated visual and texture features.
    - mask_coverage_pct: Percentage of ROI occupied by valid fiber mask.
    - valid_regions: Number of 3x3 regions passing quality screening.
    - laplacian_variance: Masked focus sharpness measurement.

    Returns:
    - Structured dictionary matching the API specification.
    """
    # 1. Quality & Mask Validations
    if mask_coverage_pct <= 0.0:
        return {
            "status": "insufficient_fiber_mask",
            "assessment_type": "experimental_threshold_based",
            "predicted_texture": None,
            "display_name": "Unavailable",
            "associated_grade": None,
            "pns_code": None,
            "threshold_match": False,
            "features": features,
            "threshold_details": {
                "rule_id": None,
                "features_used": [],
                "decision_path": ["Fiber mask is empty; texture analysis unavailable."],
            },
            "warnings": ["Empty fiber mask. Fiber bundle must be present in the designated ROI."],
        }

    if mask_coverage_pct < 5.0:
        return {
            "status": "insufficient_fiber_mask",
            "assessment_type": "experimental_threshold_based",
            "predicted_texture": None,
            "display_name": "Low Coverage",
            "associated_grade": None,
            "pns_code": None,
            "threshold_match": False,
            "features": features,
            "threshold_details": {
                "rule_id": None,
                "features_used": [],
                "decision_path": [f"Fiber coverage ({mask_coverage_pct:.1f}%) is below minimum 5.0% threshold."],
            },
            "warnings": ["Low fiber coverage; bundle texture cannot be reliably evaluated."],
        }

    # Focus check (if focus metric is available and severely degraded)
    if laplacian_variance is not None and laplacian_variance < 10.0:
        return {
            "status": "insufficient_image_quality",
            "assessment_type": "experimental_threshold_based",
            "predicted_texture": None,
            "display_name": "Blurry",
            "associated_grade": None,
            "pns_code": None,
            "threshold_match": False,
            "features": features,
            "threshold_details": {
                "rule_id": None,
                "features_used": ["laplacian_variance_focus"],
                "decision_path": [f"Laplacian focus variance ({laplacian_variance:.1f}) is below sharpness threshold."],
            },
            "warnings": ["Image focus is insufficient for reliable bundle texture characterization."],
        }

    # 2. Select Candidate Rule based on feature availability
    # Priority 1: orientation_spread_deg_regional_mean (Macro F1 = 0.7356, Balanced Acc = 0.75)
    # Requires valid_regions >= 3 so regional mean is statistically meaningful.
    reg_spread = features.get("orientation_spread_deg_regional_mean")
    if reg_spread is not None and valid_regions >= 3:
        rule_id = "orientation_spread_deg_regional_mean"
        val = float(reg_spread)
        if val <= 23.455670:
            pred_class = 0
            path = [
                f"orientation_spread_deg_regional_mean ({val:.2f}°) <= 23.46°",
                "Node classification -> Class 0 (Soft / PID-1 / Excellent)",
            ]
        elif val <= 27.049147:
            pred_class = 2
            path = [
                f"orientation_spread_deg_regional_mean ({val:.2f}°) > 23.46°",
                f"orientation_spread_deg_regional_mean ({val:.2f}°) <= 27.05°",
                "Node classification -> Class 2 (Medium-coarse / PID-3 & PID-4 / Fair)",
            ]
        else:
            pred_class = 1
            path = [
                f"orientation_spread_deg_regional_mean ({val:.2f}°) > 27.05°",
                "Node classification -> Class 1 (Medium-soft / PID-2 / Good)",
            ]

        meta = CLASS_METADATA[pred_class]
        return {
            "status": "available",
            "assessment_type": "experimental_threshold_based",
            "predicted_texture": meta["predicted_texture"],
            "display_name": meta["display_name"],
            "associated_grade": meta["associated_grade"],
            "pns_code": meta["pns_code"],
            "threshold_match": True,
            "features": features,
            "threshold_details": {
                "rule_id": rule_id,
                "features_used": [rule_id],
                "decision_path": path,
                "validation_f1": 0.7356,
                "validation_balanced_acc": 0.75,
            },
            "disclaimer": "Experimental candidate reference comparison · Does not determine or alter deep learning model classification",
            "warnings": [],
        }

    # Priority 2: Whole Bundle orientation_spread_deg (Macro F1 = 0.6816, Balanced Acc = 0.7111)
    bundle_spread = features.get("orientation_spread_deg")
    if bundle_spread is not None:
        rule_id = "orientation_spread_deg"
        val = float(bundle_spread)
        if val <= 22.552517:
            pred_class = 0
            path = [
                f"orientation_spread_deg ({val:.2f}°) <= 22.55°",
                "Node classification -> Class 0 (Soft / PID-1 / Excellent)",
            ]
        elif val <= 27.794097:
            pred_class = 2
            path = [
                f"orientation_spread_deg ({val:.2f}°) > 22.55°",
                f"orientation_spread_deg ({val:.2f}°) <= 27.79°",
                "Node classification -> Class 2 (Medium-coarse / PID-3 & PID-4 / Fair)",
            ]
        else:
            pred_class = 1
            path = [
                f"orientation_spread_deg ({val:.2f}°) > 27.79°",
                "Node classification -> Class 1 (Medium-soft / PID-2 / Good)",
            ]

        meta = CLASS_METADATA[pred_class]
        return {
            "status": "available",
            "assessment_type": "experimental_threshold_based",
            "predicted_texture": meta["predicted_texture"],
            "display_name": meta["display_name"],
            "associated_grade": meta["associated_grade"],
            "pns_code": meta["pns_code"],
            "threshold_match": True,
            "features": features,
            "threshold_details": {
                "rule_id": rule_id,
                "features_used": [rule_id],
                "decision_path": path,
                "validation_f1": 0.6816,
                "validation_balanced_acc": 0.7111,
            },
            "disclaimer": "Experimental candidate reference comparison · Does not determine or alter deep learning model classification",
            "warnings": ["Using whole-bundle orientation fallback because regional grid had insufficient valid cells."],
        }

    # Priority 3: Gabor Response Anisotropy (Macro F1 = 0.7015, Balanced Acc = 0.7111)
    gabor_aniso = features.get("gabor_response_anisotropy")
    if gabor_aniso is not None:
        rule_id = "gabor_response_anisotropy"
        val = float(gabor_aniso)
        if val <= 0.454447:
            pred_class = 1
            path = [
                f"gabor_response_anisotropy ({val:.4f}) <= 0.4544",
                "Node classification -> Class 1 (Medium-soft / PID-2 / Good)",
            ]
        elif val <= 0.545935:
            pred_class = 2
            path = [
                f"gabor_response_anisotropy ({val:.4f}) > 0.4544",
                f"gabor_response_anisotropy ({val:.4f}) <= 0.5459",
                "Node classification -> Class 2 (Medium-coarse / PID-3 & PID-4 / Fair)",
            ]
        else:
            pred_class = 0
            path = [
                f"gabor_response_anisotropy ({val:.4f}) > 0.5459",
                "Node classification -> Class 0 (Soft / PID-1 / Excellent)",
            ]

        meta = CLASS_METADATA[pred_class]
        return {
            "status": "available",
            "assessment_type": "experimental_threshold_based",
            "predicted_texture": meta["predicted_texture"],
            "display_name": meta["display_name"],
            "associated_grade": meta["associated_grade"],
            "pns_code": meta["pns_code"],
            "threshold_match": True,
            "features": features,
            "threshold_details": {
                "rule_id": rule_id,
                "features_used": [rule_id],
                "decision_path": path,
                "validation_f1": 0.7015,
                "validation_balanced_acc": 0.7111,
            },
            "disclaimer": "Experimental candidate reference comparison · Does not determine or alter deep learning model classification",
            "warnings": [],
        }

    # If all candidate features are missing / None
    return {
        "status": "threshold_not_available",
        "assessment_type": "experimental_threshold_based",
        "predicted_texture": None,
        "display_name": "Unavailable",
        "associated_grade": None,
        "pns_code": None,
        "threshold_match": False,
        "features": features,
        "threshold_details": {
            "rule_id": None,
            "features_used": [],
            "decision_path": ["Candidate features (orientation spread, Gabor anisotropy) were not calculable."],
        },
        "warnings": ["Texture threshold evaluation could not find calculable candidate features."],
    }

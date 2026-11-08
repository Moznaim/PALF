
"""
PALF-Vision AI: Experimental Texture Threshold Evaluation

Thresholds and class definitions are loaded from:
backend/config/palf_texture_threshold_rules.json

Class mapping:
    0 = Soft / Excellent / PID-1
    1 = Medium-soft / Good / PID-2
    2 = Medium-coarse / Fair / PID-3 / PID-4

This module evaluates image-derived bundle texture descriptors.
It does not measure tactile softness and does not modify CNN predictions.
"""

import os
import json
import math
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("palf_texture_thresholds")

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config",
    "palf_texture_threshold_rules.json",
)

_CONFIG_CACHE: Optional[Dict[str, Any]] = None


# ============================================================
# 1. CONFIGURATION LOADING
# ============================================================

def load_texture_rules_config(
    force_reload: bool = False
) -> Dict[str, Any]:
    """
    Load the JSON threshold configuration.

    The JSON file is the single source of truth.
    No hardcoded threshold fallback is used.
    """

    global _CONFIG_CACHE

    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            config = json.load(file)

        if not isinstance(config, dict):
            raise ValueError("JSON configuration root must be an object.")

        _CONFIG_CACHE = config
        logger.info(
            "Texture threshold configuration loaded: %s",
            CONFIG_PATH,
        )

        return _CONFIG_CACHE

    except Exception:
        logger.exception(
            "Failed to load texture threshold configuration: %s",
            CONFIG_PATH,
        )

        _CONFIG_CACHE = {}
        return _CONFIG_CACHE


# ============================================================
# 2. BASIC VALIDATION HELPERS
# ============================================================

def _finite_number(value: Any) -> Optional[float]:
    """
    Safely convert a value to a finite float.
    Rejects None, booleans, NaN, and infinity.
    """

    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _unavailable_result(
    status: str,
    features: Dict[str, Any],
    message: str,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return a consistent unavailable texture assessment."""

    return {
        "status": status,
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
            "decision_path": [message],
        },
        "disclaimer": (
            "Experimental candidate reference comparison. "
            "Does not determine or alter deep learning model classification."
        ),
        "warnings": warnings or [message],
    }


def _validate_configuration(
    config: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Validate the three required top-level configuration sections.
    """

    class_definitions = config.get("class_definitions")
    feature_rules = config.get("feature_rules")
    rule_priority = config.get("rule_priority")

    if not isinstance(class_definitions, dict) or not class_definitions:
        raise ValueError(
            "Missing or invalid 'class_definitions' in JSON configuration."
        )

    if not isinstance(feature_rules, dict) or not feature_rules:
        raise ValueError(
            "Missing or invalid 'feature_rules' in JSON configuration."
        )

    if not isinstance(rule_priority, list) or not rule_priority:
        raise ValueError(
            "Missing or invalid 'rule_priority' in JSON configuration."
        )

    return class_definitions, feature_rules, rule_priority


# ============================================================
# 3. DECISION TREE VALIDATION
# ============================================================

def _validate_decision_tree(
    decision_tree: Dict[str, Any],
    class_definitions: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Validate a configured decision tree.

    Every branch uses:
        feature_value <= max_inclusive

    If no branch matches, default_class is assigned.
    """

    branches = decision_tree.get("branches")
    default_class = decision_tree.get("default_class")

    if not isinstance(branches, list) or not branches:
        raise ValueError(
            "Decision tree must contain a non-empty branches list."
        )

    normalized_branches = []
    previous_boundary = -math.inf

    for index, branch in enumerate(branches):

        if not isinstance(branch, dict):
            raise ValueError(
                f"Decision tree branch {index} must be an object."
            )

        boundary = _finite_number(
            branch.get("max_inclusive")
        )

        if boundary is None:
            raise ValueError(
                f"Decision tree branch {index} has an invalid boundary."
            )

        if boundary <= previous_boundary:
            raise ValueError(
                "Decision tree boundaries must be in ascending order."
            )

        try:
            class_id = int(branch.get("class"))
        except (TypeError, ValueError, OverflowError):
            raise ValueError(
                f"Decision tree branch {index} has an invalid class ID."
            )

        if str(class_id) not in class_definitions:
            raise ValueError(
                f"Class {class_id} is missing from class_definitions."
            )

        normalized_branches.append({
            "max_inclusive": boundary,
            "class": class_id,
        })

        previous_boundary = boundary

    try:
        default_class = int(default_class)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Decision tree default_class is invalid.")

    if str(default_class) not in class_definitions:
        raise ValueError(
            f"Default class {default_class} is missing from class_definitions."
        )

    return normalized_branches, default_class


# ============================================================
# 4. DECISION TREE EVALUATION
# ============================================================

def _evaluate_decision_tree(
    value: float,
    branches: List[Dict[str, Any]],
    default_class: int,
    feature_name: str,
    unit: str = "",
    value_precision: int = 2,
    threshold_precision: int = 6,
) -> Tuple[int, List[str]]:
    """
    Evaluate configured branches and produce an actual decision path.

    For each branch:
        If value <= boundary:
            Assign the branch class.
        Otherwise:
            Continue to the next branch.

    If all boundaries are exceeded:
        Assign default_class.
    """

    decision_path = []

    value_text = f"{value:.{value_precision}f}{unit}"

    for branch in branches:

        boundary = branch["max_inclusive"]
        threshold_text = f"{boundary:.{threshold_precision}f}{unit}"

        if value <= boundary:

            decision_path.append(
                f"{feature_name} ({value_text}) <= {threshold_text}"
            )

            return branch["class"], decision_path

        decision_path.append(
            f"{feature_name} ({value_text}) > {threshold_text}"
        )

    decision_path.append(
        f"All configured boundaries exceeded; "
        f"default Class {default_class} assigned."
    )

    return default_class, decision_path


# ============================================================
# 5. MAIN TEXTURE THRESHOLD EVALUATOR
# ============================================================

def evaluate_texture_thresholds(
    features: Dict[str, Any],
    mask_coverage_pct: float = 0.0,
    valid_regions: int = 0,
    laplacian_variance: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluate PALF bundle texture using the configured candidate thresholds.

    Rule priority is read directly from the JSON configuration.

    Current priority:
        1. Regional orientation spread
        2. Whole-bundle orientation spread
        3. Gabor response anisotropy

    Laplacian variance is accepted for backward compatibility,
    but is NOT used as an image rejection threshold because its
    focus cutoff has not been validated.
    """

    if not isinstance(features, dict):
        features = {}

    # --------------------------------------------------------
    # A. Validate fiber mask coverage
    # --------------------------------------------------------

    coverage = _finite_number(mask_coverage_pct)

    if coverage is None or coverage < 0.0 or coverage > 100.0:

        return _unavailable_result(
            "insufficient_fiber_mask",
            features,
            "Fiber mask coverage is missing or outside the valid 0-100% range.",
        )

    if coverage <= 0.0:

        return _unavailable_result(
            "insufficient_fiber_mask",
            features,
            "Fiber mask is empty; texture analysis is unavailable.",
        )

    if coverage < 5.0:

        return _unavailable_result(
            "insufficient_fiber_mask",
            features,
            (
                f"Fiber coverage ({coverage:.1f}%) is below "
                "the configured 5.0% minimum."
            ),
        )

    # --------------------------------------------------------
    # B. Validate number of available regional cells
    # --------------------------------------------------------

    try:
        if isinstance(valid_regions, bool):
            raise ValueError("Boolean is not a valid region count.")

        region_count = int(valid_regions)

        if region_count < 0:
            raise ValueError("Region count cannot be negative.")

    except (TypeError, ValueError, OverflowError):

        region_count = 0

    # Laplacian variance is intentionally not used to reject
    # the image. It remains an image focus/sharpness diagnostic.
    _ = laplacian_variance

    # --------------------------------------------------------
    # C. Load JSON configuration
    # --------------------------------------------------------

    config = load_texture_rules_config()

    if not config:

        return _unavailable_result(
            "threshold_config_error",
            features,
            "Texture threshold JSON configuration could not be loaded.",
        )

    try:
        class_definitions, feature_rules, rule_priority = (
            _validate_configuration(config)
        )

    except ValueError as exc:

        logger.error("Invalid texture threshold configuration: %s", exc)

        return _unavailable_result(
            "threshold_config_error",
            features,
            str(exc),
        )

    # --------------------------------------------------------
    # D. Evaluate rules in the configured priority order
    # --------------------------------------------------------

    skipped_rules = []
    warnings = []

    for priority_index, priority_entry in enumerate(rule_priority):

        if not isinstance(priority_entry, dict):

            skipped_rules.append(
                f"Priority entry {priority_index} is invalid."
            )
            continue

        rule_id = priority_entry.get("rule_id")

        if not isinstance(rule_id, str) or not rule_id:

            skipped_rules.append(
                f"Priority entry {priority_index} has no valid rule_id."
            )
            continue

        # Check minimum number of valid regional cells.
        try:
            minimum_regions = int(
                priority_entry.get("min_valid_regions", 0)
            )

            if minimum_regions < 0:
                raise ValueError("Minimum region count cannot be negative.")

        except (TypeError, ValueError, OverflowError):

            skipped_rules.append(
                f"{rule_id}: invalid min_valid_regions configuration."
            )
            continue

        if region_count < minimum_regions:

            skipped_rules.append(
                f"{rule_id}: requires at least {minimum_regions} valid regions; "
                f"only {region_count} are available."
            )
            continue

        # Retrieve feature rule from the JSON configuration.
        rule_config = feature_rules.get(rule_id)

        if not isinstance(rule_config, dict):

            skipped_rules.append(
                f"{rule_id}: feature rule is missing from JSON configuration."
            )
            continue

        # Feature key defaults to the rule ID.
        feature_key = rule_config.get("feature_key", rule_id)

        if not isinstance(feature_key, str) or not feature_key:

            skipped_rules.append(
                f"{rule_id}: invalid feature_key configuration."
            )
            continue

        # Retrieve the corresponding measurement.
        feature_value = _finite_number(
            features.get(feature_key)
        )

        if feature_value is None:

            skipped_rules.append(
                f"{rule_id}: feature '{feature_key}' is missing or invalid."
            )
            continue

        # Retrieve configured decision tree.
        decision_tree = rule_config.get("decision_tree")

        if not isinstance(decision_tree, dict):

            skipped_rules.append(
                f"{rule_id}: decision_tree is missing from JSON configuration."
            )
            continue

        # Validate decision tree and its class assignments.
        try:

            branches, default_class = _validate_decision_tree(
                decision_tree,
                class_definitions,
            )

            # Select suitable display formatting.
            is_degrees = "spread_deg" in feature_key

            unit = "°" if is_degrees else ""

            value_precision = 2 if is_degrees else 4

            # Evaluate using JSON thresholds.
            predicted_class, decision_path = (
                _evaluate_decision_tree(
                    value=feature_value,
                    branches=branches,
                    default_class=default_class,
                    feature_name=feature_key,
                    unit=unit,
                    value_precision=value_precision,
                    threshold_precision=6,
                )
            )

        except (ValueError, TypeError, KeyError) as exc:

            logger.warning(
                "Skipping texture rule %s: %s",
                rule_id,
                exc,
            )

            skipped_rules.append(
                f"{rule_id}: invalid decision tree configuration: {exc}"
            )
            continue

        # ----------------------------------------------------
        # E. Retrieve predicted texture class metadata
        # ----------------------------------------------------

        class_metadata = class_definitions.get(
            str(predicted_class)
        )

        if not isinstance(class_metadata, dict):

            skipped_rules.append(
                f"{rule_id}: class {predicted_class} metadata is invalid."
            )
            continue

        texture_label = class_metadata.get("texture_label")
        display_name = class_metadata.get("display_name")
        associated_grade = class_metadata.get("associated_grade")
        pns_code = class_metadata.get("pns_code")

        if not all([
            texture_label,
            display_name,
            associated_grade,
            pns_code,
        ]):

            skipped_rules.append(
                f"{rule_id}: class metadata is incomplete."
            )
            continue

        # Preserve frontend naming convention.
        predicted_texture = str(texture_label).replace("_", "-")

        decision_path.append(
            f"Assigned Class {predicted_class}: "
            f"{display_name} / {associated_grade} / {pns_code}"
        )

        # ----------------------------------------------------
        # F. Retrieve validation statistics from JSON
        # ----------------------------------------------------

        validation_f1 = _finite_number(
            rule_config.get("cv_macro_f1")
        )

        validation_balanced_acc = _finite_number(
            rule_config.get("cv_balanced_accuracy")
        )

        # Also support the candidate_meta values if needed.
        candidate_meta = rule_config.get("candidate_meta") or {}

        if validation_f1 is None:
            validation_f1 = _finite_number(
                candidate_meta.get("cv_macro_f1")
            )

        if validation_balanced_acc is None:
            validation_balanced_acc = _finite_number(
                candidate_meta.get("cv_balanced_accuracy")
            )

        # ----------------------------------------------------
        # G. Record fallback information
        # ----------------------------------------------------

        if priority_index > 0:

            warnings.append(
                f"Fallback rule '{rule_id}' was used because "
                "a higher-priority rule was unavailable or did not "
                "meet its requirements."
            )

        warnings.extend(skipped_rules)

        # ----------------------------------------------------
        # H. Return successful texture assessment
        # ----------------------------------------------------

        return {
            "status": "available",
            "assessment_type": "experimental_threshold_based",

            "predicted_texture": predicted_texture,
            "display_name": display_name,
            "associated_grade": associated_grade,
            "pns_code": pns_code,

            "threshold_match": True,

            "features": features,

            "threshold_details": {
                "rule_id": rule_id,
                "features_used": [feature_key],
                "decision_path": decision_path,

                "candidate_thresholds": [
                    branch["max_inclusive"]
                    for branch in branches
                ],

                "validation_f1": validation_f1,
                "validation_balanced_acc": validation_balanced_acc,
            },

            "disclaimer": config.get(
                "disclaimer",
                "Experimental candidate reference comparison. "
                "Does not determine or alter deep learning model classification.",
            ),

            "warnings": warnings,
        }

    # --------------------------------------------------------
    # I. No usable threshold rule
    # --------------------------------------------------------

    logger.warning(
        "No texture threshold rule could be evaluated. Reasons: %s",
        skipped_rules,
    )

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
            "decision_path": skipped_rules or [
                "No configured candidate texture rule could be evaluated."
            ],
        },

        "disclaimer": config.get(
            "disclaimer",
            "Experimental candidate reference comparison.",
        ),

        "warnings": [
            "Texture threshold evaluation could not find an available candidate feature."
        ] + skipped_rules,
    }

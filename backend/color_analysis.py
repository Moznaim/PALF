"""
backend/color_analysis.py

PALF-Vision AI: Candidate Color Reference Analysis (PNS/BAFS 318:2021)
=======================================================================
PROOF-OF-CONCEPT / EXPERIMENTAL REFERENCE COMPARISON MODULE.

Research & Standard Context:
- Aligned with PNS/BAFS 318:2021 (Pineapple Fiber – Grading and Classification).
- Analyzes candidate color-reference ranges (P05, median, P95) across RGB and CIELAB spaces.
- Status: threshold_status = "candidate_unvalidated".
- IMPORTANT: This is an experimental proof-of-concept comparison. It is NOT an approved
  PNS numerical grading rule and must NEVER override, alter, or downgrade the deep learning
  classification grade (Excellent / Good / Fair).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from PIL import Image

logger = logging.getLogger("palf_color_analysis")

CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "config", "palf_color_reference_thresholds.json"
)

# Regional Quality Control constants
MIN_REGION_COVERAGE = 0.40
MIN_PIXELS_PER_REGION = 1000


def load_color_reference_config(config_path: str = CONFIG_PATH) -> Dict[str, Any]:
    """
    Loads candidate color-reference thresholds from versioned JSON configuration.
    Raises RuntimeError if file is missing or malformed to avoid silent fallbacks.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Candidate color reference configuration file not found at: {config_path}"
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(
            f"Failed to parse candidate color reference configuration '{config_path}': {e}"
        )

    if "references" not in data or not isinstance(data["references"], list):
        raise ValueError("Color reference configuration must contain a 'references' list.")

    return data


def extract_analysis_roi(
    image: Any,
    x0: Optional[int] = None,
    y0: Optional[int] = None,
    x1: Optional[int] = None,
    y1: Optional[int] = None,
) -> Tuple[np.ndarray, Dict[str, int]]:
    """
    Extracts the rectangular ROI for color analysis.
    If explicit pixel coordinates (x0, y0, x1, y1) are not provided:
    maps proportional inner fiber bundle area (normalized 0.20-0.80 Y, 0.15-0.85 X)
    or clamps reference coordinates [0:3000, 1000:2500] if resolution matches reference.
    """
    if isinstance(image, Image.Image):
        rgb_arr = np.asarray(image.convert("RGB"), dtype=np.uint8)
    elif isinstance(image, np.ndarray):
        rgb_arr = image if image.ndim == 3 else np.stack([image] * 3, axis=-1)
    else:
        raise ValueError(f"Unsupported image type for color analysis: {type(image)}")

    h, w = rgb_arr.shape[:2]

    # Check if explicit pixel coordinates match image size
    if x0 is not None and y0 is not None and x1 is not None and y1 is not None:
        c_x0 = max(0, min(int(x0), w - 1))
        c_x1 = max(c_x0 + 1, min(int(x1), w))
        c_y0 = max(0, min(int(y0), h - 1))
        c_y1 = max(c_y0 + 1, min(int(y1), h))
    elif w >= 3000 and h >= 2500:
        # Reference setup resolution: fixed original pixel bounds
        c_x0, c_x1 = 0, min(3000, w)
        c_y0, c_y1 = 1000, min(2500, h)
    else:
        # Proportional inner bundle area
        c_y0 = int(round(h * float(os.getenv("PALF_ROI_YMIN", "0.20"))))
        c_y1 = int(round(h * float(os.getenv("PALF_ROI_YMAX", "0.80"))))
        c_x0 = int(round(w * float(os.getenv("PALF_ROI_XMIN", "0.15"))))
        c_x1 = int(round(w * float(os.getenv("PALF_ROI_XMAX", "0.85"))))

    # Clamp safely
    c_x0 = max(0, min(c_x0, w - 1))
    c_x1 = max(c_x0 + 1, min(c_x1, w))
    c_y0 = max(0, min(c_y0, h - 1))
    c_y1 = max(c_y0 + 1, min(c_y1, h))

    roi = rgb_arr[c_y0:c_y1, c_x0:c_x1].copy()
    coords = {"x0": c_x0, "y0": c_y0, "x1": c_x1, "y1": c_y1}
    return roi, coords


def extract_analysis_mask(roi_rgb: np.ndarray) -> np.ndarray:
    """
    Extracts binary fiber bundle mask rejecting blue background and dark holder.
    Uses blue-exclusion in HSV matching notebook configuration:
      Hue: 85-140, Saturation >= 45, Value >= 25.
    """
    h, w, _ = roi_rgb.shape

    if HAS_CV2:
        gray = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2HSV)

        # Blue background in HSV (hue 85..140, sat >= 45, val >= 25)
        is_blue_bg = (
            (hsv[:, :, 0] >= 85) &
            (hsv[:, :, 0] <= 140) &
            (hsv[:, :, 1] >= 45) &
            (hsv[:, :, 2] >= 25)
        )

        # Exclude blue background and pitch-black frame/shadows (gray <= 20)
        mask = (~is_blue_bg) & (gray > 20)

        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask_uint8 = (mask.astype(np.uint8)) * 255
        mask_clean = cv2.morphologyEx(mask_uint8, cv2.MORPH_CLOSE, kernel_close)
        return mask_clean > 0
    else:
        r = roi_rgb[:, :, 0].astype(np.int32)
        g = roi_rgb[:, :, 1].astype(np.int32)
        b = roi_rgb[:, :, 2].astype(np.int32)
        is_blue = (b > r + 30) & (b > g + 15) & (b > 60)
        gray = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.uint8)
        return (~is_blue) & (gray > 20)


def compute_channel_stats(values: np.ndarray) -> Dict[str, Optional[float]]:
    """Calculates mean, median, standard deviation, P05, and P95 for a 1D pixel channel."""
    if len(values) == 0:
        return {"mean": None, "median": None, "std": None, "p05": None, "p95": None}

    return {
        "mean": round(float(np.mean(values)), 4),
        "median": round(float(np.median(values)), 4),
        "std": round(float(np.std(values)), 4),
        "p05": round(float(np.percentile(values, 5)), 4),
        "p95": round(float(np.percentile(values, 95)), 4),
    }


def evaluate_candidate_matches(
    measured_rgb: Dict[str, Dict[str, Optional[float]]],
    measured_lab: Dict[str, Dict[str, Optional[float]]],
    references: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Compares inspection stats against the 6 candidate reference profiles.
    Evaluates range overlap (inspection median in reference P05-P95, and vice versa)
    and computes CIELAB Euclidean color difference (Delta E) to reference medians.

    Allows multiple candidate matches and does NOT force a single color label.
    """
    candidate_matches = []

    m_l = measured_lab["L_star"]["median"]
    m_a = measured_lab["a_star"]["median"]
    m_b = measured_lab["b_star"]["median"]

    if m_l is None or m_a is None or m_b is None:
        return []

    for ref in references:
        key = ref["reference_key"]
        quality = ref["quality"]
        pns_pid = ref["pns_pid"]
        color_label = ref["color_label"]
        rgb_bounds = ref.get("rgb", {})
        lab_bounds = ref.get("cielab", {})

        matched_channels = []
        channel_details = {}

        # 1. CIELAB channels check
        for ch_key, ch_name in [("L_star", "L*"), ("a_star", "a*"), ("b_star", "b*")]:
            ref_ch = lab_bounds.get(ch_key, {})
            ref_p05 = ref_ch.get("p05")
            ref_p95 = ref_ch.get("p95")
            ref_med = ref_ch.get("median")

            ins_med = measured_lab[ch_key]["median"]
            ins_p05 = measured_lab[ch_key]["p05"]
            ins_p95 = measured_lab[ch_key]["p95"]

            if None not in (ref_p05, ref_p95, ins_med):
                # Check overlap: inspection median in reference range OR ranges overlap
                in_range = bool(ref_p05 <= ins_med <= ref_p95)
                if in_range:
                    matched_channels.append(ch_key)
                channel_details[ch_key] = {
                    "in_range": in_range,
                    "inspection_median": ins_med,
                    "reference_median": ref_med,
                    "reference_p05": ref_p05,
                    "reference_p95": ref_p95,
                }

        # 2. RGB channels check
        for ch in ["R", "G", "B"]:
            ref_ch = rgb_bounds.get(ch, {})
            ref_p05 = ref_ch.get("p05")
            ref_p95 = ref_ch.get("p95")
            ref_med = ref_ch.get("median")

            ins_med = measured_rgb[ch]["median"]

            if None not in (ref_p05, ref_p95, ins_med):
                in_range = bool(ref_p05 <= ins_med <= ref_p95)
                if in_range:
                    matched_channels.append(ch)
                channel_details[ch] = {
                    "in_range": in_range,
                    "inspection_median": ins_med,
                    "reference_median": ref_med,
                    "reference_p05": ref_p05,
                    "reference_p95": ref_p95,
                }

        # CIELAB Delta E distance between inspection median and reference median
        ref_l_med = lab_bounds.get("L_star", {}).get("median", 0.0)
        ref_a_med = lab_bounds.get("a_star", {}).get("median", 0.0)
        ref_b_med = lab_bounds.get("b_star", {}).get("median", 0.0)
        delta_e = float(
            np.sqrt(
                (m_l - ref_l_med) ** 2 +
                (m_a - ref_a_med) ** 2 +
                (m_b - ref_b_med) ** 2
            )
        )

        # Candidate match criteria: at least 4 channels in-range, or L* and a* and b* all in-range
        is_candidate = (len(matched_channels) >= 4) or all(
            k in matched_channels for k in ["L_star", "a_star", "b_star"]
        )

        match_record = {
            "reference_key": key,
            "quality": quality,
            "pns_pid": pns_pid,
            "color_label": color_label,
            "pns_description": ref.get("pns_description", ""),
            "is_candidate": is_candidate,
            "matched_channel_count": len(matched_channels),
            "matched_channels": matched_channels,
            "delta_e_to_reference_median": round(delta_e, 2),
            "channel_details": channel_details,
        }
        candidate_matches.append(match_record)

    # Sort candidates by Delta E distance ascending
    candidate_matches.sort(key=lambda x: x["delta_e_to_reference_median"])
    return candidate_matches


def analyze_color_references(
    image: Any,
    config_path: str = CONFIG_PATH,
    x0: Optional[int] = None,
    y0: Optional[int] = None,
    x1: Optional[int] = None,
    y1: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Main entry point for candidate color analysis.
    Executes ROI extraction, fiber masking, RGB/CIELAB stats calculation,
    regional quality control (3x3 grid), and candidate reference matching.

    Guaranteed not to raise an unhandled exception.
    """
    try:
        config = load_color_reference_config(config_path)
    except Exception as e:
        logger.error(f"Failed to load color reference configuration: {e}")
        return {
            "status": "error",
            "mode": "experimental_reference_comparison",
            "threshold_status": "candidate_unvalidated",
            "error": f"Configuration error: {str(e)}",
            "candidate_matches": [],
            "warnings": ["Color reference configuration file missing or malformed."],
        }

    try:
        # 1. ROI Extraction
        roi_rgb, roi_coords = extract_analysis_roi(image, x0, y0, x1, y1)
        h_roi, w_roi = roi_rgb.shape[:2]

        if h_roi < 32 or w_roi < 32:
            return {
                "status": "error",
                "mode": "experimental_reference_comparison",
                "threshold_status": "candidate_unvalidated",
                "roi": roi_coords,
                "error": f"ROI dimensions ({w_roi}x{h_roi}) too small for color analysis.",
                "candidate_matches": [],
                "warnings": ["ROI dimensions are insufficient."],
            }

        # 2. Fiber Mask Extraction
        fiber_mask = extract_analysis_mask(roi_rgb)
        included_pixels = int(fiber_mask.sum())
        roi_pixels = int(fiber_mask.size)
        coverage = float(included_pixels / max(1, roi_pixels))

        warnings: List[str] = []

        if included_pixels == 0:
            return {
                "status": "unavailable",
                "mode": "experimental_reference_comparison",
                "threshold_status": "candidate_unvalidated",
                "roi": roi_coords,
                "mask": {
                    "coverage": 0.0,
                    "included_pixels": 0,
                    "roi_pixels": roi_pixels,
                    "valid_regions": 0,
                    "total_regions": 9,
                },
                "rgb": {
                    "R": {"mean": None, "median": None, "std": None, "p05": None, "p95": None},
                    "G": {"mean": None, "median": None, "std": None, "p05": None, "p95": None},
                    "B": {"mean": None, "median": None, "std": None, "p05": None, "p95": None},
                },
                "cielab": {
                    "L_star": {"mean": None, "median": None, "std": None, "p05": None, "p95": None},
                    "a_star": {"mean": None, "median": None, "std": None, "p05": None, "p95": None},
                    "b_star": {"mean": None, "median": None, "std": None, "p05": None, "p95": None},
                },
                "candidate_matches": [],
                "warnings": ["Color analysis unavailable: fiber mask is empty; review camera lighting and framing."],
            }

        if coverage < 0.05:
            warnings.append("Low fiber coverage (< 5% of ROI); color analysis may reflect boundary artifacts.")
        elif coverage > 0.95:
            warnings.append("Excessive foreground coverage (> 95% of ROI); check background exclusion.")

        # 3. Masked RGB Statistics
        r_vals = roi_rgb[:, :, 0][fiber_mask].ravel()
        g_vals = roi_rgb[:, :, 1][fiber_mask].ravel()
        b_vals = roi_rgb[:, :, 2][fiber_mask].ravel()

        rgb_stats = {
            "R": compute_channel_stats(r_vals),
            "G": compute_channel_stats(g_vals),
            "B": compute_channel_stats(b_vals),
        }

        # 4. Masked CIELAB Statistics (OpenCV float32 RGB-to-Lab)
        rgb_f32 = roi_rgb.astype(np.float32) / 255.0
        if HAS_CV2:
            lab_arr = cv2.cvtColor(rgb_f32, cv2.COLOR_RGB2Lab)
        else:
            from visual_metrics import rgb_to_cielab
            lab_arr = rgb_to_cielab(roi_rgb)

        l_vals = lab_arr[:, :, 0][fiber_mask].ravel()
        a_vals = lab_arr[:, :, 1][fiber_mask].ravel()
        b_vals = lab_arr[:, :, 2][fiber_mask].ravel()

        cielab_stats = {
            "L_star": compute_channel_stats(l_vals),
            "a_star": compute_channel_stats(a_vals),
            "b_star": compute_channel_stats(b_vals),
        }

        # 5. Regional Quality Control (3x3 grid)
        n_rows, n_cols = 3, 3
        r_step = h_roi // n_rows
        c_step = w_roi // n_cols
        valid_regions_count = 0

        for r in range(n_rows):
            for c in range(n_cols):
                y_start = r * r_step
                y_end = (r + 1) * r_step if r < n_rows - 1 else h_roi
                x_start = c * c_step
                x_end = (c + 1) * c_step if c < n_cols - 1 else w_roi

                sub_mask = fiber_mask[y_start:y_end, x_start:x_end]
                sub_included = int(sub_mask.sum())
                sub_total = int(sub_mask.size)
                sub_cov = float(sub_included / max(1, sub_total))

                if (sub_cov >= MIN_REGION_COVERAGE) and (sub_included >= MIN_PIXELS_PER_REGION):
                    valid_regions_count += 1

        if valid_regions_count < 3:
            warnings.append(
                f"Low regional uniformity: only {valid_regions_count}/9 regions meet the 40% coverage threshold."
            )

        # 6. Candidate Reference Matching
        references = config.get("references", [])
        candidate_matches = evaluate_candidate_matches(rgb_stats, cielab_stats, references)

        return {
            "status": "ok",
            "mode": "experimental_reference_comparison",
            "threshold_status": "candidate_unvalidated",
            "config_version": config.get("version", "1.0.0"),
            "roi": roi_coords,
            "mask": {
                "coverage": round(coverage, 4),
                "included_pixels": included_pixels,
                "roi_pixels": roi_pixels,
                "valid_regions": valid_regions_count,
                "total_regions": 9,
            },
            "rgb": rgb_stats,
            "cielab": cielab_stats,
            "candidate_matches": candidate_matches,
            "warnings": warnings,
        }

    except Exception as e:
        logger.error(f"Candidate color analysis failed gracefully: {e}", exc_info=True)
        return {
            "status": "error",
            "mode": "experimental_reference_comparison",
            "threshold_status": "candidate_unvalidated",
            "error": str(e),
            "candidate_matches": [],
            "warnings": [f"Color analysis exception: {str(e)}"],
        }

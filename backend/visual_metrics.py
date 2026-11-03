"""
backend/visual_metrics.py

PALF-Vision AI: Color and Bundle Texture Measurement Module
===========================================================
Research references:
1. Haralick, Shanmugam, and Dinstein (1973). Textural Features for Image Classification.
   IEEE Transactions on Systems, Man, and Cybernetics, SMC-3(6), 610-621.
2. ISO/CIE 11664-4:2019. Colorimetry – CIE 1976 L*a*b* colour space.
3. Ghodrati, Gorji Kandi, and Mohseni (2018). Computer-based texture characterization.
4. PNS/BAFS 318:2021. Pineapple Fiber – Product Standard – Grading and Classification.

Scope & Limitations:
- Analyzes macro-level cleaned pineapple leaf fiber (PALF) bundles.
- Does NOT investigate individual fiber strands, microscopic morphology, or physical hand.
- Color measurements are camera-derived CIELAB and pending physical colorimeter calibration.
- Texture descriptors (GLCM) quantify spatial grayscale distributions across the bundle.
- Laplacian variance measures optical sharpness/focus, not physical fiber roughness.
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple, List
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from PIL import Image

logger = logging.getLogger("palf_visual_metrics")

# ==============================================================================
# CONFIGURABLE ROI & ALGORITHM CONSTANTS
# ==============================================================================
# Normalized coordinates (0.0 to 1.0) covering the inner fiber holder area
DEFAULT_ROI_YMIN = float(os.getenv("PALF_ROI_YMIN", "0.15"))
DEFAULT_ROI_YMAX = float(os.getenv("PALF_ROI_YMAX", "0.85"))
DEFAULT_ROI_XMIN = float(os.getenv("PALF_ROI_XMIN", "0.10"))
DEFAULT_ROI_XMAX = float(os.getenv("PALF_ROI_XMAX", "0.90"))

# GLCM default parameters
DEFAULT_GLCM_LEVELS = int(os.getenv("PALF_GLCM_LEVELS", "16"))
DEFAULT_GLCM_DISTANCE = int(os.getenv("PALF_GLCM_DISTANCE", "1"))
DEFAULT_GLCM_DIRECTIONS = [0, 45, 90, 135]


# ==============================================================================
# 1. ROI EXTRACTION & FIBER MASKING
# ==============================================================================

def extract_fiber_roi(
    image: Any,
    ymin: float = DEFAULT_ROI_YMIN,
    ymax: float = DEFAULT_ROI_YMAX,
    xmin: float = DEFAULT_ROI_XMIN,
    xmax: float = DEFAULT_ROI_XMAX,
) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """
    Extracts the rectangular ROI covering the inner PALF fiber holder.
    Accepts PIL.Image or numpy.ndarray (RGB).
    Returns (roi_rgb, (y1, y2, x1, x2)).
    """
    if isinstance(image, Image.Image):
        rgb_arr = np.asarray(image.convert("RGB"), dtype=np.uint8)
    elif isinstance(image, np.ndarray):
        rgb_arr = image if image.ndim == 3 else np.stack([image]*3, axis=-1)
    else:
        raise ValueError(f"Unsupported image type for ROI extraction: {type(image)}")

    h, w = rgb_arr.shape[:2]
    y1 = max(0, min(int(h * ymin), h - 1))
    y2 = max(y1 + 1, min(int(h * ymax), h))
    x1 = max(0, min(int(w * xmin), w - 1))
    x2 = max(x1 + 1, min(int(w * xmax), w))

    roi = rgb_arr[y1:y2, x1:x2].copy()
    return roi, (y1, y2, x1, x2)


def extract_fiber_mask(roi_rgb: np.ndarray) -> np.ndarray:
    """
    Segments the PALF fiber bundle (off-white/cream/light-tan) from
    the dark blue/black background and holder frame.
    Returns boolean 2D mask of shape (H, W) where True = valid fiber pixel.
    """
    h, w, _ = roi_rgb.shape

    # 1. Calculate grayscale intensity
    if HAS_CV2:
        gray = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2GRAY)
    else:
        gray = (
            0.299 * roi_rgb[:, :, 0] +
            0.587 * roi_rgb[:, :, 1] +
            0.114 * roi_rgb[:, :, 2]
        ).astype(np.uint8)

    # 2. Identify and exclude blue background:
    # In RGB: blue background has significantly higher B channel relative to R and G
    r = roi_rgb[:, :, 0].astype(np.int32)
    g = roi_rgb[:, :, 1].astype(np.int32)
    b = roi_rgb[:, :, 2].astype(np.int32)
    is_blue_bg = (b > r + 15) & (b > g)

    # 3. Intensity thresholding:
    # Fiber bundles are brighter than dark holder surfaces
    if HAS_CV2:
        otsu_val, mask_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Combine Otsu with blue exclusion
        mask = (mask_otsu > 0) & (~is_blue_bg)

        # Morphological clean-up: remove small speckles and close narrow bundle gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask_uint8 = (mask.astype(np.uint8)) * 255
        mask_clean = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, kernel)
        mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_CLOSE, kernel)
        fiber_mask = mask_clean > 0
    else:
        threshold = int(np.mean(gray))
        fiber_mask = (gray > threshold) & (~is_blue_bg)

    return fiber_mask


# ==============================================================================
# 2. COLOR MEASUREMENT (CIELAB - ISO/CIE 11664-4:2019)
# ==============================================================================

def rgb_to_cielab(rgb_roi: np.ndarray) -> np.ndarray:
    """
    Converts RGB uint8 array (shape H, W, 3) to CIELAB float32 array.
    L* in [0, 100], a* in [-128, 127], b* in [-128, 127].
    Uses OpenCV if available, or direct D65 standard conversion as fallback.
    """
    rgb_f = rgb_roi.astype(np.float32) / 255.0

    if HAS_CV2:
        return cv2.cvtColor(rgb_f, cv2.COLOR_RGB2LAB)

    # Fallback: ISO/CIE 11664-4:2019 standard conversion (D65 illuminant, 2° observer)
    # 1. sRGB to linear RGB (inverse gamma companding)
    mask_lin = rgb_f > 0.04045
    rgb_lin = np.empty_like(rgb_f)
    rgb_lin[mask_lin] = ((rgb_f[mask_lin] + 0.055) / 1.055) ** 2.4
    rgb_lin[~mask_lin] = rgb_f[~mask_lin] / 12.92

    # 2. Linear RGB to CIE XYZ (sRGB D65 matrix)
    x = rgb_lin[:, :, 0] * 0.4124564 + rgb_lin[:, :, 1] * 0.3575761 + rgb_lin[:, :, 2] * 0.1804375
    y = rgb_lin[:, :, 0] * 0.2126729 + rgb_lin[:, :, 1] * 0.7151522 + rgb_lin[:, :, 2] * 0.0721750
    z = rgb_lin[:, :, 0] * 0.0193339 + rgb_lin[:, :, 1] * 0.1191920 + rgb_lin[:, :, 2] * 0.9503041

    # D65 reference white
    xn, yn, zn = 0.95047, 1.00000, 1.08883
    xr, yr, zr = x / xn, y / yn, z / zn

    # f(t) transformation
    eps = (6.0 / 29.0) ** 3  # ~0.008856
    kappa = (29.0 / 6.0) ** 2 / 3.0  # ~7.787
    delta = 4.0 / 29.0

    fx = np.where(xr > eps, xr ** (1.0 / 3.0), kappa * xr + delta)
    fy = np.where(yr > eps, yr ** (1.0 / 3.0), kappa * yr + delta)
    fz = np.where(zr > eps, zr ** (1.0 / 3.0), kappa * zr + delta)

    L = 116.0 * fy - 16.0
    A = 500.0 * (fx - fy)
    B = 200.0 * (fy - fz)

    return np.stack([L, A, B], axis=-1)


def cielab_to_hex(l_val: float, a_val: float, b_val: float) -> str:
    """Computes a representative sRGB hex color (#RRGGBB) from CIELAB coordinates."""
    try:
        lab_pixel = np.array([[[l_val, a_val, b_val]]], dtype=np.float32)
        if HAS_CV2:
            rgb_f = cv2.cvtColor(lab_pixel, cv2.COLOR_LAB2RGB)[0, 0]
        else:
            # Fallback simple approximate clip
            rgb_f = np.array([l_val / 100.0, (l_val + a_val) / 100.0, (l_val + b_val) / 100.0])
        rgb_8u = np.clip(rgb_f * 255.0, 0, 255).astype(np.uint8)
        return f"#{rgb_8u[0]:02x}{rgb_8u[1]:02x}{rgb_8u[2]:02x}"
    except Exception:
        return "#e0d8cc"


def extract_color_metrics(roi_rgb: np.ndarray, mask: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """
    Extracts mean and standard deviation of CIELAB color components (L*, a*, b*),
    chroma, and a representative display hex swatch.
    """
    lab = rgb_to_cielab(roi_rgb)
    L = lab[:, :, 0]
    A = lab[:, :, 1]
    B = lab[:, :, 2]

    if mask is not None and mask.sum() > 0:
        valid_l = L[mask]
        valid_a = A[mask]
        valid_b = B[mask]
    else:
        valid_l = L.ravel()
        valid_a = A.ravel()
        valid_b = B.ravel()

    mean_l = float(np.mean(valid_l))
    mean_a = float(np.mean(valid_a))
    mean_b = float(np.mean(valid_b))
    std_l = float(np.std(valid_l))
    std_a = float(np.std(valid_a))
    std_b = float(np.std(valid_b))

    chroma_vals = np.sqrt(valid_a ** 2 + valid_b ** 2)
    mean_chroma = float(np.mean(chroma_vals))
    hex_code = cielab_to_hex(mean_l, mean_a, mean_b)

    return {
        "color_space": "CIELAB",
        "l_star": round(mean_l, 2),
        "a_star": round(mean_a, 2),
        "b_star": round(mean_b, 2),
        "mean_L_star": round(mean_l, 2),
        "mean_a_star": round(mean_a, 2),
        "mean_b_star": round(mean_b, 2),
        "l_star_std": round(std_l, 2),
        "a_star_std": round(std_a, 2),
        "b_star_std": round(std_b, 2),
        "chroma": round(mean_chroma, 2),
        "mean_chroma": round(mean_chroma, 2),
        "hex_color": hex_code,
        "calibration_status": "Camera-derived CIELAB measurements - calibration pending",
    }


# ==============================================================================
# 3. TEXTURE MEASUREMENT (GLCM - Pure NumPy Implementation)
# ==============================================================================

def calculate_glcm_features(
    gray_img: np.ndarray,
    mask: Optional[np.ndarray] = None,
    levels: int = DEFAULT_GLCM_LEVELS,
    distance: int = DEFAULT_GLCM_DISTANCE,
    directions: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Calculates Gray-Level Co-occurrence Matrix (GLCM) textural descriptors
    using pure NumPy without external scikit-image dependency.

    Features calculated:
    - Contrast:    sum(P(i,j) * (i - j)^2)
    - Homogeneity: sum(P(i,j) / (1 + (i - j)^2))
    - Energy:      sum(P(i,j)^2)  (Angular Second Moment / ASM)
    - Entropy:     -sum(P(i,j) * log2(P(i,j)))
    """
    if directions is None:
        directions = DEFAULT_GLCM_DIRECTIONS

    # Quantize grayscale (0-255) to 0..(levels-1)
    scale_factor = 256 // levels
    gray_q = (gray_img // scale_factor).astype(np.uint8)
    gray_q = np.clip(gray_q, 0, levels - 1)

    h, w = gray_q.shape

    if mask is None:
        mask = np.ones((h, w), dtype=bool)

    i_indices, j_indices = np.indices((levels, levels))
    diff_sq = (i_indices - j_indices) ** 2
    homog_denom = 1.0 + diff_sq

    # Map angle degrees to (dy, dx)
    angle_shifts = {
        0:   (0, distance),
        45:  (-distance, distance),
        90:  (-distance, 0),
        135: (-distance, -distance),
    }

    dir_contrast = []
    dir_homogeneity = []
    dir_energy = []
    dir_entropy = []

    for deg in directions:
        if deg not in angle_shifts:
            continue
        dy, dx = angle_shifts[deg]

        if dy == 0 and dx > 0:
            p1 = gray_q[:, :-dx]
            p2 = gray_q[:, dx:]
            m = mask[:, :-dx] & mask[:, dx:]
        elif dy < 0 and dx > 0:
            abs_dy = abs(dy)
            p1 = gray_q[abs_dy:, :-dx]
            p2 = gray_q[:-abs_dy, dx:]
            m = mask[abs_dy:, :-dx] & mask[:-abs_dy, dx:]
        elif dy < 0 and dx == 0:
            abs_dy = abs(dy)
            p1 = gray_q[abs_dy:, :]
            p2 = gray_q[:-abs_dy, :]
            m = mask[abs_dy:, :] & mask[:-abs_dy, :]
        elif dy < 0 and dx < 0:
            abs_dy = abs(dy)
            abs_dx = abs(dx)
            p1 = gray_q[abs_dy:, abs_dx:]
            p2 = gray_q[:-abs_dy, :-abs_dx]
            m = mask[abs_dy:, abs_dx:] & mask[:-abs_dy, :-abs_dx]
        else:
            continue

        p1_valid = p1[m].ravel().astype(np.int64)
        p2_valid = p2[m].ravel().astype(np.int64)

        if len(p1_valid) == 0:
            continue

        # Co-occurrence counts
        counts = np.bincount(
            p1_valid * levels + p2_valid,
            minlength=levels * levels
        ).reshape((levels, levels))

        # Symmetrical GLCM
        P = counts + counts.T
        total = P.sum()
        if total == 0:
            continue

        P_norm = P.astype(np.float64) / total

        # Compute Haralick features
        cont = float((P_norm * diff_sq).sum())
        homog = float((P_norm / homog_denom).sum())
        asm = float((P_norm ** 2).sum())

        nonzero = P_norm[P_norm > 0]
        ent = float(-(nonzero * np.log2(nonzero)).sum())

        dir_contrast.append(cont)
        dir_homogeneity.append(homog)
        dir_energy.append(asm)
        dir_entropy.append(ent)

    if not dir_contrast:
        return {
            "method": "GLCM",
            "contrast": None,
            "homogeneity": None,
            "entropy": None,
            "energy": None,
            "directions": directions,
            "gray_levels": levels,
            "distance_pixels": distance,
        }

    return {
        "method": "GLCM",
        "contrast": round(float(np.mean(dir_contrast)), 4),
        "homogeneity": round(float(np.mean(dir_homogeneity)), 4),
        "entropy": round(float(np.mean(dir_entropy)), 4),
        "energy": round(float(np.mean(dir_energy)), 4),
        "directions": directions,
        "gray_levels": levels,
        "distance_pixels": distance,
    }


# ==============================================================================
# 4. BUNDLE UNIFORMITY (3x3 Regional Grid Analysis)
# ==============================================================================

def calculate_bundle_uniformity(
    gray_img: np.ndarray,
    mask: Optional[np.ndarray] = None,
    grid: Tuple[int, int] = (3, 3),
    levels: int = DEFAULT_GLCM_LEVELS,
) -> Dict[str, Any]:
    """
    Subdivides the PALF fiber bundle ROI into a 3x3 grid (9 regions) to quantify
    spatial variation in contrast and homogeneity across the bundle.
    Skips subregions with insufficient valid fiber coverage.
    """
    h, w = gray_img.shape
    if mask is None:
        mask = np.ones((h, w), dtype=bool)

    n_rows, n_cols = grid
    r_step = h // n_rows
    c_step = w // n_cols

    regional_contrasts: List[float] = []
    regional_homogeneities: List[float] = []

    for r in range(n_rows):
        for c in range(n_cols):
            y_start = r * r_step
            y_end = (r + 1) * r_step if r < n_rows - 1 else h
            x_start = c * c_step
            x_end = (c + 1) * c_step if c < n_cols - 1 else w

            sub_gray = gray_img[y_start:y_end, x_start:x_end]
            sub_mask = mask[y_start:y_end, x_start:x_end]

            valid_count = int(sub_mask.sum())
            total_count = sub_mask.size

            # Skip cells with fewer than 40 valid pixels or < 4% coverage
            if valid_count < 40 or (valid_count / max(1, total_count)) < 0.04:
                continue

            feats = calculate_glcm_features(
                sub_gray,
                mask=sub_mask,
                levels=levels,
                distance=1,
            )

            if feats["contrast"] is not None and feats["homogeneity"] is not None:
                regional_contrasts.append(feats["contrast"])
                regional_homogeneities.append(feats["homogeneity"])

    valid_regions_count = len(regional_contrasts)

    if valid_regions_count == 0:
        return {
            "grid": list(grid),
            "valid_regions": 0,
            "contrast_mean": None,
            "contrast_std": None,
            "homogeneity_mean": None,
            "homogeneity_std": None,
        }

    c_mean = float(np.mean(regional_contrasts))
    c_std = float(np.std(regional_contrasts)) if valid_regions_count > 1 else 0.0
    h_mean = float(np.mean(regional_homogeneities))
    h_std = float(np.std(regional_homogeneities)) if valid_regions_count > 1 else 0.0

    return {
        "grid": list(grid),
        "valid_regions": valid_regions_count,
        "contrast_mean": round(c_mean, 4),
        "contrast_std": round(c_std, 4),
        "homogeneity_mean": round(h_mean, 4),
        "homogeneity_std": round(h_std, 4),
    }


# ==============================================================================
# 5. IMAGE QUALITY CHECK (Laplacian Variance Focus Metric)
# ==============================================================================

def calculate_image_quality(
    gray_img: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Computes Laplacian variance as an image sharpness indicator.
    Note: Indicates focus/blur only; not a measure of physical fiber roughness.
    """
    try:
        if HAS_CV2:
            lap_var = float(cv2.Laplacian(gray_img, cv2.CV_64F).var())
        else:
            # 3x3 discrete Laplacian kernel
            kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)
            # Simple 2D convolution for interior pixels
            h, w = gray_img.shape
            g_f = gray_img.astype(np.float64)
            lap = (
                g_f[0:h-2, 1:w-1] +
                g_f[2:h,   1:w-1] +
                g_f[1:h-1, 0:w-2] +
                g_f[1:h-1, 2:w]   -
                4.0 * g_f[1:h-1, 1:w-1]
            )
            lap_var = float(lap.var())

        return {
            "laplacian_variance": round(lap_var, 2),
            "status": "unvalidated",
        }
    except Exception as e:
        logger.warning(f"Laplacian variance calculation error: {e}")
        return {
            "laplacian_variance": None,
            "status": "unvalidated",
        }


# ==============================================================================
# 6. MASTER VISUAL METRICS PIPELINE
# ==============================================================================

def extract_visual_metrics(image: Any) -> Dict[str, Any]:
    """
    Master pipeline executing independent color and bundle texture analysis.
    Does NOT modify the deep learning model or image tensor.
    Guaranteed not to raise an exception; returns structured warning/error on failure.
    """
    try:
        # 1. Extract Configurable Fiber ROI
        roi_rgb, (y1, y2, x1, x2) = extract_fiber_roi(image)
        h_roi, w_roi = roi_rgb.shape[:2]

        if h_roi < 10 or w_roi < 10:
            return {
                "status": "error",
                "error": "Extracted ROI dimensions are too small for measurement",
                "method_version": "bundle_metrics_v1",
                "color": None,
                "texture": None,
                "uniformity": None,
                "image_quality": None,
            }

        # 2. Extract Fiber Mask
        fiber_mask = extract_fiber_mask(roi_rgb)
        coverage_pct = float(fiber_mask.mean() * 100.0)

        # 3. Grayscale conversion for texture and quality
        if HAS_CV2:
            gray_roi = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2GRAY)
        else:
            gray_roi = (
                0.299 * roi_rgb[:, :, 0] +
                0.587 * roi_rgb[:, :, 1] +
                0.114 * roi_rgb[:, :, 2]
            ).astype(np.uint8)

        # 4. Color Measurements (CIELAB)
        color_data = extract_color_metrics(roi_rgb, mask=fiber_mask)

        # 5. Texture Measurements (GLCM)
        texture_data = calculate_glcm_features(
            gray_roi,
            mask=fiber_mask,
            levels=DEFAULT_GLCM_LEVELS,
            distance=DEFAULT_GLCM_DISTANCE,
        )

        # 6. Bundle Uniformity (3x3 grid)
        uniformity_data = calculate_bundle_uniformity(
            gray_roi,
            mask=fiber_mask,
            grid=(3, 3),
            levels=DEFAULT_GLCM_LEVELS,
        )

        # 7. Image Quality Check
        quality_data = calculate_image_quality(gray_roi, mask=fiber_mask)

        status_flag = "ok"
        if coverage_pct < 5.0:
            status_flag = "warning_low_fiber_coverage"

        return {
            "status": status_flag,
            "method_version": "bundle_metrics_v1",
            "color": color_data,
            "texture": texture_data,
            "uniformity": uniformity_data,
            "image_quality": quality_data,
            "roi": {
                "bounds": [y1, y2, x1, x2],
                "fiber_coverage_pct": round(coverage_pct, 1),
            },
        }

    except Exception as e:
        logger.error(f"Visual metrics extraction failed gracefully: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "method_version": "bundle_metrics_v1",
            "color": None,
            "texture": None,
            "uniformity": None,
            "image_quality": None,
        }

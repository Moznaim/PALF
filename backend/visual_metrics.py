"""
backend/visual_metrics.py

PALF-Vision AI: Color and Bundle Texture Measurement Module (Version 2)
=======================================================================
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
# Normalized coordinates (0.0 to 1.0) targeting the inner fiber bundle area
DEFAULT_ROI_YMIN = float(os.getenv("PALF_ROI_YMIN", "0.20"))
DEFAULT_ROI_YMAX = float(os.getenv("PALF_ROI_YMAX", "0.80"))
DEFAULT_ROI_XMIN = float(os.getenv("PALF_ROI_XMIN", "0.15"))
DEFAULT_ROI_XMAX = float(os.getenv("PALF_ROI_XMAX", "0.85"))

# GLCM default parameters
DEFAULT_GLCM_LEVELS = int(os.getenv("PALF_GLCM_LEVELS", "16"))
DEFAULT_GLCM_DISTANCE = int(os.getenv("PALF_GLCM_DISTANCE", "1"))
DEFAULT_GLCM_DIRECTIONS = [0, 45, 90, 135]

# Regional Quality Control constants
MIN_REGION_COVERAGE = 0.40       # Provisional quality screening rule
MIN_PIXELS_PER_REGION = 1000     # Minimum included valid pixels per grid region


# ==============================================================================
# 1. ROI EXTRACTION & FIBER MASKING
# ==============================================================================

def validate_roi_bounds(
    ymin: float,
    ymax: float,
    xmin: float,
    xmax: float,
) -> Tuple[float, float, float, float]:
    """
    Validates normalized ROI coordinates (0.0 to 1.0).
    Ensures 0 <= ymin < ymax <= 1 and 0 <= xmin < xmax <= 1.
    Falls back to safe inner bundle bounds if coordinates are invalid.
    """
    try:
        ymin = float(ymin)
        ymax = float(ymax)
        xmin = float(xmin)
        xmax = float(xmax)
    except (TypeError, ValueError):
        logger.warning("Invalid non-numeric ROI bounds provided; falling back to defaults.")
        return DEFAULT_ROI_YMIN, DEFAULT_ROI_YMAX, DEFAULT_ROI_XMIN, DEFAULT_ROI_XMAX

    if not (0.0 <= ymin < ymax <= 1.0 and 0.0 <= xmin < xmax <= 1.0):
        logger.warning(
            f"ROI bounds out of range: y=[{ymin}, {ymax}], x=[{xmin}, {xmax}]. Falling back to defaults."
        )
        ymin = max(0.0, min(ymin, 0.95))
        ymax = max(ymin + 0.05, min(ymax, 1.0))
        xmin = max(0.0, min(xmin, 0.95))
        xmax = max(xmin + 0.05, min(xmax, 1.0))

    return ymin, ymax, xmin, xmax


def extract_fiber_roi(
    image: Any,
    ymin: float = DEFAULT_ROI_YMIN,
    ymax: float = DEFAULT_ROI_YMAX,
    xmin: float = DEFAULT_ROI_XMIN,
    xmax: float = DEFAULT_ROI_XMAX,
) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """
    Extracts the rectangular ROI covering the inner PALF fiber bundle.
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
    if h < 32 or w < 32:
        raise ValueError(f"Source image too small ({w}x{h}); minimum 32x32 required.")

    ymin, ymax, xmin, xmax = validate_roi_bounds(ymin, ymax, xmin, xmax)

    y1 = int(round(h * ymin))
    y2 = int(round(h * ymax))
    x1 = int(round(w * xmin))
    x2 = int(round(w * xmax))

    # Clamp safely
    y1 = max(0, min(y1, h - 1))
    y2 = max(y1 + 1, min(y2, h))
    x1 = max(0, min(x1, w - 1))
    x2 = max(x1 + 1, min(x2, w))

    roi_h = y2 - y1
    roi_w = x2 - x1

    if roi_h < 32 or roi_w < 32:
        raise ValueError(
            f"Extracted ROI dimensions ({roi_w}x{roi_h}) are insufficient for measurement; minimum 32x32 required."
        )

    roi = rgb_arr[y1:y2, x1:x2].copy()
    return roi, (y1, y2, x1, x2)


def extract_fiber_mask(roi_rgb: np.ndarray) -> np.ndarray:
    """
    Segments the PALF fiber bundle (off-white/cream/light-tan) from
    the dark blue/black background and holder frame.
    Returns boolean 2D mask of shape (H, W) where True = valid fiber pixel.
    """
    h, w, _ = roi_rgb.shape

    # 1. Calculate grayscale intensity and HSV color space
    if HAS_CV2:
        gray = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2HSV)

        # 2. Identify blue background using notebook HSV configuration:
        # Hue: 85-140, Saturation: >= 45, Value: >= 25
        is_blue_bg = (
            (hsv[:, :, 0] >= 85) &
            (hsv[:, :, 0] <= 140) &
            (hsv[:, :, 1] >= 45) &
            (hsv[:, :, 2] >= 25)
        )

        # Exclude blue background and pitch-black frame/holder edges (gray <= 20)
        mask = (~is_blue_bg) & (gray > 20)

        # Morphological clean-up: close narrow bundle gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask_uint8 = (mask.astype(np.uint8)) * 255
        mask_clean = cv2.morphologyEx(mask_uint8, cv2.MORPH_CLOSE, kernel)
        fiber_mask = mask_clean > 0
    else:
        r = roi_rgb[:, :, 0].astype(np.int32)
        g = roi_rgb[:, :, 1].astype(np.int32)
        b = roi_rgb[:, :, 2].astype(np.int32)
        is_blue_bg = (b > r + 30) & (b > g + 15) & (b > 60)
        gray = (
            0.299 * roi_rgb[:, :, 0] +
            0.587 * roi_rgb[:, :, 1] +
            0.114 * roi_rgb[:, :, 2]
        ).astype(np.uint8)
        fiber_mask = (~is_blue_bg) & (gray > 20)

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
    mask_lin = rgb_f > 0.04045
    rgb_lin = np.empty_like(rgb_f)
    rgb_lin[mask_lin] = ((rgb_f[mask_lin] + 0.055) / 1.055) ** 2.4
    rgb_lin[~mask_lin] = rgb_f[~mask_lin] / 12.92

    # Linear RGB to CIE XYZ (sRGB D65 matrix)
    x = rgb_lin[:, :, 0] * 0.4124564 + rgb_lin[:, :, 1] * 0.3575761 + rgb_lin[:, :, 2] * 0.1804375
    y = rgb_lin[:, :, 0] * 0.2126729 + rgb_lin[:, :, 1] * 0.7151522 + rgb_lin[:, :, 2] * 0.0721750
    z = rgb_lin[:, :, 0] * 0.0193339 + rgb_lin[:, :, 1] * 0.1191920 + rgb_lin[:, :, 2] * 0.9503041

    # D65 reference white
    xn, yn, zn = 0.95047, 1.00000, 1.08883
    xr, yr, zr = x / xn, y / yn, z / zn

    eps = (6.0 / 29.0) ** 3
    kappa = (29.0 / 6.0) ** 2 / 3.0
    delta = 4.0 / 29.0

    fx = np.where(xr > eps, xr ** (1.0 / 3.0), kappa * xr + delta)
    fy = np.where(yr > eps, yr ** (1.0 / 3.0), kappa * yr + delta)
    fz = np.where(zr > eps, zr ** (1.0 / 3.0), kappa * zr + delta)

    L = 116.0 * fy - 16.0
    A = 500.0 * (fx - fy)
    B = 200.0 * (fy - fz)

    return np.stack([L, A, B], axis=-1)


def cielab_to_hex(l_val: float, a_val: float, b_val: float) -> Optional[str]:
    """
    Computes a representative sRGB hex color (#RRGGBB) from CIELAB coordinates
    using standard CIELAB -> XYZ -> sRGB conversion.
    """
    if l_val is None or a_val is None or b_val is None:
        return None
    try:
        lab_pixel = np.array([[[float(l_val), float(a_val), float(b_val)]]], dtype=np.float32)
        if HAS_CV2:
            rgb_f = cv2.cvtColor(lab_pixel, cv2.COLOR_Lab2RGB)[0, 0]
        else:
            # Fallback: CIELAB -> XYZ -> Linear sRGB -> Gamma corrected sRGB
            fy = (l_val + 16.0) / 116.0
            fx = a_val / 500.0 + fy
            fz = fy - b_val / 200.0

            delta = 6.0 / 29.0
            xr = fx**3 if fx > delta else (fx - 4.0 / 29.0) * (3.0 * delta**2)
            yr = fy**3 if fy > delta else (fy - 4.0 / 29.0) * (3.0 * delta**2)
            zr = fz**3 if fz > delta else (fz - 4.0 / 29.0) * (3.0 * delta**2)

            xn, yn, zn = 0.95047, 1.00000, 1.08883
            x, y, z = xr * xn, yr * yn, zr * zn

            # XYZ to Linear sRGB
            r_l = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
            g_l = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
            b_l = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z

            # Gamma companding
            def gamma(v):
                v_cl = max(0.0, v)
                return 1.055 * (v_cl ** (1.0 / 2.4)) - 0.055 if v_cl > 0.0031308 else 12.92 * v_cl

            rgb_f = np.array([gamma(r_l), gamma(g_l), gamma(b_l)])

        rgb_8u = np.clip(np.round(rgb_f * 255.0), 0, 255).astype(np.uint8)
        return f"#{rgb_8u[0]:02x}{rgb_8u[1]:02x}{rgb_8u[2]:02x}"
    except Exception:
        return "#e0d8cc"


def extract_color_metrics(roi_rgb: np.ndarray, mask: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """
    Extracts mean and standard deviation of CIELAB color components (L*, a*, b*),
    mean pixel chroma, and a representative display hex swatch.

    Safety: If an explicitly supplied mask contains 0 valid pixels, returns None
    for color stats rather than calculating color on background/holder pixels.
    """
    if mask is not None:
        valid_pixel_count = int(mask.sum())
        if valid_pixel_count == 0:
            logger.warning("Empty mask provided to extract_color_metrics; returning unavailable values.")
            return {
                "color_space": "CIELAB",
                "l_star": None,
                "a_star": None,
                "b_star": None,
                "mean_L_star": None,
                "mean_a_star": None,
                "mean_b_star": None,
                "l_star_std": None,
                "a_star_std": None,
                "b_star_std": None,
                "chroma": None,
                "mean_chroma": None,
                "hex_color": None,
                "valid_pixels": 0,
                "status": "error_empty_mask",
                "calibration_status": "Camera-derived CIELAB measurements - calibration pending",
            }

    lab = rgb_to_cielab(roi_rgb)
    L = lab[:, :, 0]
    A = lab[:, :, 1]
    B = lab[:, :, 2]

    if mask is not None:
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

    # Mean pixel chroma: (1/N) * sum(sqrt(a*^2 + b*^2))
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
        "valid_pixels": int(len(valid_l)),
        "status": "ok",
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
    - ASM:         sum(P(i,j)^2)  (Angular Second Moment)
    - Energy:      sqrt(ASM)      (Standard Haralick Energy)
    - Entropy:     -sum(P(i,j) * log2(P(i,j)))
    """
    if directions is None:
        directions = DEFAULT_GLCM_DIRECTIONS

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
    dir_asm = []
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

        cont = float((P_norm * diff_sq).sum())
        homog = float((P_norm / homog_denom).sum())
        asm_val = float((P_norm ** 2).sum())
        energy_val = float(np.sqrt(asm_val))

        nonzero = P_norm[P_norm > 0]
        ent = float(-(nonzero * np.log2(nonzero)).sum())

        dir_contrast.append(cont)
        dir_homogeneity.append(homog)
        dir_asm.append(asm_val)
        dir_energy.append(energy_val)
        dir_entropy.append(ent)

    if not dir_contrast:
        return {
            "method": "GLCM",
            "contrast": None,
            "homogeneity": None,
            "entropy": None,
            "asm": None,
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
        "asm": round(float(np.mean(dir_asm)), 4),
        "energy": round(float(np.mean(dir_energy)), 4),
        "directions": directions,
        "gray_levels": levels,
        "distance_pixels": distance,
    }


# ==============================================================================
# 3b. STRUCTURE TENSOR ORIENTATION FEATURES
# ==============================================================================

def calculate_structure_tensor_features(
    gray_img: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Computes structure tensor-based fiber orientation features for the whole
    bundle and per 3×3 regional grid.

    Features calculated:
    - Orientation concentration R ∈ [0, 1] (axial circular resultant length)
    - Orientation spread (degrees) via von Mises dispersion formula
    - Dominant strand orientation (degrees, 0-180°)
    - Mean coherence (local anisotropy from eigenvalue ratio of structure tensor)
    - Regional mean ± SD of the above across valid 3×3 grid cells

    Circular/axial math modulo 180° is used because fiber strands are undirected:
      θ and θ+180° are equivalent orientations.

    Formula for spread:
      spread_deg = 0.5 * sqrt(-2 * ln(max(R, 1e-6))) * (180 / π)

    This matches the threshold-study notebook's computation exactly.
    """
    if not HAS_CV2:
        return _empty_structure_tensor("OpenCV not available")

    try:
        h, w = gray_img.shape
        if mask is None:
            mask = np.ones((h, w), dtype=bool)

        if mask.sum() < MIN_PIXELS_PER_REGION:
            return _empty_structure_tensor("Insufficient mask pixels")

        gray_f = gray_img.astype(np.float64) / 255.0

        # Gradients via Sobel
        Ix = cv2.Sobel(gray_f, cv2.CV_64F, 1, 0, ksize=3)
        Iy = cv2.Sobel(gray_f, cv2.CV_64F, 0, 1, ksize=3)

        # Structure tensor components with Gaussian smoothing
        Jxx = cv2.GaussianBlur(Ix * Ix, (5, 5), 1.5)
        Jyy = cv2.GaussianBlur(Iy * Iy, (5, 5), 1.5)
        Jxy = cv2.GaussianBlur(Ix * Iy, (5, 5), 1.5)

        # Coherence per pixel
        denom = Jxx + Jyy + 1e-6
        coherence = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / denom

        # Local orientation angle (radians, [-π/2, π/2])
        theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy)

        # Whole-bundle statistics (masked pixels only)
        whole_stats = _axial_orientation_stats(theta, coherence, mask)

        # Regional 3×3 grid analysis
        n_rows, n_cols = 3, 3
        r_step = h // n_rows
        c_step = w // n_cols

        regional_concentrations: List[float] = []
        regional_spreads: List[float] = []
        regional_coherences: List[float] = []
        region_details: List[Dict[str, Any]] = []
        valid_region_count = 0

        for r in range(n_rows):
            for c in range(n_cols):
                y_start = r * r_step
                y_end = (r + 1) * r_step if r < n_rows - 1 else h
                x_start = c * c_step
                x_end = (c + 1) * c_step if c < n_cols - 1 else w

                sub_mask = mask[y_start:y_end, x_start:x_end]
                sub_theta = theta[y_start:y_end, x_start:x_end]
                sub_coh = coherence[y_start:y_end, x_start:x_end]

                valid_count = int(sub_mask.sum())
                total_count = int(sub_mask.size)
                coverage = float(valid_count / max(1, total_count))

                is_valid = (coverage >= MIN_REGION_COVERAGE) and (valid_count >= MIN_PIXELS_PER_REGION)

                if is_valid:
                    reg_stats = _axial_orientation_stats(sub_theta, sub_coh, sub_mask)
                    regional_concentrations.append(reg_stats["orientation_concentration"])
                    regional_spreads.append(reg_stats["orientation_spread_deg"])
                    regional_coherences.append(reg_stats["mean_coherence"])
                    valid_region_count += 1
                    region_details.append({
                        "region_id": f"R{r+1}C{c+1}",
                        "valid": True,
                        "coverage_pct": round(coverage * 100.0, 1),
                        "orientation_concentration": round(reg_stats["orientation_concentration"], 6),
                        "orientation_spread_deg": round(reg_stats["orientation_spread_deg"], 2),
                        "mean_coherence": round(reg_stats["mean_coherence"], 6),
                    })
                else:
                    region_details.append({
                        "region_id": f"R{r+1}C{c+1}",
                        "valid": False,
                        "coverage_pct": round(coverage * 100.0, 1),
                    })

        result = {
            "status": "available",
            "structure_tensor_mean_coherence": round(whole_stats["mean_coherence"], 6),
            "orientation_concentration": round(whole_stats["orientation_concentration"], 6),
            "dominant_strand_orientation_deg": round(whole_stats["dominant_angle_deg"], 2),
            "orientation_spread_deg": round(whole_stats["orientation_spread_deg"], 2),
            "valid_regions": valid_region_count,
        }

        if valid_region_count >= 1:
            result["orientation_concentration_regional_mean"] = round(float(np.mean(regional_concentrations)), 6)
            result["orientation_concentration_regional_sd"] = round(float(np.std(regional_concentrations)), 6) if valid_region_count > 1 else 0.0
            result["orientation_spread_deg_regional_mean"] = round(float(np.mean(regional_spreads)), 2)
            result["orientation_spread_deg_regional_sd"] = round(float(np.std(regional_spreads)), 2) if valid_region_count > 1 else 0.0
            result["structure_tensor_mean_coherence_regional_mean"] = round(float(np.mean(regional_coherences)), 6)
            result["structure_tensor_mean_coherence_regional_sd"] = round(float(np.std(regional_coherences)), 6) if valid_region_count > 1 else 0.0
        else:
            result["orientation_concentration_regional_mean"] = None
            result["orientation_concentration_regional_sd"] = None
            result["orientation_spread_deg_regional_mean"] = None
            result["orientation_spread_deg_regional_sd"] = None
            result["structure_tensor_mean_coherence_regional_mean"] = None
            result["structure_tensor_mean_coherence_regional_sd"] = None

        result["regions"] = region_details
        return result

    except Exception as e:
        logger.error(f"Structure tensor calculation error: {e}", exc_info=True)
        return _empty_structure_tensor(str(e))


def _axial_orientation_stats(
    theta: np.ndarray,
    coherence: np.ndarray,
    mask: np.ndarray,
) -> Dict[str, float]:
    """
    Computes axial circular orientation statistics for fiber orientations
    modulo 180°. Uses the 2θ trick for axial data.

    Returns orientation_concentration (R), orientation_spread_deg,
    dominant_angle_deg, and mean_coherence.
    """
    theta_m = theta[mask]
    coh_m = coherence[mask]

    # Double angle for axial data
    cos_2t = np.cos(2.0 * theta_m)
    sin_2t = np.sin(2.0 * theta_m)

    C = float(np.mean(cos_2t))
    S = float(np.mean(sin_2t))
    R = float(np.sqrt(C ** 2 + S ** 2))

    # Spread: von Mises circular standard deviation
    R_safe = max(R, 1e-6)
    spread_deg = float(0.5 * np.sqrt(-2.0 * np.log(R_safe)) * (180.0 / np.pi))

    # Dominant angle in [0, 180)
    dom_angle = float(0.5 * np.arctan2(S, C) * (180.0 / np.pi)) % 180.0

    mean_coh = float(np.mean(coh_m))

    return {
        "orientation_concentration": R,
        "orientation_spread_deg": spread_deg,
        "dominant_angle_deg": dom_angle,
        "mean_coherence": mean_coh,
    }


def _empty_structure_tensor(reason: str) -> Dict[str, Any]:
    """Returns a structured empty result for structure tensor analysis."""
    return {
        "status": "unavailable",
        "error": reason,
        "structure_tensor_mean_coherence": None,
        "orientation_concentration": None,
        "dominant_strand_orientation_deg": None,
        "orientation_spread_deg": None,
        "valid_regions": 0,
        "orientation_concentration_regional_mean": None,
        "orientation_concentration_regional_sd": None,
        "orientation_spread_deg_regional_mean": None,
        "orientation_spread_deg_regional_sd": None,
        "structure_tensor_mean_coherence_regional_mean": None,
        "structure_tensor_mean_coherence_regional_sd": None,
    }


# ==============================================================================
# 3c. GABOR FILTER BANK ANALYSIS
# ==============================================================================

def calculate_gabor_features(
    gray_img: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Applies a 6-orientation Gabor filter bank and computes mean response
    magnitude per filter across masked fiber pixels.

    Filter bank settings (matching the threshold-study notebook):
      ksize  = (15, 15)
      sigma  = 3.0
      lambd  = 6.0
      gamma  = 0.5
      psi    = 0.0
      angles = [0°, 30°, 60°, 90°, 120°, 150°]

    Features:
    - gabor_response_anisotropy: (Rmax - Rmin) / (Rmax + Rmin + ε)
    - gabor_mean_response: mean over all orientations
    - gabor_dominant_filter_angle_deg: angle with highest mean response
    - Per-angle responses: gabor_response_0deg ... gabor_response_150deg
    """
    if not HAS_CV2:
        return _empty_gabor("OpenCV not available")

    try:
        h, w = gray_img.shape
        if mask is None:
            mask = np.ones((h, w), dtype=bool)

        if mask.sum() < MIN_PIXELS_PER_REGION:
            return _empty_gabor("Insufficient mask pixels")

        gray_f = gray_img.astype(np.float64) / 255.0

        angles_deg = [0, 30, 60, 90, 120, 150]
        ksize = (15, 15)
        sigma = 3.0
        lambd = 6.0
        gamma = 0.5
        psi = 0.0

        responses = {}

        for angle in angles_deg:
            theta_rad = angle * np.pi / 180.0
            kernel = cv2.getGaborKernel(ksize, sigma, theta_rad, lambd, gamma, psi, ktype=cv2.CV_64F)
            filtered = cv2.filter2D(gray_f, cv2.CV_64F, kernel)
            mean_resp = float(np.mean(np.abs(filtered[mask])))
            responses[angle] = mean_resp

        resp_values = list(responses.values())
        r_max = max(resp_values)
        r_min = min(resp_values)
        anisotropy = float((r_max - r_min) / (r_max + r_min + 1e-6))
        mean_response = float(np.mean(resp_values))
        dominant_angle = max(responses, key=responses.get)

        return {
            "status": "available",
            "gabor_response_anisotropy": round(anisotropy, 6),
            "gabor_mean_response": round(mean_response, 6),
            "gabor_dominant_filter_angle_deg": dominant_angle,
            "gabor_response_0deg": round(responses[0], 6),
            "gabor_response_30deg": round(responses[30], 6),
            "gabor_response_60deg": round(responses[60], 6),
            "gabor_response_90deg": round(responses[90], 6),
            "gabor_response_120deg": round(responses[120], 6),
            "gabor_response_150deg": round(responses[150], 6),
            "filter_params": {
                "ksize": list(ksize),
                "sigma": sigma,
                "lambd": lambd,
                "gamma": gamma,
                "psi": psi,
                "angles_deg": angles_deg,
            },
        }

    except Exception as e:
        logger.error(f"Gabor filter calculation error: {e}", exc_info=True)
        return _empty_gabor(str(e))


def _empty_gabor(reason: str) -> Dict[str, Any]:
    """Returns a structured empty result for Gabor analysis."""
    return {
        "status": "unavailable",
        "error": reason,
        "gabor_response_anisotropy": None,
        "gabor_mean_response": None,
        "gabor_dominant_filter_angle_deg": None,
        "gabor_response_0deg": None,
        "gabor_response_30deg": None,
        "gabor_response_60deg": None,
        "gabor_response_90deg": None,
        "gabor_response_120deg": None,
        "gabor_response_150deg": None,
    }


# ==============================================================================
# 3d. EDGE DENSITY & GRADIENT MAGNITUDE (Supporting Features)
# ==============================================================================

def calculate_edge_gradient_features(
    gray_img: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Computes edge density percentage and mean gradient magnitude over
    masked fiber pixels. These are supporting features available for
    the texture characterization but not used in primary threshold rules.
    """
    if not HAS_CV2:
        return {"edge_density_pct": None, "mean_gradient_magnitude": None, "status": "unavailable"}

    try:
        h, w = gray_img.shape
        if mask is None:
            mask = np.ones((h, w), dtype=bool)

        if mask.sum() < 100:
            return {"edge_density_pct": None, "mean_gradient_magnitude": None, "status": "insufficient_mask"}

        gray_f = gray_img.astype(np.float64) / 255.0

        # Gradient magnitude (Sobel)
        Ix = cv2.Sobel(gray_f, cv2.CV_64F, 1, 0, ksize=3)
        Iy = cv2.Sobel(gray_f, cv2.CV_64F, 0, 1, ksize=3)
        grad_mag = np.sqrt(Ix ** 2 + Iy ** 2)

        masked_grad = grad_mag[mask]
        mean_grad = float(np.mean(masked_grad))

        # Edge density via Canny on uint8, counting edge pixels in mask
        edges = cv2.Canny(gray_img, 50, 150)
        edge_pixels = int(np.sum((edges > 0) & mask))
        total_mask_pixels = int(mask.sum())
        edge_density = float(edge_pixels / max(1, total_mask_pixels) * 100.0)

        return {
            "edge_density_pct": round(edge_density, 4),
            "mean_gradient_magnitude": round(mean_grad, 6),
            "status": "available",
        }

    except Exception as e:
        logger.warning(f"Edge/gradient calculation error: {e}")
        return {"edge_density_pct": None, "mean_gradient_magnitude": None, "status": "error"}


# ==============================================================================
# 4. BUNDLE UNIFORMITY (3x3 Regional Grid Analysis)
# ==============================================================================

def calculate_bundle_uniformity(
    gray_img: np.ndarray,
    mask: Optional[np.ndarray] = None,
    grid: Tuple[int, int] = (3, 3),
    levels: int = DEFAULT_GLCM_LEVELS,
    distance: int = DEFAULT_GLCM_DISTANCE,
    directions: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Subdivides the PALF fiber bundle ROI into a 3x3 grid (9 regions) to quantify
    spatial variation in contrast and homogeneity across the bundle.

    Synchronized with whole-bundle GLCM parameters (distance and directions).
    Applies regional quality screening rule:
      valid_region = (coverage >= 0.40) and (included_pixels >= 1000)
    """
    if directions is None:
        directions = DEFAULT_GLCM_DIRECTIONS

    h, w = gray_img.shape
    if mask is None:
        mask = np.ones((h, w), dtype=bool)

    n_rows, n_cols = grid
    r_step = h // n_rows
    c_step = w // n_cols

    regional_contrasts: List[float] = []
    regional_homogeneities: List[float] = []
    region_diagnostics: List[Dict[str, Any]] = []

    for r in range(n_rows):
        for c in range(n_cols):
            y_start = r * r_step
            y_end = (r + 1) * r_step if r < n_rows - 1 else h
            x_start = c * c_step
            x_end = (c + 1) * c_step if c < n_cols - 1 else w

            sub_gray = gray_img[y_start:y_end, x_start:x_end]
            sub_mask = mask[y_start:y_end, x_start:x_end]

            valid_count = int(sub_mask.sum())
            total_count = int(sub_mask.size)
            coverage = float(valid_count / max(1, total_count))

            # Quality screening rule
            is_valid = (coverage >= MIN_REGION_COVERAGE) and (valid_count >= MIN_PIXELS_PER_REGION)

            feats = calculate_glcm_features(
                sub_gray,
                mask=sub_mask if valid_count > 0 else None,
                levels=levels,
                distance=distance,
                directions=directions,
            ) if valid_count >= 50 else {
                "contrast": None, "homogeneity": None, "asm": None, "energy": None
            }

            diag_item = {
                "region_id": f"R{r+1}C{c+1}",
                "grid_row": r + 1,
                "grid_col": c + 1,
                "included_pixels": valid_count,
                "total_pixels": total_count,
                "coverage_pct": round(coverage * 100.0, 1),
                "valid": is_valid,
                "contrast": feats.get("contrast"),
                "homogeneity": feats.get("homogeneity"),
            }
            region_diagnostics.append(diag_item)

            if is_valid and feats.get("contrast") is not None and feats.get("homogeneity") is not None:
                regional_contrasts.append(feats["contrast"])
                regional_homogeneities.append(feats["homogeneity"])

    valid_regions_count = len(regional_contrasts)

    if valid_regions_count == 0:
        return {
            "grid": list(grid),
            "valid_regions": 0,
            "total_regions": n_rows * n_cols,
            "contrast_mean": None,
            "contrast_std": None,
            "homogeneity_mean": None,
            "homogeneity_std": None,
            "regions": region_diagnostics,
        }

    c_mean = float(np.mean(regional_contrasts))
    c_std = float(np.std(regional_contrasts)) if valid_regions_count > 1 else 0.0
    h_mean = float(np.mean(regional_homogeneities))
    h_std = float(np.std(regional_homogeneities)) if valid_regions_count > 1 else 0.0

    return {
        "grid": list(grid),
        "valid_regions": valid_regions_count,
        "total_regions": n_rows * n_cols,
        "contrast_mean": round(c_mean, 4),
        "contrast_std": round(c_std, 4),
        "homogeneity_mean": round(h_mean, 4),
        "homogeneity_std": round(h_std, 4),
        "regions": region_diagnostics,
    }


# ==============================================================================
# 5. IMAGE QUALITY CHECK (Masked Laplacian Variance Focus Metric)
# ==============================================================================

def calculate_image_quality(
    gray_img: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Computes Laplacian variance as an image sharpness indicator.
    Calculates variance strictly across valid fiber pixels.
    Erodes the mask to eliminate high-contrast boundary edge artifacts.
    Note: Indicates focus/blur only; not a measure of physical fiber roughness.
    Status remains 'unvalidated' pending camera focus testing.
    """
    try:
        h, w = gray_img.shape
        if HAS_CV2:
            lap = cv2.Laplacian(gray_img, cv2.CV_64F)
        else:
            g_f = gray_img.astype(np.float64)
            lap = np.zeros_like(g_f)
            lap[1:h-1, 1:w-1] = (
                g_f[0:h-2, 1:w-1] +
                g_f[2:h,   1:w-1] +
                g_f[1:h-1, 0:w-2] +
                g_f[1:h-1, 2:w]   -
                4.0 * g_f[1:h-1, 1:w-1]
            )

        if mask is not None and mask.sum() > 0:
            if HAS_CV2:
                # Erode 3x3 to avoid bundle-boundary edge discontinuity inflating variance
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                eroded_mask = cv2.erode(mask.astype(np.uint8), kernel) > 0
            else:
                eroded_mask = mask[1:h-1, 1:w-1]

            if eroded_mask.sum() >= 50:
                lap_pixels = lap[eroded_mask] if eroded_mask.shape == lap.shape else lap[1:h-1, 1:w-1][eroded_mask]
            else:
                lap_pixels = lap[mask]

            lap_var = float(np.var(lap_pixels))
        else:
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

        if h_roi < 32 or w_roi < 32:
            return {
                "status": "error",
                "error": f"Extracted ROI dimensions ({w_roi}x{h_roi}) are too small (minimum 32x32 required)",
                "method_version": "bundle_metrics_v3",
                "color": None,
                "texture": None,
                "uniformity": None,
                "image_quality": None,
                "structure_tensor": None,
                "gabor": None,
                "edge_gradient": None,
            }

        # 2. Extract Fiber Mask
        fiber_mask = extract_fiber_mask(roi_rgb)
        included_pixels = int(fiber_mask.sum())
        total_pixels = int(fiber_mask.size)
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

        # Validate dimensions
        assert gray_roi.shape == fiber_mask.shape, "Grayscale image and mask dimensions must match."

        # Mask quality checks
        warnings: List[str] = []
        if included_pixels == 0:
            warnings.append("Fiber mask is empty; no valid bundle pixels detected.")
        elif coverage_pct < 5.0:
            warnings.append("Low fiber coverage (< 5% of ROI); segmentation may be unreliable.")
        elif coverage_pct > 95.0:
            warnings.append("Excessive foreground coverage (> 95% of ROI); check background exclusion.")

        # 4. Color Measurements (CIELAB)
        color_data = extract_color_metrics(roi_rgb, mask=fiber_mask)

        # 5. Texture Measurements (GLCM)
        texture_data = calculate_glcm_features(
            gray_roi,
            mask=fiber_mask,
            levels=DEFAULT_GLCM_LEVELS,
            distance=DEFAULT_GLCM_DISTANCE,
            directions=DEFAULT_GLCM_DIRECTIONS,
        )

        # 6. Bundle Uniformity (3x3 grid, synchronized GLCM distance/directions)
        uniformity_data = calculate_bundle_uniformity(
            gray_roi,
            mask=fiber_mask,
            grid=(3, 3),
            levels=DEFAULT_GLCM_LEVELS,
            distance=DEFAULT_GLCM_DISTANCE,
            directions=DEFAULT_GLCM_DIRECTIONS,
        )

        # 7. Image Quality Check (Masked Laplacian Variance)
        quality_data = calculate_image_quality(gray_roi, mask=fiber_mask)

        # 8. Structure Tensor Orientation Features
        structure_tensor_data = calculate_structure_tensor_features(
            gray_roi, mask=fiber_mask,
        )

        # 9. Gabor Filter Bank Analysis
        gabor_data = calculate_gabor_features(
            gray_roi, mask=fiber_mask,
        )

        # 10. Edge Density & Gradient Magnitude (supporting features)
        edge_gradient_data = calculate_edge_gradient_features(
            gray_roi, mask=fiber_mask,
        )

        status_flag = "ok"
        if included_pixels == 0:
            status_flag = "error_empty_mask"
        elif coverage_pct < 5.0:
            status_flag = "warning_low_fiber_coverage"
        elif coverage_pct > 95.0:
            status_flag = "warning_excessive_foreground_coverage"

        return {
            "status": status_flag,
            "method_version": "bundle_metrics_v3",
            "color": color_data,
            "texture": texture_data,
            "uniformity": uniformity_data,
            "image_quality": quality_data,
            "structure_tensor": structure_tensor_data,
            "gabor": gabor_data,
            "edge_gradient": edge_gradient_data,
            "metadata": {
                "roi_bounds": [y1, y2, x1, x2],
                "roi_width": w_roi,
                "roi_height": h_roi,
                "glcm_levels": DEFAULT_GLCM_LEVELS,
                "pixel_distance": DEFAULT_GLCM_DISTANCE,
                "directions": DEFAULT_GLCM_DIRECTIONS,
                "symmetric_glcm": True,
                "regional_grid": [3, 3],
                "included_pixels": included_pixels,
                "roi_pixels": total_pixels,
                "mask_coverage_pct": round(coverage_pct, 1),
            },
            "warnings": warnings,
        }

    except Exception as e:
        logger.error(f"Visual metrics extraction failed gracefully: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "method_version": "bundle_metrics_v3",
            "color": None,
            "texture": None,
            "uniformity": None,
            "image_quality": None,
            "structure_tensor": None,
            "gabor": None,
            "edge_gradient": None,
        }

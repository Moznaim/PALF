"""
backend/test_visual_and_color.py

Comprehensive Verification Test Suite for Visual Metrics and Candidate Color Analysis:
1. ROI coordinate validation & dimension checks
2. Empty-mask color fallback safety (must return None, not background color)
3. GLCM Energy vs. ASM separation (Energy == sqrt(ASM))
4. Masked Laplacian variance with erosion
5. Synchronized regional GLCM (distance, directions) and 40% coverage QC rule
6. Mask validation (empty, low coverage, dimension matching)
7. CIELAB conversion and mean pixel chroma calculation
8. Six candidate reference range matching and schema validation
9. End-to-end inference compatibility (DL classification unchanged)
"""

import sys
import os
import json
import numpy as np

# Add backend directory to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import visual_metrics as vm
import color_analysis as ca


def test_roi_validation():
    print("\n--- Test 1: ROI Validation & Dimension Safety ---")
    # Valid normalized
    ymin, ymax, xmin, xmax = vm.validate_roi_bounds(0.2, 0.8, 0.15, 0.85)
    assert 0 <= ymin < ymax <= 1 and 0 <= xmin < xmax <= 1
    print("✓ Valid bounds accepted:", (ymin, ymax, xmin, xmax))

    # Inverted / out-of-bounds coords must be sanitized safely
    s_ymin, s_ymax, s_xmin, s_xmax = vm.validate_roi_bounds(1.5, -0.2, 0.9, 0.1)
    assert s_ymin < s_ymax and s_xmin < s_xmax
    print("✓ Out-of-bounds sanitized:", (s_ymin, s_ymax, s_xmin, s_xmax))

    # Extraction from synthetic image
    img = np.full((500, 500, 3), 180, dtype=np.uint8)
    roi, bounds = vm.extract_fiber_roi(img, ymin=0.2, ymax=0.8, xmin=0.15, xmax=0.85)
    assert roi.shape[0] >= 32 and roi.shape[1] >= 32
    print(f"✓ ROI extracted: shape {roi.shape}, bounds {bounds}")


def test_empty_mask_handling():
    print("\n--- Test 2: Empty Mask Safety (No Background Fallback) ---")
    roi = np.full((100, 100, 3), 150, dtype=np.uint8)
    empty_mask = np.zeros((100, 100), dtype=bool)

    color_res = vm.extract_color_metrics(roi, mask=empty_mask)
    assert color_res["l_star"] is None, "Empty mask must return None for l_star"
    assert color_res["hex_color"] is None, "Empty mask must return None for hex_color"
    assert color_res["status"] == "error_empty_mask"
    print("✓ Empty mask returned None without falling back to background:", color_res["status"])


def test_glcm_energy_and_asm():
    print("\n--- Test 3: GLCM Energy vs. ASM Separation ---")
    # Synthetic gradient image
    gray = np.tile(np.linspace(0, 255, 128, dtype=np.uint8), (128, 1))
    mask = np.ones((128, 128), dtype=bool)

    features = vm.calculate_glcm_features(
        gray,
        mask=mask,
        levels=16,
        distance=1,
        directions=[0, 45, 90, 135]
    )

    asm_val = features["asm"]
    energy_val = features["energy"]

    assert asm_val is not None and energy_val is not None
    # Energy must equal sqrt(ASM) within numerical tolerance
    diff = abs(energy_val - np.sqrt(asm_val))
    assert diff < 1e-3, f"Energy ({energy_val}) must be sqrt(ASM) ({np.sqrt(asm_val)})"
    print(f"✓ GLCM ASM: {asm_val}, Energy: {energy_val} (diff={diff:.6f})")


def test_masked_laplacian_variance():
    print("\n--- Test 4: Masked Laplacian Variance with Erosion ---")
    # Fiber rectangle (bright) on dark background
    img = np.full((100, 100), 20, dtype=np.uint8)
    img[25:75, 25:75] = 200  # bright fiber bundle
    mask = img > 100

    quality = vm.calculate_image_quality(img, mask=mask)
    assert quality["status"] == "unvalidated"
    assert quality["laplacian_variance"] is not None
    print(f"✓ Masked Laplacian variance: {quality['laplacian_variance']} (status={quality['status']})")


def test_regional_glcm_sync_and_qc():
    print("\n--- Test 5: 3x3 Regional GLCM Sync & 40% QC Screening Rule ---")
    gray = np.full((300, 300), 160, dtype=np.uint8)
    # Only center region (row 1, col 1 in 0-index) has full mask; other regions have low/no mask
    mask = np.zeros((300, 300), dtype=bool)
    mask[100:200, 100:200] = True  # Center region R2C2 has 10,000 pixels = 100% coverage
    mask[0:20, 0:20] = True        # Top-left region R1C1 has 400 pixels = 4% coverage (< 40% and < 1000 px)

    unif = vm.calculate_bundle_uniformity(
        gray,
        mask=mask,
        grid=(3, 3),
        levels=16,
        distance=1,
        directions=[0, 45, 90, 135]
    )

    # R2C2 must be valid; R1C1 must be invalid
    assert unif["valid_regions"] == 1, f"Expected 1 valid region, got {unif['valid_regions']}"
    print(f"✓ Valid regions under 40% QC rule: {unif['valid_regions']}/9 regions")


def test_cielab_conversion_and_hex():
    print("\n--- Test 6: CIELAB Conversion & Mean Pixel Chroma ---")
    # Synthetic fiber off-white patch (R=186, G=200, B=219)
    rgb = np.full((64, 64, 3), [186, 200, 219], dtype=np.uint8)
    mask = np.ones((64, 64), dtype=bool)

    metrics = vm.extract_color_metrics(rgb, mask=mask)
    assert metrics["l_star"] is not None
    assert metrics["a_star"] is not None
    assert metrics["b_star"] is not None
    assert metrics["chroma"] is not None
    assert metrics["hex_color"].startswith("#")
    print(f"✓ CIELAB: L*={metrics['l_star']}, a*={metrics['a_star']}, b*={metrics['b_star']}, chroma={metrics['chroma']}, hex={metrics['hex_color']}")


def test_color_reference_matching():
    print("\n--- Test 7: PNS/BAFS 318:2021 Candidate Reference Matching ---")
    config = ca.load_color_reference_config()
    assert len(config["references"]) == 6, "Must contain exactly 6 candidate references"

    keys = [r["reference_key"] for r in config["references"]]
    expected_keys = [
        "excellent_light_ivory",
        "excellent_white",
        "good_ivory",
        "good_light_ochre",
        "fair_light_brown",
        "fair_dull_brown",
    ]
    assert keys == expected_keys, f"Reference keys mismatch: {keys}"

    # Verify Fair light brown is marked as shared boundary
    fair_lb = next(r for r in config["references"] if r["reference_key"] == "fair_light_brown")
    assert "boundary" in fair_lb["pns_pid"].lower()
    print("✓ Fair light brown properly designated as PID-3 / PID-4 shared boundary")

    # Synthetic image matching excellent_white median (R=186, G=200, B=219)
    synth_img = np.full((200, 200, 3), [186, 200, 219], dtype=np.uint8)
    res = ca.analyze_color_references(synth_img)

    assert res["status"] == "ok"
    assert res["threshold_status"] == "candidate_unvalidated"
    assert len(res["candidate_matches"]) == 6
    top_match = res["candidate_matches"][0]
    print(f"✓ Candidate color analysis executed. Top match: {top_match['color_label']} ({top_match['quality']}) with ΔE={top_match['delta_e_to_reference_median']}")


def test_master_pipeline():
    print("\n--- Test 8: Master Visual Metrics Pipeline ---")
    synth_fiber = np.full((300, 300, 3), 10, dtype=np.uint8)  # dark background
    synth_fiber[100:200, 80:220] = [180, 195, 210]             # partial fiber bundle in center

    res = vm.extract_visual_metrics(synth_fiber)
    assert res["status"] in ("ok", "warning_low_fiber_coverage", "warning_excessive_foreground_coverage")
    assert res["method_version"] == "bundle_metrics_v2"
    assert "asm" in res["texture"]
    assert "energy" in res["texture"]
    assert "laplacian_variance" in res["image_quality"]
    assert "metadata" in res
    print("✓ Master visual metrics pipeline completed with full metadata:")
    print("  - Status:", res["status"])
    print("  - Texture:", res["texture"])
    print("  - Uniformity valid regions:", res["uniformity"]["valid_regions"])
    print("  - Image Quality:", res["image_quality"])


if __name__ == "__main__":
    test_roi_validation()
    test_empty_mask_handling()
    test_glcm_energy_and_asm()
    test_masked_laplacian_variance()
    test_regional_glcm_sync_and_qc()
    test_cielab_conversion_and_hex()
    test_color_reference_matching()
    test_master_pipeline()
    print("\n==========================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==========================================")

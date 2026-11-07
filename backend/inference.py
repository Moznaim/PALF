import io
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional

import torch
import torch.nn.functional as F

import numpy as np
from visual_metrics import extract_visual_metrics
from color_analysis import analyze_color_references
from texture_thresholds import evaluate_texture_thresholds

from PIL import Image, UnidentifiedImageError
from torchvision import transforms

from inference_models import build_model

logger = logging.getLogger("palf_inference")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Limit PyTorch CPU threads on embedded devices (Raspberry Pi 4) to prevent OpenMP contention crashes
if DEVICE.type == "cpu":
    try:
        torch.set_num_threads(int(os.getenv("TORCH_NUM_THREADS", "2")))
    except Exception:
        pass


class PadToSquare:
    """
    Pads a PIL image to a square canvas using a solid fill colour before resizing.
    Matches the training preprocessing used for the new PALF dataset (pad_fill=(124,116,104)).
    """
    def __init__(self, fill: tuple = (124, 116, 104)):
        self.fill = fill

    def __call__(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        if w == h:
            return img
        side = max(w, h)
        canvas = Image.new("RGB", (side, side), self.fill)
        canvas.paste(img, ((side - w) // 2, (side - h) // 2))
        return canvas


def build_image_transform(
    img_size: int = 224,
    preserve_aspect: bool = False,
    pad_to_square: bool = False,
    pad_fill: tuple = (124, 116, 104),
):
    """
    Builds RGB preprocessing transform.

    pad_to_square=True  – first pads the image to a square canvas (fill=pad_fill)
                          then resizes to img_size×img_size. Matches the new PALF dataset
                          training pipeline (pipeline_metadata.json: "pad_to_square": true).
    preserve_aspect     – legacy centre-crop mode (mutually exclusive with pad_to_square).
    Default             – direct resize to img_size×img_size (original ResNet training pipeline).
    """
    steps = []
    if pad_to_square:
        steps.append(PadToSquare(fill=pad_fill))
        steps.append(transforms.Resize((img_size, img_size), interpolation=transforms.InterpolationMode.BILINEAR))
    elif preserve_aspect:
        steps.append(transforms.Resize(img_size, interpolation=transforms.InterpolationMode.BILINEAR))
        steps.append(transforms.CenterCrop((img_size, img_size)))
    else:
        steps.append(transforms.Resize((img_size, img_size), interpolation=transforms.InterpolationMode.BILINEAR))

    steps += [
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ]
    return transforms.Compose(steps)

# Global in-memory cache for loaded model, metadata, and transform
_LOADED_MODEL = None
_LOADED_METADATA: Dict[str, Any] = {}
_ACTIVE_TRANSFORM = build_image_transform(224, preserve_aspect=False)


def load_model_checkpoint(checkpoint_path: str) -> Tuple[torch.nn.Module, Dict[str, Any]]:
    """
    Loads model checkpoint, reads metadata, instantiates exact architecture,
    loads weights, sets eval mode, and moves model to configured device.
    """
    global _LOADED_MODEL, _LOADED_METADATA, _ACTIVE_TRANSFORM

    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Checkpoint file not found at: {checkpoint_path}")

    logger.info(f"Loading checkpoint from {checkpoint_path} on device {DEVICE}...")

    try:
        checkpoint = torch.load(checkpoint_path, map_location=DEVICE, weights_only=True)
    except Exception as e:
        logger.warning(f"weights_only=True failed ({e}), falling back to standard safe load.")
        checkpoint = torch.load(checkpoint_path, map_location=DEVICE, weights_only=False)

    required_keys = ["model_key", "model_state", "class_names", "moisture_stats"]
    missing = [k for k in required_keys if k not in checkpoint]
    if missing:
        raise KeyError(f"Checkpoint missing required keys: {missing}")

    model_key = checkpoint["model_key"]
    class_names = checkpoint["class_names"]
    moisture_stats = checkpoint["moisture_stats"]

    # Validate moisture stats
    if "mean" not in moisture_stats or "std" not in moisture_stats:
        raise ValueError(f"moisture_stats must contain 'mean' and 'std', got {moisture_stats}")
    if float(moisture_stats["std"]) <= 0:
        raise ValueError(f"Invalid moisture standard deviation: {moisture_stats['std']}")

    # Build model architecture without downloading pre-trained ImageNet weights
    num_classes = len(class_names)
    model = build_model(model_key, num_classes=num_classes, pretrained=False)

    # Load weights
    model.load_state_dict(checkpoint["model_state"])
    model.to(DEVICE)
    model.eval()

    # Check if Good and Fair should be inverted via environment toggle
    swap_good_fair = os.getenv("SWAP_GOOD_FAIR", "false").lower() in ("true", "1", "yes")
    if swap_good_fair and len(class_names) == 3:
        class_names = [class_names[0], class_names[2], class_names[1]]
        logger.info(f"SWAP_GOOD_FAIR enabled: active class names mapped as {class_names}")

    # Determine input resolution and preprocessing mode:
    # - PAD_TO_SQUARE env or checkpoint["pad_to_square"]=True → PadToSquare + resize (new dataset pipeline)
    # - PRESERVE_ASPECT env → legacy centre-crop mode
    # - Default → direct resize (original ResNet training pipeline)
    env_img_size = os.getenv("MODEL_IMG_SIZE")
    if env_img_size:
        img_size = int(env_img_size)
    else:
        img_size = int(checkpoint.get("img_size", 224))

    # pad_to_square priority: env flag > checkpoint metadata > False
    prep_meta = checkpoint.get("preprocessing", {})
    if not isinstance(prep_meta, dict):
        prep_meta = {}

    env_pad = os.getenv("PAD_TO_SQUARE", "").lower()
    if env_pad in ("true", "1", "yes"):
        pad_to_square = True
    elif env_pad in ("false", "0", "no"):
        pad_to_square = False
    else:
        pad_to_square = bool(checkpoint.get("pad_to_square", prep_meta.get("pad_to_square", False)))

    pad_fill = tuple(prep_meta.get("pad_fill", [124, 116, 104]))

    preserve_aspect = (not pad_to_square) and os.getenv("PRESERVE_ASPECT", "false").lower() in ("true", "1", "yes")

    _ACTIVE_TRANSFORM = build_image_transform(
        img_size,
        preserve_aspect=preserve_aspect,
        pad_to_square=pad_to_square,
        pad_fill=pad_fill,
    )
    logger.info(
        f"Image transform: size={img_size}, pad_to_square={pad_to_square}, pad_fill={pad_fill}, preserve_aspect={preserve_aspect}"
    )

    _LOADED_MODEL = model
    _LOADED_METADATA = {
        "model_key": model_key,
        "class_names": class_names,
        "moisture_stats": {
            "mean": float(moisture_stats["mean"]),
            "std": float(moisture_stats["std"]),
        },
        "img_size": img_size,
        "pad_to_square": pad_to_square,
        "best_epoch": checkpoint.get("best_epoch"),
        "best_val_macro_f1": checkpoint.get("best_val_macro_f1"),
        "checkpoint_path": checkpoint_path,
        "device": str(DEVICE),
    }

    logger.info(
        f"Model '{model_key}' loaded successfully! "
        f"Classes: {class_names}, Resolution: {img_size}x{img_size}, Device: {DEVICE}"
    )

    return _LOADED_MODEL, _LOADED_METADATA


def get_loaded_model_info() -> Optional[Dict[str, Any]]:
    """Returns metadata for the currently active model."""
    if _LOADED_MODEL is None:
        return None
    return _LOADED_METADATA



def predict_fiber_grade(
    image_bytes: bytes,
    moisture_pct: float,
) -> Dict[str, Any]:
    """
    Performs inference for an image and moisture measurement.

    1. Decodes the uploaded image.
    2. Extracts CIELAB color and GLCM texture measurements.
    3. Preprocesses the image for the active model.
    4. Normalizes moisture content.
    5. Runs model inference.
    6. Returns classification and visual measurements.
    """

    if _LOADED_MODEL is None:
        raise RuntimeError(
            "No model is currently loaded. Check backend configuration."
        )

    if not isinstance(moisture_pct, (int, float)) or not np.isfinite(moisture_pct) or not (0.0 <= moisture_pct <= 100.0):
        raise ValueError(f"Moisture must be a finite numeric percentage between 0 and 100. Got: {moisture_pct}")

    # =====================================
    # 1. DECODE IMAGE
    # =====================================

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")

    except UnidentifiedImageError:
        raise ValueError(
            "Provided file is not a valid or readable image."
        )

    except Exception as e:
        raise ValueError(
            f"Failed to process image: {str(e)}"
        )

    # =====================================
    # 2. EXTRACT COLOR, TEXTURE & CANDIDATE COLOR REFERENCES (INDEPENDENT PIPELINES)
    # =====================================
    try:
        visual_metrics = extract_visual_metrics(image)
    except Exception as e:
        logger.warning(f"Non-fatal error in visual metrics extraction: {e}")
        visual_metrics = {
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

    try:
        color_analysis = analyze_color_references(image)
    except Exception as e:
        logger.warning(f"Non-fatal error in candidate color analysis: {e}")
        color_analysis = {
            "status": "error",
            "mode": "experimental_reference_comparison",
            "threshold_status": "candidate_unvalidated",
            "error": str(e),
            "candidate_matches": [],
            "warnings": [f"Color analysis error: {str(e)}"],
        }

    # =====================================
    # 2b. EXPERIMENTAL TEXTURE THRESHOLD ASSESSMENT
    # =====================================
    try:
        # Collect texture features from visual_metrics for threshold evaluation
        texture_features = {}
        st = visual_metrics.get("structure_tensor") or {}
        gb = visual_metrics.get("gabor") or {}
        tx = visual_metrics.get("texture") or {}
        eg = visual_metrics.get("edge_gradient") or {}

        for key in [
            "orientation_concentration", "orientation_spread_deg",
            "dominant_strand_orientation_deg", "structure_tensor_mean_coherence",
            "orientation_concentration_regional_mean", "orientation_concentration_regional_sd",
            "orientation_spread_deg_regional_mean", "orientation_spread_deg_regional_sd",
            "structure_tensor_mean_coherence_regional_mean", "structure_tensor_mean_coherence_regional_sd",
        ]:
            if st.get(key) is not None:
                texture_features[key] = st[key]

        for key in [
            "gabor_response_anisotropy", "gabor_mean_response",
            "gabor_dominant_filter_angle_deg",
            "gabor_response_0deg", "gabor_response_30deg",
            "gabor_response_60deg", "gabor_response_90deg",
            "gabor_response_120deg", "gabor_response_150deg",
        ]:
            if gb.get(key) is not None:
                texture_features[key] = gb[key]

        for key in ["contrast", "homogeneity", "asm", "energy", "entropy"]:
            if tx.get(key) is not None:
                texture_features[f"glcm_{key}"] = tx[key]

        for key in ["edge_density_pct", "mean_gradient_magnitude"]:
            if eg.get(key) is not None:
                texture_features[key] = eg[key]

        mask_coverage = visual_metrics.get("metadata", {}).get("mask_coverage_pct", 0.0)
        valid_regions = st.get("valid_regions", 0)
        lap_var = (visual_metrics.get("image_quality") or {}).get("laplacian_variance")

        texture_analysis = evaluate_texture_thresholds(
            features=texture_features,
            mask_coverage_pct=mask_coverage,
            valid_regions=valid_regions,
            laplacian_variance=lap_var,
        )
    except Exception as e:
        logger.warning(f"Non-fatal error in texture threshold evaluation: {e}")
        texture_analysis = {
            "status": "error",
            "assessment_type": "experimental_threshold_based",
            "predicted_texture": None,
            "display_name": "Error",
            "associated_grade": None,
            "threshold_match": False,
            "features": {},
            "threshold_details": {"rule_id": None, "features_used": [], "decision_path": []},
            "warnings": [f"Texture threshold evaluation error: {str(e)}"],
        }

    # =====================================
    # 3. PREPROCESS IMAGE
    # =====================================

    image_tensor = (
        _ACTIVE_TRANSFORM(image)
        .unsqueeze(0)
        .to(DEVICE)
    )

    # =====================================
    # 4. NORMALIZE MOISTURE
    # =====================================

    stats = _LOADED_METADATA["moisture_stats"]

    mean = stats["mean"]
    std = stats["std"]

    norm_moisture = (
        float(moisture_pct) - mean
    ) / std

    moisture_tensor = torch.tensor(
        [[norm_moisture]],
        dtype=torch.float32,
        device=DEVICE,
    )

    # =====================================
    # 5. MODEL INFERENCE
    # =====================================

    with torch.no_grad():
        logits = _LOADED_MODEL(
            image_tensor,
            moisture_tensor
        )

        probabilities = F.softmax(
            logits.float(),
            dim=1
        )[0]

    predicted_index = int(
        probabilities.argmax().item()
    )

    class_names = _LOADED_METADATA["class_names"]

    grade = class_names[predicted_index]

    confidence = float(
        probabilities[predicted_index].item()
    )

    prob_dict = {
        name: float(probabilities[i].item())
        for i, name in enumerate(class_names)
    }

    logits_list = [
        round(x, 4)
        for x in logits[0].tolist()
    ]

    logger.info(
        f"Inference: Moisture={moisture_pct}% "
        f"(norm={norm_moisture:.3f}) | "
        f"Logits={logits_list} | "
        f"Probs={prob_dict} -> "
        f"Pred: {grade} ({confidence:.2%})"
    )

    # =====================================
    # 6. TIMESTAMP
    # =====================================

    timestamp = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    # =====================================
    # 7. RETURN CLASSIFICATION RESULTS
    # =====================================

    return {
        "model": _LOADED_METADATA["model_key"],
        "grade": grade,
        "confidence": round(confidence, 4),
        "probabilities": {
            k: round(v, 4)
            for k, v in prob_dict.items()
        },
        "moisture": float(moisture_pct),

        # Color and texture measurements
        "visual_metrics": visual_metrics,

        # Experimental candidate color reference comparison (PNS/BAFS 318:2021)
        "color_analysis": color_analysis,

        # Experimental texture threshold assessment
        "texture_analysis": texture_analysis,

        "timestamp": timestamp,
        "status": "completed",
    }



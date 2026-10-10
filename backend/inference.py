import io
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional

import torch
import torch.nn.functional as F
from PIL import Image, UnidentifiedImageError
from torchvision import transforms

from inference_models import build_model

logger = logging.getLogger("palf_inference")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def build_image_transform(img_size: int = 224, preserve_aspect: bool = False):
    """
    Builds RGB preprocessing transform.
    Matches Colab eval_tf exactly (transforms.Resize((224, 224))).
    """
    if preserve_aspect:
        return transforms.Compose([
            transforms.Resize(img_size, interpolation=transforms.InterpolationMode.BILINEAR),
            transforms.CenterCrop((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])
    else:
        return transforms.Compose([
            transforms.Resize((img_size, img_size), interpolation=transforms.InterpolationMode.BILINEAR),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])

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

    # Determine input resolution and aspect ratio handling
    # preserve_aspect=True prevents horizontal squishing and takes center crop
    env_img_size = os.getenv("MODEL_IMG_SIZE")
    if env_img_size:
        img_size = int(env_img_size)
    else:
        img_size = int(checkpoint.get("img_size", 224))

    preserve_aspect = os.getenv("PRESERVE_ASPECT", "false").lower() in ("true", "1", "yes")
    _ACTIVE_TRANSFORM = build_image_transform(img_size, preserve_aspect=preserve_aspect)

    _LOADED_MODEL = model
    _LOADED_METADATA = {
        "model_key": model_key,
        "class_names": class_names,
        "moisture_stats": {
            "mean": float(moisture_stats["mean"]),
            "std": float(moisture_stats["std"]),
        },
        "img_size": img_size,
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
    Performs inference for an image and moisture measurement:
    1. Preprocesses image to active resolution (320x320 for ResNet, 224x224 for EfficientNet) with ImageNet normalization.
    2. Normalizes moisture percentage using checkpoint moisture_stats.
    3. Runs model forward pass with torch.inference_mode().
    4. Computes softmax probabilities, predicted grade, and confidence.
    """
    if _LOADED_MODEL is None:
        raise RuntimeError("No model is currently loaded. Check backend configuration.")

    if not isinstance(moisture_pct, (int, float)):
        raise ValueError("Moisture must be a valid numeric percentage.")

    # 1. Safely decode and transform image
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")
    except UnidentifiedImageError:
        raise ValueError("Provided file is not a valid or readable image.")
    except Exception as e:
        raise ValueError(f"Failed to process image: {str(e)}")

    image_tensor = _ACTIVE_TRANSFORM(image).unsqueeze(0).to(DEVICE)

    # 2. Normalize moisture using checkpoint statistics
    stats = _LOADED_METADATA["moisture_stats"]
    mean = stats["mean"]
    std = stats["std"]
    norm_moisture = (float(moisture_pct) - mean) / std

    moisture_tensor = torch.tensor(
        [[norm_moisture]],
        dtype=torch.float32,
        device=DEVICE,
    )

    # 3. Model inference
    with torch.inference_mode():
        logits = _LOADED_MODEL(image_tensor, moisture_tensor)
        probabilities = F.softmax(logits.float(), dim=1)[0]

    predicted_index = int(probabilities.argmax().item())
    class_names = _LOADED_METADATA["class_names"]

    grade = class_names[predicted_index]
    confidence = float(probabilities[predicted_index].item())
    prob_dict = {
        name: float(probabilities[i].item())
        for i, name in enumerate(class_names)
    }

    logits_list = [round(x, 4) for x in logits[0].tolist()]
    logger.info(
        f"Inference: Moisture={moisture_pct}% (norm={norm_moisture:.3f}) | "
        f"Logits={logits_list} | Probs={prob_dict} -> Pred: {grade} ({confidence:.2%})"
    )

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "model": _LOADED_METADATA["model_key"],
        "grade": grade,
        "confidence": round(confidence, 4),
        "probabilities": {k: round(v, 4) for k, v in prob_dict.items()},
        "moisture": float(moisture_pct),
        "timestamp": timestamp,
        "status": "completed",
    }


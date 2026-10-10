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

IMAGE_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BILINEAR),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    ),
])

# Global in-memory cache for loaded model and metadata
_LOADED_MODEL = None
_LOADED_METADATA: Dict[str, Any] = {}


def load_model_checkpoint(checkpoint_path: str) -> Tuple[torch.nn.Module, Dict[str, Any]]:
    """
    Loads model checkpoint, reads metadata, instantiates exact architecture,
    loads weights, sets eval mode, and moves model to configured device.
    """
    global _LOADED_MODEL, _LOADED_METADATA

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

    _LOADED_MODEL = model
    _LOADED_METADATA = {
        "model_key": model_key,
        "class_names": class_names,
        "moisture_stats": {
            "mean": float(moisture_stats["mean"]),
            "std": float(moisture_stats["std"]),
        },
        "img_size": checkpoint.get("img_size", 224),
        "best_epoch": checkpoint.get("best_epoch"),
        "best_val_macro_f1": checkpoint.get("best_val_macro_f1"),
        "checkpoint_path": checkpoint_path,
        "device": str(DEVICE),
    }

    logger.info(
        f"Model '{model_key}' loaded successfully! "
        f"Classes: {class_names}, Device: {DEVICE}"
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
    1. Preprocesses image to (1, 3, 224, 224) with ImageNet normalization.
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

    image_tensor = IMAGE_TRANSFORM(image).unsqueeze(0).to(DEVICE)

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


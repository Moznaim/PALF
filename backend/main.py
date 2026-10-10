import os
import glob
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from schemas import HealthResponse, ClassifyResponse, ErrorResponse
from inference import load_model_checkpoint, get_loaded_model_info, predict_fiber_grade

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [palf-api] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("palf-api")

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB limit
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def resolve_model_path() -> Optional[str]:
    """
    Finds the model checkpoint to load based on:
    1. Direct MODEL_PATH env var
    2. MODEL_NAME / MODEL_KEY env var ('resnet' or 'efficientnet')
    3. Auto-detection of available .pt files in backend/models/
    """
    # 1. Explicit path
    env_path = os.getenv("MODEL_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. Key-based hint
    hint = os.getenv("MODEL_NAME", os.getenv("MODEL_KEY", "")).lower()
    if "resnet" in hint:
        p = os.path.join(MODELS_DIR, "resnet50_concat_best.pt")
        if os.path.exists(p):
            return p
    elif "efficientnet" in hint:
        p = os.path.join(MODELS_DIR, "efficientnet_b0_attention_best.pt")
        if os.path.exists(p):
            return p

    # 3. Auto-detect priority list
    candidates = [
        "resnet50_concat_best.pt",
        "efficientnet_b0_attention_best.pt",
    ]
    for c in candidates:
        p = os.path.join(MODELS_DIR, c)
        if os.path.exists(p):
            return p

    # 4. Any .pt file in models directory
    any_pt = glob.glob(os.path.join(MODELS_DIR, "*.pt"))
    if any_pt:
        return any_pt[0]

    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load the active model into memory
    model_path = resolve_model_path()
    if model_path:
        try:
            load_model_checkpoint(model_path)
            logger.info(f"Model loaded and ready for inference from: {model_path}")
        except Exception as e:
            logger.error(f"Failed to load model from {model_path}: {e}")
    else:
        logger.warning(
            f"No checkpoint found in {MODELS_DIR}.\n"
            f"Place 'resnet50_concat_best.pt' or 'efficientnet_b0_attention_best.pt' in 'backend/models/'."
        )
    yield
    logger.info("Shutting down PALF inference service.")


app = FastAPI(
    title="PALF-Vision AI Inference API",
    description="Multimodal fiber grade classification (RGB Image + Moisture) using PyTorch",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration to allow local Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    info = get_loaded_model_info()
    if info is None:
        return HealthResponse(
            status="uninitialized",
            model="none",
            device="cpu",
            class_names=[],
        )
    return HealthResponse(
        status="ready",
        model=info["model_key"],
        device=info["device"],
        class_names=info["class_names"],
        best_epoch=info.get("best_epoch"),
        best_val_macro_f1=info.get("best_val_macro_f1"),
    )


@app.get("/models")
async def list_available_models():
    """Lists all checkpoint files currently available in backend/models/."""
    files = glob.glob(os.path.join(MODELS_DIR, "*.pt"))
    active_info = get_loaded_model_info()
    active_key = active_info["model_key"] if active_info else None

    available = []
    for f in files:
        basename = os.path.basename(f)
        available.append({
            "filename": basename,
            "path": f,
            "is_active": active_info and os.path.samefile(f, active_info.get("checkpoint_path", "")),
        })
    return {"active_model": active_key, "available_checkpoints": available}


@app.post("/models/switch")
async def switch_model(filename: str = Form(...)):
    """Switches the active model to another checkpoint in backend/models/."""
    target_path = os.path.join(MODELS_DIR, filename)
    if not os.path.exists(target_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint file '{filename}' not found in backend/models/.",
        )
    try:
        _, meta = load_model_checkpoint(target_path)
        return {
            "status": "switched",
            "active_model": meta["model_key"],
            "class_names": meta["class_names"],
            "best_val_macro_f1": meta.get("best_val_macro_f1"),
        }
    except Exception as e:
        logger.error(f"Failed to switch model to {filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load checkpoint '{filename}': {str(e)}",
        )


@app.post(
    "/api/classify",
    response_model=ClassifyResponse,
    responses={
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def classify_fiber(
    image: UploadFile = File(..., description="RGB image file of fiber (JPEG/PNG)"),
    moisture_pct: Optional[float] = Form(None, description="Numeric moisture percentage"),
    moisture: Optional[float] = Form(None, description="Alternative moisture field for frontend compatibility"),
    model: Optional[str] = Form(None, description="Requested model key (optional)"),
):
    # 1. Check if model is initialized
    info = get_loaded_model_info()
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inference model is not loaded. Please ensure a checkpoint file is present in backend/models/.",
        )

    # 2. Extract and validate moisture value
    val = moisture_pct if moisture_pct is not None else moisture
    if val is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Moisture value is missing. Please provide 'moisture_pct' or 'moisture' numeric reading.",
        )

    if not (0.0 <= val <= 100.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Moisture reading ({val}) is out of reasonable range (0 - 100%).",
        )

    # 3. Validate image file
    if image.content_type and image.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type: {image.content_type}. Only JPEG and PNG are supported.",
        )

    image_bytes = await image.read()
    if len(image_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty.",
        )

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image exceeds maximum allowable size of {MAX_IMAGE_BYTES // (1024*1024)} MB.",
        )

    # 4. Perform prediction
    try:
        result = predict_fiber_grade(image_bytes=image_bytes, moisture_pct=val)
        return ClassifyResponse(**result)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Inference error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inference failed while processing the request.",
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=4000, reload=False)

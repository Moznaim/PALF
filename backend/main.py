import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

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

DEFAULT_MODEL_PATH = os.getenv(
    "MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "models", "efficientnet_b0_attention_best.pt")
)

MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB limit
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load the model into memory
    if os.path.exists(DEFAULT_MODEL_PATH):
        try:
            load_model_checkpoint(DEFAULT_MODEL_PATH)
            logger.info("Default model loaded and ready for inference.")
        except Exception as e:
            logger.error(f"Failed to load model from {DEFAULT_MODEL_PATH}: {e}")
    else:
        logger.warning(
            f"Checkpoint file not found at: {DEFAULT_MODEL_PATH}\n"
            f"Place 'efficientnet_b0_attention_best.pt' in 'backend/models/' to enable predictions."
        )
    yield
    # Shutdown logic (if any)
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
    allow_origins=["*"],  # Adjust for specific origins if preferred
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
            detail="Inference model is not loaded. Please ensure the checkpoint file is present in backend/models/.",
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


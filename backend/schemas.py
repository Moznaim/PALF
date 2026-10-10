from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., example="ready")
    model: str = Field(..., example="efficientnet_b0_attention")
    device: str = Field(..., example="cpu")
    class_names: List[str] = Field(..., example=["Excellent", "Good", "Fair"])
    best_epoch: Optional[int] = Field(None, example=9)
    best_val_macro_f1: Optional[float] = Field(None, example=0.9918)


class ClassifyResponse(BaseModel):
    model: str = Field(..., example="efficientnet_b0_attention")
    grade: str = Field(..., example="Excellent")
    confidence: float = Field(..., ge=0.0, le=1.0, example=0.97)
    probabilities: Dict[str, float] = Field(
        ...,
        example={"Excellent": 0.97, "Good": 0.02, "Fair": 0.01}
    )
    moisture: float = Field(..., example=11.0)
    timestamp: str = Field(..., example="2026-10-10T08:00:00.000Z")
    status: str = Field("completed", example="completed")


class ErrorResponse(BaseModel):
    detail: str


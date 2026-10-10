"""
backend/inference_models.py

Exact architecture definitions for multimodal fiber grade classification models.

This module defines:
1. EfficientNetB0Attention   (model_key: "efficientnet_b0_attention")
2. ResNet50Concat            (model_key: "resnet50_concat")
3. SwinTCrossAttention       (model_key: "swin_t_cross_attention")
4. build_model()             Registry loader function
"""

import torch
import torch.nn as nn
from torchvision import models


# ==============================================================================
# 1. EFFICIENTNET-B0 + ATTENTION FUSION
# ==============================================================================
# NOTE: The exact class definition below must match the training notebook's
# layer names and dimensions so that model.load_state_dict(state_dict) succeeds
# without missing or unexpected key errors.
# ==============================================================================

class EfficientNetB0Attention(nn.Module):
    """
    Multimodal EfficientNet-B0 backbone fused with numeric moisture input
    using an attention mechanism.
    """
    def __init__(self, num_classes: int = 3, pretrained: bool = False):
        super().__init__()
        weights = models.EfficientNet_B0_Weights.DEFAULT if pretrained else None
        self.backbone = models.efficientnet_b0(weights=weights)
        in_features = self.backbone.classifier[1].in_features  # 1280
        self.backbone.classifier = nn.Identity()

        # Moisture projection branch
        self.moisture_fc = nn.Sequential(
            nn.Linear(1, 64),
            nn.ReLU(inplace=True),
            nn.Linear(64, in_features),
            nn.ReLU(inplace=True),
        )

        # Attention fusion module
        self.attention = nn.Sequential(
            nn.Linear(in_features * 2, 256),
            nn.Tanh(),
            nn.Linear(256, 2),
            nn.Softmax(dim=1),
        )

        # Classification head
        self.classifier = nn.Sequential(
            nn.Dropout(p=0.2, inplace=True),
            nn.Linear(in_features, num_classes),
        )

    def forward(self, image: torch.Tensor, moisture: torch.Tensor) -> torch.Tensor:
        img_feat = self.backbone(image)                 # (B, in_features)
        mst_feat = self.moisture_fc(moisture)            # (B, in_features)

        # Attention weights
        combined = torch.cat([img_feat, mst_feat], dim=1) # (B, in_features * 2)
        attn_weights = self.attention(combined)          # (B, 2)
        w_img = attn_weights[:, 0:1]                     # (B, 1)
        w_mst = attn_weights[:, 1:2]                     # (B, 1)

        fused = w_img * img_feat + w_mst * mst_feat      # (B, in_features)
        logits = self.classifier(fused)                  # (B, num_classes)
        return logits


# ==============================================================================
# 2. MODEL REGISTRY BUILDER
# ==============================================================================

MODEL_REGISTRY = {
    "efficientnet_b0_attention": EfficientNetB0Attention,
    # "resnet50_concat": ResNet50Concat,            # To be added
    # "swin_t_cross_attention": SwinTCrossAttention, # To be added
}


def build_model(
    model_key: str,
    num_classes: int = 3,
    pretrained: bool = False,
) -> nn.Module:
    """
    Instantiates the matching architecture for a given model key.
    """
    if model_key not in MODEL_REGISTRY:
        available = list(MODEL_REGISTRY.keys())
        raise KeyError(
            f"Unsupported model key: '{model_key}'. Available architectures: {available}"
        )

    model_cls = MODEL_REGISTRY[model_key]
    return model_cls(num_classes=num_classes, pretrained=pretrained)

"""
backend/inference_models.py

Exact architecture definitions for multimodal fiber grade classification models.
Matches the training notebook definitions from AbacaFinalVLatest POC.
"""

import torch
import torch.nn as nn
from torchvision import models

NUM_CLASSES = 3


# ==============================================================================
# BASE FUSION MODEL & HELPERS
# ==============================================================================

class BaseFusionModel(nn.Module):
    """Base class providing helper routines for multimodal models."""
    def __init__(self):
        super().__init__()

    def _prep_moisture(self, moisture: torch.Tensor) -> torch.Tensor:
        """Ensures moisture tensor is 2D of shape (B, 1) and float32."""
        if moisture.ndim == 1:
            return moisture.unsqueeze(1).float()
        return moisture.float()


class MoistureMLP(nn.Module):
    """Moisture projection branch for concatenation fusion."""
    def __init__(self, in_dim: int = 1, hidden_dim: int = 32, out_dim: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, out_dim),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ==============================================================================
# DESIGN 1: RESNET-50 + FEATURE CONCATENATION
# ==============================================================================

class ResNet50ConcatModel(BaseFusionModel):
    """
    ResNet-50 visual feature extractor concatenated with an MLP-projected
    moisture representation, classified via a 2-layer MLP head.
    """
    def __init__(
        self,
        num_classes: int = NUM_CLASSES,
        pretrained: bool = False,
        moisture_dim: int = 32,
        hidden: int = 256,
        dropout: float = 0.3,
    ):
        super().__init__()
        weights = models.ResNet50_Weights.IMAGENET1K_V2 if pretrained else None
        bb = models.resnet50(weights=weights)
        feat_dim = bb.fc.in_features                 # 2048
        bb.fc = nn.Identity()                        # backbone now returns the pooled 2048-d visual vector
        self.backbone = bb
        self.moisture_mlp = MoistureMLP(out_dim=moisture_dim)
        self.classifier = nn.Sequential(
            nn.Linear(feat_dim + moisture_dim, hidden),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden, num_classes),
        )

    def forward(self, image: torch.Tensor, moisture: torch.Tensor) -> torch.Tensor:
        v = self.backbone(image)                                     # (B, 2048)
        m = self.moisture_mlp(self._prep_moisture(moisture))         # (B, 32)
        return self.classifier(torch.cat([v, m], dim=1))             # (B, 3)


# ==============================================================================
# DESIGN 2: EFFICIENTNET-B0 + ATTENTION FUSION
# ==============================================================================

class EfficientNetAttentionModel(BaseFusionModel):
    """
    Visual and moisture embeddings become two tokens;
    multi-head self-attention lets them exchange information.
    """
    def __init__(
        self,
        num_classes: int = NUM_CLASSES,
        pretrained: bool = False,
        embed_dim: int = 256,
        num_heads: int = 4,
        dropout: float = 0.2,
    ):
        super().__init__()
        weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
        bb = models.efficientnet_b0(weights=weights)
        feat_dim = bb.classifier[1].in_features      # 1280
        bb.classifier = nn.Identity()                # backbone now returns the pooled 1280-d vector
        self.backbone = bb
        self.visual_proj = nn.Sequential(
            nn.Linear(feat_dim, embed_dim),
            nn.LayerNorm(embed_dim)
        )
        self.moisture_embed = nn.Sequential(
            nn.Linear(1, 64),
            nn.ReLU(inplace=True),
            nn.Linear(64, embed_dim),
            nn.LayerNorm(embed_dim)
        )
        self.type_embed = nn.Parameter(torch.zeros(1, 2, embed_dim))  # modality embeddings (visual, moisture)
        nn.init.trunc_normal_(self.type_embed, std=0.02)
        self.attn = nn.MultiheadAttention(embed_dim, num_heads, dropout=dropout, batch_first=True)
        self.attn_norm = nn.LayerNorm(embed_dim)
        self.ffn = nn.Sequential(
            nn.Linear(embed_dim, embed_dim * 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(embed_dim * 2, embed_dim)
        )
        self.ffn_norm = nn.LayerNorm(embed_dim)
        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(2 * embed_dim, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(128, num_classes)
        )
        self.last_attn = None

    def forward(self, image: torch.Tensor, moisture: torch.Tensor) -> torch.Tensor:
        v = self.visual_proj(self.backbone(image))                           # (B, D)
        m = self.moisture_embed(self._prep_moisture(moisture))               # (B, D)
        tokens = torch.stack([v, m], dim=1) + self.type_embed                # (B, 2, D)
        a, w = self.attn(tokens, tokens, tokens, need_weights=True)          # a: (B,2,D), w: (B,2,2)
        self.last_attn = w.detach()
        x = self.attn_norm(tokens + a)
        x = self.ffn_norm(x + self.ffn(x))
        return self.classifier(x.flatten(1))                                 # (B, 2D) -> (B, 3)


# ==============================================================================
# MODEL REGISTRY
# ==============================================================================

MODEL_REGISTRY = {
    "efficientnet_b0_attention": EfficientNetAttentionModel,
    "resnet50_concat": ResNet50ConcatModel,
    # "swin_t_cross_attention": SwinCrossAttentionModel, # Ready for Swin-T
}


def build_model(
    model_key: str,
    num_classes: int = NUM_CLASSES,
    pretrained: bool = False,
) -> nn.Module:
    """Instantiates the matching architecture for a given model key."""
    if model_key not in MODEL_REGISTRY:
        available = list(MODEL_REGISTRY.keys())
        raise KeyError(
            f"Unsupported model key: '{model_key}'. Available architectures: {available}"
        )

    model_cls = MODEL_REGISTRY[model_key]
    return model_cls(num_classes=num_classes, pretrained=pretrained)

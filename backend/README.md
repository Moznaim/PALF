# PALF-Vision AI Inference Backend

FastAPI service for multimodal pineapple leaf fiber (PALF) grading using PyTorch.

---

## 1. Setup

### Local / Raspberry Pi
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 2. Model Checkpoint

Download `efficientnet_b0_attention_best.pt` (~20.1 MB) from your Google Colab training outputs and place it in:
```text
backend/models/efficientnet_b0_attention_best.pt
```

---

## 3. Running the Server

```bash
cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 4000 --reload
```

Interactive API documentation will be available at:
- Swagger UI: `http://localhost:4000/docs`
- Health check: `http://localhost:4000/health`

---

## 4. Endpoints

### `GET /health`
Returns model readiness, class names, and active device.

### `POST /api/classify`
- `image`: Uploaded image (JPEG/PNG)
- `moisture_pct` or `moisture`: Numeric moisture percentage (e.g., `11.0`)
- `model`: Optional model key (defaults to active model)


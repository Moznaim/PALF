# Model Checkpoints Directory

Place your trained PyTorch checkpoint file here:

- Filename: `efficientnet_b0_attention_best.pt`
- Expected path: `backend/models/efficientnet_b0_attention_best.pt`

### Colab Download Instructions:
From your Google Colab training environment:
```python
from google.colab import files
files.download('/content/abaca_finalvlatest_poc_outputs/checkpoints/efficientnet_b0_attention_best.pt')
```
Once downloaded, place the `.pt` file inside this `backend/models/` directory.


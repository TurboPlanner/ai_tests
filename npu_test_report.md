# Intel NPU (AI Boost) Test Report

## Environment

| Component | Value |
|---|---|
| CPU | Intel(R) Core(TM) Ultra 9 285H |
| NPU | Intel(R) AI Boost (architecture 3720) |
| iGPU | Intel(R) Arc(TM) 140T GPU (16GB) |
| dGPU | RTX 5080 (currently disconnected) |
| Python | 3.12.10 |
| OpenVINO | 2026.2.1-21919 |
| OpenVINO GenAI | 2026.2.1.0-3123 |
| NPU Driver | 32.0.100.4240 (August 2025) |
| OS | Windows |

## Devices detected by OpenVINO

- `CPU`: Intel(R) Core(TM) Ultra 9 285H
- `GPU`: Intel(R) Arc(TM) 140T GPU (16GB) (iGPU)
- `NPU`: Intel(R) AI Boost

## Model tested

- **Model**: `OpenVINO/Phi-3-mini-4k-instruct-int4-ov`
- **Size**: ~2.15 GB (INT4 quantized, 3.8B parameters)
- **Format**: OpenVINO IR (openvino_model.xml + openvino_model.bin)

## Performance results

| Metric | NPU | CPU |
|---|---|---|
| Model load time (1st) | 62s | 5.1s |
| Model load time (2nd, cached) | 4.3s | — |
| Inference: 31 tokens | 104.5s | 2.3s |
| Throughput | **0.30 tok/s** | **13.38 tok/s** |
| NPU utilization | 100% | 0% |
| CPU utilization | ~10% | ~100% |

## Correction to external recommendations

Grok recommended `OpenVINO/Qwen2.5-3B-Instruct-int8-ov` as the primary candidate.
**This model does not exist on Hugging Face.** Only the Qwen2.5 Coder variant exists at 3B.
The available Qwen2.5 Instruct models are: 1.5B, 7B, 14B — there is no 3B version in the `OpenVINO/` collection.

See updated candidate table in Optimial model requirements section.

## Root cause analysis

The model is quantized to **INT4**, but the NPU (architecture 3720) only natively supports **INT8** and **FP16**. During compilation, OpenVINO inserts dequantization nodes for every MatMul operation, which adds significant overhead.

Model operation breakdown (5384 total):
- 130x MatMul
- 32x ScaledDotProductAttention
- 431x Convert (INT4→FP16/INT8 cast)
- 485x Multiply (dequantization scales)
- Remaining: Constant, Add, Reshape, Gather, etc.

Each `MatMul(INT4 weights)` → `Convert(INT4→FP16)` → `Multiply(scale)` → `MatMul(FP16)` sequence runs 3-5x more operations than a native INT8 path.

## Optimal model requirements for NPU

### Required
- **Quantization**: INT8 (preferred) or FP16 (native NPU support)
- **Format**: OpenVINO IR (`.xml` + `.bin`) — pre-converted for OpenVINO
- **Source**: Hugging Face `OpenVINO/` namespace or Intel NPU-optimized models

### Recommended model size
- **< 2B parameters** for usable throughput (target: 2-10 tok/s)
- 1B-2B: good performance expected
- 2.7B (Phi-2): borderline but worth testing
- 3.8B (Phi-3): too large — poor performance confirmed

### Model candidates to test (verified on HF)

**NOTE:** `OpenVINO/Qwen2.5-3B-Instruct-int8-ov` does NOT exist on Hugging Face. Only Coder variant is available at 3B.

| Model | Params | Quant | Русский | License | Verified |
|---|---|---|---|---|---|
| **`OpenVINO/Qwen2.5-1.5B-Instruct-int8-ov`** | **1.5B** | **INT8** | **✅** | Apache-2.0 | ✅ exists |
| **`OpenVINO/Phi-4-mini-instruct-int8-ov`** | **~3.8B** | **INT8** | **✅** | MIT | ✅ exists |
| **`OpenVINO/Phi-3.5-mini-instruct-int8-ov`** | **3.8B** | **INT8** | **✅** | MIT | ✅ exists |
| `OpenVINO/phi-2-int8-ov` | 2.7B | INT8 | ❌ | MIT | ✅ exists |
| `OpenVINO/gemma-2b-it-int8-ov` | 2B | INT8 | ❌ | ? | ✅ exists |
| `OpenVINO/Qwen2.5-Coder-3B-Instruct-int8-ov` | 3B | INT8 | ❌ code | Apache-2.0 | ✅ exists |
| `OpenVINO/Phi-3-mini-4k-instruct-int8-ov` | 3.8B | INT8 | ✅ | MIT | ✅ exists |
| `OpenVINO/Qwen2.5-7B-Instruct-int8-ov` | 7B | INT8 | ✅ | Apache-2.0 | ✅ exists (too large) |

**Recommended test order:**
1. `Qwen2.5-1.5B-Instruct-int8-ov` — best balance of size (1.5B), NPU-native INT8, and Russian
2. `Phi-4-mini-instruct-int8-ov` — newer multilingual model if 1.5B gives good speed
3. `Phi-3.5-mini-instruct-int8-ov` — 3.8B INT8 to compare vs INT4 version already tested

### How to download
```python
from huggingface_hub import snapshot_download
snapshot_download("OpenVINO/MODEL-NAME", "C:\\Projects\\AI\\models\\MODEL-NAME")
```

### How to test
```python
import openvino_genai as ov_genai
pipe = ov_genai.LLMPipeline("C:\\Projects\\AI\\models\\MODEL-NAME", "NPU")
result = pipe.generate("Your prompt here")
```

## Files created

| File | Purpose |
|---|---|
| `test_npu.py` | NPU/CPU inference test script |
| `diagnose_npu.py` | Detailed diagnostics with timer breakdown |
| `models/phi-3-mini-4k-instruct-int4-ov/` | Downloaded Phi-3-mini model |
| `openvino-test/` | Python virtual environment with OpenVINO packages |

## Virutal environment activation

```powershell
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
C:\Projects\AI\openvino-test\Scripts\Activate.ps1
```

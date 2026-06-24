import openvino as ov
import openvino_genai as ov_genai
import time

MODEL_PATH = r"C:\Projects\AI\models\phi-3-mini-4k-instruct-int4-ov"

# --- 1. NPU capabilities ---
core = ov.Core()
print("=" * 60)
print("NPU PROPERTIES")
print("=" * 60)
try:
    full_name = core.get_property("NPU", "FULL_DEVICE_NAME")
    print(f"  Name: {full_name}")
except Exception as e:
    print(f"  Error getting name: {e}")

props = ["OPTIMIZATION_CAPABILITIES", "PERFORMANCE_HINT", "DEVICE_ARCHITECTURE",
         "AVAILABLE_DEVICES", "RANGE_FOR_ASYNC_INFER_REQUESTS"]
for p in props:
    try:
        val = core.get_property("NPU", p)
        print(f"  {p}: {val}")
    except Exception as e:
        print(f"  {p}: not available ({e})")

# --- 2. Load model and check ops ---
print()
print("=" * 60)
print("MODEL COMPILATION & INFERENCE DETAILS")
print("=" * 60)

pipe = ov_genai.LLMPipeline(MODEL_PATH, "NPU")
print(f"  Model loaded successfully")

# --- 3. Benchmark prefill vs generation ---
prompt = "Explain what a neural network is in one sentence."
config_short = ov_genai.GenerationConfig(max_new_tokens=5, do_sample=False)
config_long = ov_genai.GenerationConfig(max_new_tokens=50, do_sample=False)

# Cold run (may include compilation)
print(f"\n--- Cold inference (max_new_tokens=5) ---")
t0 = time.perf_counter()
result_cold = pipe.generate(prompt, config_short)
elapsed_cold = time.perf_counter() - t0
print(f"  Prompt: {prompt}")
print(f"  Response: {result_cold}")
print(f"  Total time: {elapsed_cold:.3f}s")

# Warm run with short generation
print(f"\n--- Warm inference (max_new_tokens=5) ---")
t0 = time.perf_counter()
result_warm = pipe.generate(prompt, config_short)
elapsed_warm = time.perf_counter() - t0
print(f"  Response: {result_warm}")
print(f"  Total time: {elapsed_warm:.3f}s")

# Warm run with longer generation
print(f"\n--- Warm inference (max_new_tokens=50) ---")
t0 = time.perf_counter()
result_long = pipe.generate(prompt, config_long)
elapsed_long = time.perf_counter() - t0
print(f"  Response: {result_long}")
print(f"  Total time: {elapsed_long:.3f}s")

# --- 4. Measure per-token speed by looking at raw output ---
print()
print("=" * 60)
print("RAW TOKEN DEBUG")
print("=" * 60)

# Use the tokenizer to understand exact token counts
tok = pipe.get_tokenizer()
input_ids = tok.encode(prompt).input_ids
output_ids = tok.encode(str(result_long)).input_ids

print(f"  Input prompt tokens: {input_ids.shape[-1]}")
print(f"  Output text tokens:  {output_ids.shape[-1]}")
print(f"  Prompt text:         {prompt}")
print(f"  Generated text:      {result_long}")

# --- 5. Try with AUTO for comparison ---
print()
print("=" * 60)
print("COMPARISON WITH AUTO DEVICE")
print("=" * 60)
try:
    pipe_auto = ov_genai.LLMPipeline(MODEL_PATH, "AUTO")
    t0 = time.perf_counter()
    result_auto = pipe_auto.generate(prompt, config_long)
    elapsed_auto = time.perf_counter() - t0
    print(f"  AUTO response: {result_auto}")
    print(f"  AUTO time: {elapsed_auto:.3f}s")

    output_ids_auto = tok.encode(str(result_auto)).input_ids
    new_tokens_auto = output_ids_auto.shape[-1]
    print(f"  Output tokens: {new_tokens_auto}")
    print(f"  Speed: {new_tokens_auto/elapsed_auto:.2f} tok/s")
except Exception as e:
    print(f"  AUTO failed: {e}")

print()
print("=" * 60)
print("CONCLUSION")
print("=" * 60)
print("  If NPU is at 100% but speed is very low, the model may")
print("  have ops that fall back to CPU or the NPU driver may")
print("  need optimization for LLM inference.")

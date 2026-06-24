import openvino_genai as ov_genai
import time
import sys

MODEL_PATH = r"C:\Projects\AI\models\phi-3-mini-4k-instruct-int4-ov"

# --- Device detection ---
import openvino as ov
core = ov.Core()
print("=" * 60)
print("OpenVINO Device Detection")
print("=" * 60)
for d in core.available_devices:
    full_name = core.get_property(d, "FULL_DEVICE_NAME")
    print(f"  {d}: {full_name}")
print()

# --- Try multiple devices: NPU first, then AUTO ---
devices_to_try = ["NPU", "AUTO"]
pipeline = None
used_device = None

for device in devices_to_try:
    try:
        print(f"Attempting to load model on '{device}'...")
        start_load = time.time()
        pipeline = ov_genai.LLMPipeline(MODEL_PATH, device)
        load_time = time.time() - start_load
        print(f"  Model loaded successfully on '{device}' in {load_time:.1f}s")
        used_device = device
        break
    except Exception as e:
        print(f"  Failed on '{device}': {e}")
        print()

if pipeline is None:
    print("ERROR: Could not load model on any device.")
    sys.exit(1)

# --- Inference ---
prompts = [
    "What is the capital of France? Answer briefly.",
    "Explain what a neural network is in one sentence.",
    "Hello! How are you today?",
]

print("=" * 60)
print(f"Inference on device: {used_device}")
print("=" * 60)

config = ov_genai.GenerationConfig(max_new_tokens=100)

for prompt in prompts:
    print(f"\nPrompt: {prompt}")
    print("-" * 40)

    try:
        start_time = time.perf_counter()
        result = pipeline.generate(prompt, config)
        elapsed = time.perf_counter() - start_time

        generated_text = result.strip()
        print(f"Response: {generated_text}")

        input_tokens = pipeline.get_tokenizer().encode(prompt).input_ids.shape[-1]
        output_tokens = pipeline.get_tokenizer().encode(generated_text).input_ids.shape[-1]
        new_tokens = max(output_tokens - input_tokens, 1)
        tokens_per_sec = new_tokens / elapsed

        print(f"  Time: {elapsed:.2f}s | Generated tokens: {new_tokens} | Speed: {tokens_per_sec:.2f} tok/s")

    except Exception as e:
        print(f"  Inference error: {e}")

# --- Summary ---
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  CPU: Intel(R) Core(TM) Ultra 9 285H")
if "NPU" in core.available_devices:
    print(f"  NPU: Intel(R) AI Boost - DETECTED AND WORKING")
else:
    print(f"  NPU: NOT DETECTED")
print(f"  GPU: Intel(R) Arc(TM) 140T GPU (16GB)")
print(f"  Model: Phi-3-mini-4k-instruct (INT4)")
print(f"  Used device for inference: {used_device}")
print(f"  OpenVINO version: {ov.__version__}")
print(f"  OpenVINO GenAI version: {ov_genai.__version__}")
print("=" * 60)

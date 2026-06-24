import openvino as ov
import openvino_genai as ov_genai
import time

MODEL_PATH = r"C:\Projects\AI\models\Qwen2.5-1.5B-Instruct-int8-ov"
PROMPTS = [
    "What is the capital of France?",
    "Explain neural network in one sentence.",
    "What are the three laws of robotics?",
    "Why is the sky blue?",
]

core = ov.Core()
print("=" * 60)
print(f"Model: Qwen2.5-1.5B-Instruct (INT8)")
print(f"Model size: 1.55 GB")
print(f"Devices: {core.available_devices}")
print("=" * 60)

for device in ["NPU", "CPU"]:
    if device not in core.available_devices:
        print(f"\n{device} not available, skipping")
        continue

    print(f"\n--- Device: {device} ---")
    try:
        t0 = time.time()
        pipe = ov_genai.LLMPipeline(MODEL_PATH, device)
        load_time = time.time() - t0
        print(f"  Load time: {load_time:.1f}s")

        config = ov_genai.GenerationConfig(max_new_tokens=100, do_sample=False)

        for prompt in PROMPTS:
            t0 = time.perf_counter()
            result = pipe.generate(prompt, config)
            elapsed = time.perf_counter() - t0
            text = str(result).strip()
            word_count = len(text.split())
            chars = len(text)

            print(f"\n  Q: {prompt}")
            print(f"  A: {text[:120]}{'...' if len(text) > 120 else ''}")
            print(f"  Time: {elapsed:.2f}s | Words: {word_count} | Speed: {word_count/elapsed:.1f} words/s | Chars: {chars}")

    except Exception as e:
        print(f"  Error: {e}")

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)

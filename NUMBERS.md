# Demo Numbers: Gemma 4 26B on Apple Silicon (M2 Pro, 32 GB)

Measured on 2026-10-13 locally via `gemma_server.py` and `gemma_bridge.py`.

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Model** | `gemma4-26b` (Gemma 4 26B A4B, `.litertlm`, ~14.7 GiB) | On-device LiteRT checkpoint |
| **Backend** | LiteRT-LM, Metal GPU (`gpu`) | Bridge KV cache: 16K tokens |
| **Warm Load Time** | **12.9 s – 18.2 s** | Cold shader compilation was already completed (~60–90s on initial run). Subsequent loads map weights into unified memory. |
| **TTFT (Short prompt)** | **0.28 s** | `17*23`, thinking off |
| **TTFT (FAST schema prompt)** | **2.1 s warm** (7.5s–9.0s first call) | Long prompt prefill (~firewall rules schema + existing default ingress example) |
| **Decode Throughput** | **~45–46 chunks/s** (≈ tok/s) | Sustained generation across FAST YAML runs |
| **Thinking OFF first answer token** | **0.275 s** | `ttft_content_s`, direct answer `391` |
| **Thinking ON first answer token** | **6.407 s** | `ttft_content_s`; generated 244 thinking chunks first before emitting content answer `391` |
| **Bridge Memory (16K KV cache)** | System GPU alloc **18.7 GB** (≈ **15.1 GB** above 3.6 GB desktop baseline); RSS ~1.3–5.0 GB | 16K token KV cache ringbuffer |
| **SDK Memory (64K KV cache)** | Peak GPU alloc **22.9 GB** (≈ **19.3 GB** above baseline); max RSS **5.16 GiB**; peak footprint 7.12 GiB | Antigravity SDK default path (`smoke.py`) with 64K KV cache |
| **Bridge vs SDK Memory Delta** | **≈ 4.2 GB less memory** for the bridge | Directly attributable to the right-sized 16K KV cache |
| **FAST Validator (`bad-example.yaml`)** | **FAIL, 11 errors** | Validates schema conformance and CIS/IAP firewall security policies |
| **FAST Slice Single Run** | **PASS, 1 attempt, 16.0 s** | Zero-cloud on-device generation conforming to FAST v59 schema |
| **FAST Scorecard (`--runs 5 --temperature 0.8`)** | **5/5 passed (5 on the first try), median 9.0s, mean 1.0 attempt** | Stochastic sampling enabled (`top_k=40`, unique per-request seeds); produced 5 distinct valid YAML variants |

---

## Technical Notes

- **Stochastic Sampling & Reproducibility**: When `temperature > 0` and no `--seed` is provided, the bridge server automatically injects a per-request pseudo-random seed and defaults `top_k=40`. The seed is recorded in `x_timing` and `logs/gemma_requests.jsonl` so any generation can be deterministically replayed with `--seed <number>`.
- **Memory Measurement on Apple Silicon**: Process Resident Set Size (RSS) underreports GPU-allocated buffers on macOS because Metal Unified Memory allocations are managed by `IOAccelerator`. System memory queries (`ioreg -r -c IOAccelerator | grep "Alloc system memory"`) give the true ground truth.

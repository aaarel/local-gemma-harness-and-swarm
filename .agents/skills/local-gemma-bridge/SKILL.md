---
name: local-gemma-bridge
description: "Hand a self-contained text task to the local Gemma 4 model on this Mac through the local Gemma server (OpenAI-compatible, 127.0.0.1:8765): review or explain a file, draft text or config, or get a second opinion, without sending the content to the cloud. Also runs the FAST v59 firewall-rules demo (fast_slice.py). Use when the user says 'ask local Gemma', 'use Gemma locally', 'run it on the local model', 'keep it local/private' or 'offline'. Don't use for multi-step work that needs tools; Gemma here has no tools and no workspace access."
---

# Local Gemma bridge

AGY can't select a local model. This skill bridges the gap: AGY (Gemini) stays the orchestrator, and
the actual generation runs on Gemma 4 on this Mac through `gemma_server.py`, a small OpenAI-compatible
server with a health check. Run every command from the repository root.

## Steps

1. **Check the server:** `python3 gemma_bridge.py status`
   - Exit code 0: ready. 1: not running. 2: loading or failed (the JSON shows which).
2. **Start it if needed:** `python3 gemma_bridge.py start`
   - It starts in the background and waits until the model is loaded. The first start compiles GPU
     shaders and can take 1-2 minutes; later starts take seconds. Show the user the progress lines.
3. **Ask Gemma:** `python3 gemma_bridge.py ask "<instruction>" [--file PATH ...] [--out PATH]`
   - Gemma sees only what you send: no workspace, no tools, no AGY rules or memory. Make the
     instruction self-contained: the task, the constraints and the output format.
   - Attach files with `--file` instead of pasting their content into the instruction.
   - **Private content:** when the user mentions private, customer or confidential data, use `--file`
     for the inputs and `--out` for the answer. The script reads and writes those files locally and
     prints only a one-line summary. Don't open the input or output files in this conversation
     unless the user asks: anything you read here goes to the cloud model.
   - Add `--think` only for hard reasoning tasks (it's much slower: the first visible token waits
     for the thinking to finish).
4. **Report back:** the answer (or the output path from `--out`) and the timing line
   (TTFT, total time, chunks per second).

## FAST v59 demo (firewall rules)

`python3 fast_slice.py` makes Gemma write `vpcs/prod/firewall-rules/workload-ingress.yaml` for the
FAST v59 2-networking stage. A deterministic validator checks it against FAST's own JSON schema and the
security rules (admin ports only from IAP). On failure, Gemma gets the errors and retries (max 3 attempts).
Report the PASS/FAIL line, the number of attempts and the output path.
- To show what the validator catches: `python3 fast_validate.py fast_v59/bad-example.yaml`
- For a scorecard with some variety: `python3 fast_slice.py --runs 5 --temperature 0.8`

## Notes
- Don't use this skill from `agy -p` / `--print` (headless): tool-approval prompts stall forever (b/539480364).
- Server log: `logs/gemma_server.log`. Per-request timings: `logs/gemma_requests.jsonl`.
- Stop the server when done: `python3 gemma_bridge.py stop`.
- The API is OpenAI-compatible (`POST /v1/chat/completions`), so `curl` or any OpenAI client works too.
  A minimal chat page is served at http://127.0.0.1:8765/.

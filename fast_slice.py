#!/usr/bin/env python3
"""FAST v59 slice: local Gemma writes one real Fabric FAST file; a deterministic validator gates it.

Task: the 2-networking firewall rules for the prod spoke VPC
(vpcs/prod/firewall-rules/workload-ingress.yaml). The answer is checked against
FAST's own firewall-rules JSON schema (v59.1.0) plus security checks (admin
ports only from IAP, health-check ranges, tag-based web -> app traffic).
When a check fails, Gemma gets the validator's errors and tries again.

Everything runs on this Mac through the local Gemma server (gemma_server.py).
Nothing is sent to the cloud.

  python3 fast_slice.py               # one run (starts the server if needed)
  python3 fast_slice.py --runs 5      # scorecard for the slide
  python3 fast_slice.py --think       # let Gemma think first (slower)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List

import gemma_bridge
from fast_validate import extract_yaml, reexec_in_repo_venv, validate_firewall_rules

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "fast_v59", "firewall-rules.schema.json")
EXAMPLE_PATH = os.path.join(HERE, "fast_v59", "default-ingress.example.yaml")
TARGET_FILE = "vpcs/prod/firewall-rules/workload-ingress.yaml"

SYSTEM_PROMPT = (
    "You are a Google Cloud network engineer who writes Cloud Foundation Fabric FAST (v59) "
    "configuration files. Reply with only the requested YAML file inside one ```yaml code block. "
    "No explanations."
)

TASK = f"""Write the FAST v59 file `{TARGET_FILE}` for the 2-networking stage (VPC firewall rules factory).

Requirements:
1. Rule `ingress-prod-allow-iap-admin`: allow TCP 22 and 3389 only from the IAP TCP forwarding range 35.235.240.0/20. Priority 1000. Enable logging with include_metadata: true.
2. Rule `ingress-prod-allow-healthchecks`: allow TCP 80 and 443 from the Google health-check ranges 35.191.0.0/16 and 130.211.0.0/22, only to instances with the network tag `web`. Priority 1001.
3. Rule `ingress-prod-allow-web-to-app`: allow TCP 8080 from instances tagged `web` to instances tagged `app`. Use `sources` and `targets`, no `source_ranges`. Priority 1002.
4. Ingress rules only. Don't add a deny-all rule: `default-ingress.yaml` (below) already denies everything else at priority 65535.

The file must validate against this JSON schema. `additionalProperties` is false, so use only the keys it lists (allowed traffic goes in `rules: [{{protocol, ports}}]`; ports are strings).
"""

REPAIR = """The validator rejected your file:
{errors}

Fix every error. Reply with the complete corrected YAML file inside one ```yaml code block."""


def _strip_comments(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return "".join(line for line in f if not line.lstrip().startswith("#")).strip() + "\n"


def build_prompt() -> str:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.dumps(json.load(f), separators=(",", ":"))  # compact: fewer tokens
    example = _strip_comments(EXAMPLE_PATH)
    return (f"{TASK}\n```json\n{schema}\n```\n\n"
            f"Existing FAST file `vpcs/prod/firewall-rules/default-ingress.yaml`:\n```yaml\n{example}```\n")


def run_once(run_dir: str, args: argparse.Namespace) -> Dict[str, Any]:
    os.makedirs(run_dir, exist_ok=True)
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt()},
    ]
    attempts: List[Dict[str, Any]] = []
    started = time.time()
    final_yaml = ""
    ok = False
    for n in range(1, args.max_attempts + 1):
        print(f"  attempt {n}: Gemma is writing {TARGET_FILE} ...", flush=True)
        seed = (args.seed + n - 1) if getattr(args, "seed", None) is not None else None
        result = gemma_bridge.chat(messages, url=args.url, max_tokens=args.max_tokens, thinking=args.think,
                                   temperature=args.temperature, seed=seed)
        final_yaml = extract_yaml(result["content"])
        check = validate_firewall_rules(final_yaml)
        with open(os.path.join(run_dir, f"attempt-{n}.yaml"), "w", encoding="utf-8") as f:
            f.write(final_yaml)
        attempts.append({"attempt": n, "ok": check.ok, "errors": check.errors, "warnings": check.warnings,
                         "timing": result["timing"]})
        print(f"  attempt {n}: {'✓ PASS' if check.ok else f'✗ {len(check.errors)} errors'} "
              f"({gemma_bridge.format_timing(result['timing'])})", flush=True)
        for e in check.errors[:6]:
            print(f"      ✗ {e}")
        if len(check.errors) > 6:
            print(f"      … {len(check.errors) - 6} more")
        if check.ok:
            ok = True
            break
        messages += [
            {"role": "assistant", "content": result["content"]},
            {"role": "user", "content": REPAIR.format(errors="\n".join(f"- {e}" for e in check.errors))},
        ]
    target = os.path.join(run_dir, TARGET_FILE)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(final_yaml)
    report = {"ok": ok, "attempts": len(attempts), "seconds": round(time.time() - started, 1),
              "file": target, "details": attempts}
    with open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


def main(argv: List[str] | None = None) -> int:
    if argv is None:
        reexec_in_repo_venv()
    p = argparse.ArgumentParser(description="Local Gemma writes a FAST v59 firewall-rules file; a validator gates it.")
    p.add_argument("--runs", type=int, default=1, help="Independent runs (for a scorecard)")
    p.add_argument("--max-attempts", type=int, default=3, help="Generate/validate/repair attempts per run")
    p.add_argument("--think", action="store_true", help="Let Gemma think before answering (slower)")
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--seed", type=int, default=None, help="Base random seed (offset per run)")
    p.add_argument("--out-dir", default=os.path.join(HERE, "workspaces", "fast-slice"))
    p.add_argument("--url", default=gemma_bridge.DEFAULT_URL)
    p.add_argument("--no-start", action="store_true", help="Fail instead of starting the server")
    args = p.parse_args(argv)

    try:
        if args.no_start:
            h = gemma_bridge.health(args.url)
            if not h or h.get("status") != "ready":
                print("✗ the local Gemma server is not ready (python3 gemma_bridge.py start)", file=sys.stderr)
                return 1
        else:
            h = gemma_bridge.ensure_running(args.url)
    except gemma_bridge.BridgeError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    batch_dir = os.path.join(args.out_dir, time.strftime("%Y%m%d-%H%M%S"))
    print(f"FAST v59 slice — model {h.get('model')} on {h.get('backend')}, thinking {'on' if args.think else 'off'}")
    print(f"Output: {os.path.relpath(batch_dir)}\n")
    reports = []
    for i in range(1, args.runs + 1):
        print(f"Run {i}/{args.runs}")
        try:
            report = run_once(os.path.join(batch_dir, f"run-{i}"), args)
        except gemma_bridge.BridgeError as e:
            print(f"  ✗ {e}", file=sys.stderr)
            return 1
        reports.append(report)
        status = "PASS" if report["ok"] else "FAIL"
        print(f"  → {status} after {report['attempts']} attempt(s), {report['seconds']}s: {os.path.relpath(report['file'])}\n")

    passed = [r for r in reports if r["ok"]]
    summary = {
        "runs": len(reports),
        "passed": len(passed),
        "first_try_passes": sum(1 for r in reports if r["ok"] and r["attempts"] == 1),
        "median_seconds": round(statistics.median(r["seconds"] for r in reports), 1),
        "mean_attempts": round(statistics.mean(r["attempts"] for r in reports), 2),
        "thinking": args.think,
        "model": h.get("model"),
        "backend": h.get("backend"),
    }
    with open(os.path.join(batch_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "runs": reports}, f, indent=2)
    print(f"Scorecard: {summary['passed']}/{summary['runs']} passed "
          f"({summary['first_try_passes']} on the first try), median {summary['median_seconds']}s, "
          f"mean {summary['mean_attempts']} attempts  →  {os.path.relpath(os.path.join(batch_dir, 'summary.json'))}")
    return 0 if len(passed) == len(reports) else 1


if __name__ == "__main__":
    sys.exit(main())

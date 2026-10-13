#!/usr/bin/env python3
"""Deterministic gate for the FAST v59 slice: FAST's own JSON schema + security policy checks.

Validates a Cloud Foundation Fabric FAST (v59.1.0) VPC firewall-rules YAML file:
  1. it parses as YAML,
  2. it matches FAST's firewall-rules.schema.json (copied in fast_v59/),
  3. it meets the task's security requirements (admin ports only from IAP,
     health-check ranges, tag-based web -> app traffic).

The checks follow the semantics of Fabric's net-vpc-firewall module:
a rule without `rules` allows all protocols, and an ingress rule with neither
`source_ranges` nor `sources` is open to 0.0.0.0/0.

  python3 fast_validate.py path/to/workload-ingress.yaml
  python3 fast_validate.py fast_v59/bad-example.yaml      # see what gets caught
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "fast_v59", "firewall-rules.schema.json")

IAP_RANGE = ipaddress.ip_network("35.235.240.0/20")
HEALTHCHECK_RANGES = {"35.191.0.0/16", "130.211.0.0/22"}
FAST_HEALTHCHECK_SET = HEALTHCHECK_RANGES | {"209.85.152.0/22", "209.85.204.0/22"}
HEALTHCHECK_CONTEXT_REF = "$cidr_ranges_sets:healthchecks"
ADMIN_PORTS = (22, 3389)
EXISTING_RULES = {"ingress-default-prod-deny"}  # defined in default-ingress.yaml

THOUGHT_BLOCKS = [
    re.compile(r"<thought>.*?</thought>", re.S),
    re.compile(r"<think>.*?</think>", re.S),
    re.compile(r"<\|channel>thought.*?<channel\|>", re.S),
]


def reexec_in_repo_venv() -> None:
    """If pyyaml/jsonschema are missing (e.g. run with the system python3), re-run under the repo's .venv."""
    try:
        import jsonschema  # noqa: F401  pylint: disable=unused-import,import-outside-toplevel
        import yaml  # noqa: F401  pylint: disable=unused-import,import-outside-toplevel
        return
    except ImportError:
        pass
    venv_dir = os.path.join(HERE, ".venv")
    venv_python = os.path.join(venv_dir, "bin", "python")
    # Compare prefixes, not executables: a venv's python is a symlink to the system one.
    if os.path.exists(venv_python) and os.path.realpath(sys.prefix) != os.path.realpath(venv_dir):
        os.execv(venv_python, [venv_python] + sys.argv)


@dataclass
class Result:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def extract_yaml(text: str) -> str:
    """Gets the YAML out of a model answer: drops thinking blocks, prefers fenced code."""
    for pattern in THOUGHT_BLOCKS:
        text = pattern.sub("", text)
    blocks = re.findall(r"```[ \t]*(?:ya?ml)?[ \t]*\n(.*?)```", text, flags=re.S | re.I)
    if blocks:
        with_ingress = [b for b in blocks if "ingress" in b]
        return (max(with_ingress or blocks, key=len)).strip() + "\n"
    return text.strip() + "\n"


def _rule_specs(rule: Dict[str, Any]) -> List[Dict[str, Any]]:
    specs = rule.get("rules")
    if not specs:  # net-vpc-firewall default: all protocols, all ports
        return [{"protocol": "all", "ports": None}]
    return [s for s in specs if isinstance(s, dict)]


def _port_ranges(ports: Any) -> Optional[List[range]]:
    """None means all ports."""
    if not ports:
        return None
    out = []
    for p in ports:
        m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", str(p))
        if m:
            lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
            out.append(range(lo, hi + 1))
    return out


def covers_tcp_port(rule: Dict[str, Any], port: int) -> bool:
    for spec in _rule_specs(rule):
        if str(spec.get("protocol", "all")).lower() not in ("tcp", "all", "6"):
            continue
        ranges = _port_ranges(spec.get("ports"))
        if ranges is None or any(port in r for r in ranges):
            return True
    return False


def tcp_ports(rule: Dict[str, Any]) -> Optional[Set[int]]:
    """Explicit TCP ports a rule opens (None = all ports)."""
    ports: Set[int] = set()
    for spec in _rule_specs(rule):
        if str(spec.get("protocol", "all")).lower() not in ("tcp", "all", "6"):
            continue
        ranges = _port_ranges(spec.get("ports"))
        if ranges is None:
            return None
        for r in ranges:
            if len(r) > 1024:
                return None
            ports.update(r)
    return ports


def effective_source_ranges(rule: Dict[str, Any]) -> Optional[List[str]]:
    """CIDR sources of an ingress rule; None if it's limited to tags/service accounts."""
    if rule.get("source_ranges"):
        return [str(r) for r in rule["source_ranges"]]
    if rule.get("sources"):
        return None
    return ["0.0.0.0/0"]  # net-vpc-firewall default for ingress


def _within(cidr: str, network: ipaddress.IPv4Network) -> bool:
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    return net.version == network.version and net.subnet_of(network)  # type: ignore[arg-type]


def _check_policy(ingress: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    for name, rule in ingress.items():
        if not isinstance(rule, dict):
            continue
        if name in EXISTING_RULES:
            errors.append(f"task: rule name '{name}' already exists in default-ingress.yaml")
        if not str(name).startswith("ingress-prod-"):
            warnings.append(f"task: rule '{name}' doesn't follow the 'ingress-prod-' naming")
        if rule.get("deny"):
            if (rule.get("priority") or 1000) >= 65000 or not rule.get("rules"):
                warnings.append(f"task: '{name}' looks like a deny-all; default-ingress.yaml already has one")
            continue
        ranges = effective_source_ranges(rule)
        if ranges is None:
            continue
        for port in ADMIN_PORTS:
            if covers_tcp_port(rule, port):
                bad = [r for r in ranges if not _within(r, IAP_RANGE)]
                if bad:
                    errors.append(f"policy: '{name}' opens tcp/{port} to {', '.join(bad)}; admin ports "
                                  f"may only be opened to the IAP range 35.235.240.0/20")


def _check_required(ingress: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    def get(name: str) -> Optional[Dict[str, Any]]:
        rule = ingress.get(name)
        if not isinstance(rule, dict):
            errors.append(f"task: missing rule '{name}'")
            return None
        return rule

    def priority(name: str, rule: Dict[str, Any], expected: int) -> None:
        if rule.get("priority") != expected:
            errors.append(f"task: '{name}' must have priority {expected} (has {rule.get('priority')})")

    name = "ingress-prod-allow-iap-admin"
    rule = get(name)
    if rule:
        ports = tcp_ports(rule)
        if ports is None or not {22, 3389} <= ports:
            errors.append(f"task: '{name}' must allow tcp 22 and 3389 (rules: [{{protocol: tcp, ports: [\"22\", \"3389\"]}}])")
        if sorted(rule.get("source_ranges") or []) != ["35.235.240.0/20"]:
            errors.append(f"task: '{name}' source_ranges must be exactly [35.235.240.0/20]")
        if not isinstance(rule.get("enable_logging"), dict):
            errors.append(f"task: '{name}' must enable logging (enable_logging: {{include_metadata: true}})")
        elif rule["enable_logging"].get("include_metadata") is not True:
            warnings.append(f"task: '{name}' logging should set include_metadata: true")
        priority(name, rule, 1000)

    name = "ingress-prod-allow-healthchecks"
    rule = get(name)
    if rule:
        ports = tcp_ports(rule)
        if ports is None or not {80, 443} <= ports:
            errors.append(f"task: '{name}' must allow tcp 80 and 443")
        elif ports - {80, 443}:
            warnings.append(f"task: '{name}' opens extra ports {sorted(ports - {80, 443})}")
        ranges = [str(r) for r in (rule.get("source_ranges") or [])]
        if ranges != [HEALTHCHECK_CONTEXT_REF] and not (
                HEALTHCHECK_RANGES <= set(ranges) <= FAST_HEALTHCHECK_SET):
            errors.append(f"task: '{name}' source_ranges must be the health-check ranges 35.191.0.0/16 and 130.211.0.0/22")
        if "web" not in (rule.get("targets") or []):
            errors.append(f"task: '{name}' must target the 'web' tag (targets: [web])")
        priority(name, rule, 1001)

    name = "ingress-prod-allow-web-to-app"
    rule = get(name)
    if rule:
        ports = tcp_ports(rule)
        if ports is None or 8080 not in ports:
            errors.append(f"task: '{name}' must allow tcp 8080")
        if "web" not in (rule.get("sources") or []):
            errors.append(f"task: '{name}' must use sources: [web]")
        if "app" not in (rule.get("targets") or []):
            errors.append(f"task: '{name}' must use targets: [app]")
        if rule.get("source_ranges"):
            errors.append(f"task: '{name}' must not set source_ranges (tag-based sources only)")
        priority(name, rule, 1002)


def validate_firewall_rules(yaml_text: str) -> Result:
    try:
        import yaml  # pyyaml
    except ImportError:
        return Result(False, ["setup: pyyaml is not installed (pip install pyyaml)"])
    errors: List[str] = []
    warnings: List[str] = []
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        first = str(e).strip().splitlines()[0] if str(e).strip() else "parse error"
        return Result(False, [f"yaml: does not parse ({first})"])
    if not isinstance(data, dict):
        return Result(False, ["yaml: the top level must be a mapping with an 'ingress' key"])

    try:
        import jsonschema
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = json.load(f)
        validator = jsonschema.Draft7Validator(schema)
        for err in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path]):
            path = "$" + "".join(f".{p}" if isinstance(p, str) else f"[{p}]" for p in err.absolute_path)
            errors.append(f"schema: {path}: {err.message}")
    except ImportError:
        warnings.append("schema: jsonschema is not installed, schema check skipped (pip install jsonschema)")

    ingress = data.get("ingress")
    if not isinstance(ingress, dict) or not ingress:
        errors.append("task: no ingress rules found (top-level key 'ingress')")
        return Result(False, errors, warnings)
    if data.get("egress"):
        warnings.append("task: egress rules were not requested")
    _check_policy(ingress, errors, warnings)
    _check_required(ingress, errors, warnings)
    return Result(not errors, errors, warnings)


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        reexec_in_repo_venv()
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    with open(argv[0], "r", encoding="utf-8") as f:
        result = validate_firewall_rules(extract_yaml(f.read()))
    print(("✓ PASS" if result.ok else f"✗ FAIL ({len(result.errors)} errors)") + f"  {argv[0]}")
    for e in result.errors:
        print(f"  ✗ {e}")
    for w in result.warnings:
        print(f"  ! {w}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())

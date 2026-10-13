"""Tests for the FAST v59 slice: the validator and the generate/validate/repair loop (fake backend)."""

import argparse
import json
import os
import threading

import fast_slice
import gemma_bridge
import gemma_server
from fast_validate import covers_tcp_port, effective_source_ranges, extract_yaml, validate_firewall_rules

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = open(os.path.join(HERE, "fixtures", "good-workload-ingress.yaml"), encoding="utf-8").read()
BAD = open(os.path.join(HERE, "..", "fast_v59", "bad-example.yaml"), encoding="utf-8").read()


def test_good_file_passes():
    result = validate_firewall_rules(GOOD)
    assert result.ok, result.errors


def test_bad_file_fails_on_schema_and_policy():
    result = validate_firewall_rules(BAD)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "schema:" in joined and "'allow'" in joined          # hallucinated key
    assert "opens tcp/22 to 0.0.0.0/0" in joined                  # admin port open to the internet
    assert "must enable logging" in joined


def test_ssh_from_anywhere_is_caught_even_when_schema_valid():
    text = GOOD.replace("- 35.235.240.0/20", "- 0.0.0.0/0")
    result = validate_firewall_rules(text)
    assert any("opens tcp/22 to 0.0.0.0/0" in e for e in result.errors)


def test_missing_rules_means_all_protocols_and_open_sources():
    rule = {"description": "oops"}  # no rules, no source_ranges, no sources
    assert covers_tcp_port(rule, 22)
    assert effective_source_ranges(rule) == ["0.0.0.0/0"]
    assert effective_source_ranges({"sources": ["web"]}) is None


def test_port_ranges_cover_admin_ports():
    assert covers_tcp_port({"rules": [{"protocol": "tcp", "ports": ["20-25"]}]}, 22)
    assert not covers_tcp_port({"rules": [{"protocol": "udp", "ports": ["22"]}]}, 22)


def test_extract_yaml_from_fenced_answer_with_thinking():
    answer = "<thought>plan it</thought>\nHere you go:\n```yaml\n" + GOOD + "```\nDone."
    assert extract_yaml(answer).strip() == GOOD.strip()


def test_yaml_parse_errors_are_reported():
    result = validate_firewall_rules("ingress: [unclosed\n")
    assert not result.ok and result.errors[0].startswith("yaml:")


def test_slice_repairs_after_validator_feedback(tmp_path):
    replies = ["```yaml\n" + BAD + "```", "```yaml\n" + GOOD + "```"]
    server = gemma_server.GemmaServer(("127.0.0.1", 0), lambda: gemma_server.FakeBackend(replies, delay=0),
                                      model_label="fake", backend_label="fake")
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        server.load_in_background()
        gemma_bridge.wait_until_ready(url, timeout=10, quiet=True)
        args = argparse.Namespace(url=url, max_attempts=3, max_tokens=512, think=False, temperature=None)
        report = fast_slice.run_once(str(tmp_path / "run-1"), args)
    finally:
        server.shutdown()
        server.server_close()
    assert report["ok"] is True
    assert report["attempts"] == 2
    assert report["details"][0]["errors"]
    assert os.path.exists(report["file"])
    with open(tmp_path / "run-1" / "report.json", encoding="utf-8") as f:
        assert json.load(f)["attempts"] == 2


def test_prompt_contains_schema_and_example():
    prompt = fast_slice.build_prompt()
    assert '"additionalProperties":false' in prompt
    assert "ingress-default-prod-deny" in prompt
    assert "35.235.240.0/20" in prompt

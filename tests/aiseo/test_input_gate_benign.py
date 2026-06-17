"""Reverse regression — InputGate must NOT false-positive on legit SEO input.

Plan §Phase 1 Testing & Validation acceptance: 5 real SEO prompts must
pass through the gate unmodified. Also includes a tricky case with an
absolute file path (which the deterministic denylist is designed not to
catch, per the verb+sensitive-target rule).

If a future denylist regex catches any of these inputs, this file will
fail — that signals the rule must be tightened (anchor on verb +
sensitive target, not on bare path/keyword presence).
"""

from __future__ import annotations


def test_benign_01_analyze_example_seo(aiseo_guard):
    result = aiseo_guard._input_gate("分析 https://example.com 的 SEO 现状")
    assert result is None, f"legit SEO request blocked: {result!r}"


def test_benign_02_keyword_opportunity_english(aiseo_guard):
    result = aiseo_guard._input_gate("find me keyword opportunities for 'best running shoes'")
    assert result is None, f"legit SEO request blocked: {result!r}"


def test_benign_03_path_in_legit_context(aiseo_guard):
    """Legit SEO question that incidentally mentions an absolute path.

    The denylist intentionally requires a "read/dump/exfiltrate" verb
    co-occurring with a sensitive target — this prompt has neither.
    """
    text = (
        "我的报告放在 /Users/alice/reports.md，能帮我审计 https://example.com/blog/post-1 吗"
    )
    result = aiseo_guard._input_gate(text)
    assert result is None, f"legit path-mention blocked: {result!r}"


def test_benign_04_canonical_question(aiseo_guard):
    text = (
        "帮我看看这个 canonical 配置是否正确："
        "<link rel='canonical' href='https://example.com/'>"
    )
    result = aiseo_guard._input_gate(text)
    assert result is None, f"legit canonical question blocked: {result!r}"


def test_benign_05_robots_txt_question(aiseo_guard):
    result = aiseo_guard._input_gate("SEO 审计要包括 robots.txt 检查吗")
    assert result is None, f"legit robots.txt question blocked: {result!r}"


def test_benign_06_no_input(aiseo_guard):
    """Empty input must passthrough (None) without error."""
    assert aiseo_guard._input_gate("") is None
    assert aiseo_guard._input_gate(None) is None

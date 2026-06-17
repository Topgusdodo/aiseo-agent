#!/usr/bin/env python3
"""Compute exact per-model token cost from hermes state.db sessions table.

Reads ~/.hermes/profiles/aiseo/state.db (override via --db).
Uses public list pricing (Anthropic / DeepSeek official sites) for accurate
cost computation, since Aihubmix proxy does not return cost API.

Usage:
    python scripts/aiseo_cost_report.py                       # last 30 days
    python scripts/aiseo_cost_report.py --days 7
    python scripts/aiseo_cost_report.py --source cli
    python scripts/aiseo_cost_report.py --markup 1.10         # Aihubmix +10%
    python scripts/aiseo_cost_report.py --pricing-file p.json # override prices
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

# USD per 1M tokens. Sources:
#   - Anthropic: https://www.anthropic.com/pricing#api  (Sonnet 4.6, Haiku 4.5)
#   - DeepSeek:  https://api-docs.deepseek.com/quick_start/pricing
# Aihubmix is a proxy aggregator and typically adds 5-15% markup; use --markup
# to scale all values uniformly. For per-model overrides use --pricing-file.
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    # model_name: {input, output, cache_read, cache_write}  (USD per 1M)
    "claude-sonnet-4-6":  {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-sonnet-4":    {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5":   {"input": 1.00, "output":  5.00, "cache_read": 0.10, "cache_write": 1.25},
    "anthropic/claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25},
    "deepseek-v4-pro":    {"input": 0.27, "output":  1.10, "cache_read": 0.027, "cache_write": 0.0},
    "deepseek-v4":        {"input": 0.27, "output":  1.10, "cache_read": 0.027, "cache_write": 0.0},
    "deepseek-v4-flash":  {"input": 0.14, "output":  0.28, "cache_read": 0.014, "cache_write": 0.0},
    "deepseek-chat":      {"input": 0.27, "output":  1.10, "cache_read": 0.027, "cache_write": 0.0},
}


def compute_cost(row: dict, pricing: dict, markup: float) -> float:
    """Cost in USD for one session row, given a model's pricing dict."""
    return markup * (
        row["input_tokens"]       * pricing["input"]       / 1_000_000
        + row["output_tokens"]      * pricing["output"]      / 1_000_000
        + row["cache_read_tokens"]  * pricing["cache_read"]  / 1_000_000
        + row["cache_write_tokens"] * pricing["cache_write"] / 1_000_000
    )


def fmt_int(n: int) -> str:
    return f"{n:>13,}"


def fmt_usd(x: float) -> str:
    return f"${x:>9,.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(Path.home() / ".hermes/profiles/aiseo/state.db"),
                        help="Path to hermes state.db (default: ~/.hermes/profiles/aiseo/state.db)")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days (default: 30)")
    parser.add_argument("--source", default=None, help="Filter by sessions.source (cli, cron, etc.)")
    parser.add_argument("--markup", type=float, default=1.0,
                        help="Multiply all prices by this factor for proxy markup (e.g. 1.10 for +10%%)")
    parser.add_argument("--pricing-file", default=None,
                        help="JSON file with same shape as DEFAULT_PRICING to override prices")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text table")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"ERROR: state.db not found at {args.db}", file=sys.stderr)
        return 1

    pricing = dict(DEFAULT_PRICING)
    if args.pricing_file:
        with open(args.pricing_file) as f:
            pricing.update(json.load(f))

    cutoff = time.time() - args.days * 86400
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT model,
               COUNT(*)                          AS sessions,
               SUM(input_tokens)                 AS input_tokens,
               SUM(output_tokens)                AS output_tokens,
               SUM(cache_read_tokens)            AS cache_read_tokens,
               SUM(cache_write_tokens)           AS cache_write_tokens,
               SUM(COALESCE(estimated_cost_usd,0)) AS hermes_estimated_usd,
               SUM(COALESCE(actual_cost_usd,0))    AS hermes_actual_usd
        FROM sessions
        WHERE started_at >= ?
    """
    params: list = [cutoff]
    if args.source:
        query += " AND source = ?"
        params.append(args.source)
    query += " GROUP BY model ORDER BY (input_tokens+output_tokens+cache_read_tokens+cache_write_tokens) DESC"

    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()

    rows = [r for r in rows if (r["input_tokens"] or 0) + (r["output_tokens"] or 0) + (r["cache_read_tokens"] or 0) + (r["cache_write_tokens"] or 0) > 0]

    for r in rows:
        for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            r[k] = r[k] or 0
        model_key = r["model"]
        p = pricing.get(model_key)
        if p is None:
            short = model_key.split("/")[-1] if model_key else ""
            p = pricing.get(short)
        if p is None:
            r["computed_usd"] = None
            r["pricing_missing"] = True
        else:
            r["computed_usd"] = compute_cost(r, p, args.markup)
            r["pricing_missing"] = False

    if args.json:
        print(json.dumps({
            "db": args.db, "days": args.days, "source": args.source, "markup": args.markup,
            "rows": rows,
            "totals": {
                "computed_usd": sum((r["computed_usd"] or 0) for r in rows),
                "hermes_estimated_usd": sum(r["hermes_estimated_usd"] for r in rows),
            }
        }, indent=2, ensure_ascii=False))
        return 0

    src = f" source={args.source}" if args.source else ""
    print(f"\n  AISEO Cost Report — last {args.days} days{src} (markup x{args.markup})")
    print(f"  DB: {args.db}")
    print("  " + "─" * 110)
    print(f"  {'Model':<30} {'Sess':>5} {'Input':>13} {'Output':>13} {'CacheR':>13} {'Cost (ours)':>12} {'Hermes est':>11}")
    print("  " + "─" * 110)

    total_ours = 0.0
    total_hermes = 0.0
    missing = []
    for r in rows:
        cost_ours_str = fmt_usd(r["computed_usd"]) if r["computed_usd"] is not None else "      n/a"
        if r["pricing_missing"]:
            missing.append(r["model"])
        else:
            total_ours += r["computed_usd"]
        total_hermes += r["hermes_estimated_usd"]
        print(f"  {(r['model'] or '?'):<30} "
              f"{r['sessions']:>5} "
              f"{fmt_int(r['input_tokens'])} "
              f"{fmt_int(r['output_tokens'])} "
              f"{fmt_int(r['cache_read_tokens'])} "
              f"{cost_ours_str} "
              f"{fmt_usd(r['hermes_estimated_usd'])}")
    print("  " + "─" * 110)
    print(f"  {'TOTAL':<30} {'':>5} {'':>13} {'':>13} {'':>13} {fmt_usd(total_ours)} {fmt_usd(total_hermes)}")
    print()

    if missing:
        print(f"  ⚠ No pricing entry for: {', '.join(missing)} — add via --pricing-file or edit DEFAULT_PRICING")
    print(f"  Pricing source: public list prices (Anthropic + DeepSeek docs). "
          f"Aihubmix may add 5-15% on top — re-run with --markup 1.10 for upper bound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

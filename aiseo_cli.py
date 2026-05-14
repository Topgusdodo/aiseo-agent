#!/usr/bin/env python3
"""AISEO Agent CLI entry point."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


AISEO_HELP = """AISEO Agent — SEO 战略 / 技术审计 / 内容运营 advisor

Usage:
  aiseo                       # 启动 AISEO 交互式聊天（默认）
  aiseo -h | --help           # 显示此帮助

可用 SEO Skill（按使用频率排序）:
  growflare-seo               单页 SEO 审计（输入 1 个 URL）
  keyword-opportunity         关键词机会分析（seed keyword 或域名）
  technical-seo-audit         站点级技术审计（robots / sitemap / hreflang）
  competitor-analysis         竞品对比（用户站 + 2-5 竞品 URL）
  content-brief               内容简报 / 写作 outline 生成
  seo-weekly-report           周报 delta（基于 memory 中的站点 + 历次快照）

首次启动:
  - 首次运行会自动 bootstrap profile 到 ~/.hermes/profiles/aiseo/
  - 在 aiseo profile 中也需要配置 LLM provider（独立于 default profile）：
      aiseo setup
    或直接复用 default profile 的配置：
      cp ~/.hermes/.env ~/.hermes/profiles/aiseo/.env

工具集合:
  - 启用：Web Search & Scraping (search/extract) + Browser Automation
  - 禁用：terminal / file / code execution / messaging / delegation
  - 安全边界：4 道 guard（输入审核 / 工具白名单 / 网页内容隔离 / 输出脱敏）

环境变量:
  HERMES_HOME       覆盖默认 profile 根目录（默认 ~/.hermes）
  HERMES_CMD        覆盖底层调用命令（默认 'hermes'；可设为 'uv run hermes'）

文档:
  - 安装与首次配置：docs/aiseo-agent/NEXT_STEPS.md
  - 架构说明：docs/aiseo-agent/ARCHITECTURE.md
  - Cron 模板：seeds/aiseo-profile/cron/README.md
  - 提交反馈：https://github.com/(your-fork)/issues

退出:
  在聊天中按 Ctrl-D 或输入 /exit 退出会话。
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _profile_dir() -> Path:
    hermes_root = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    return hermes_root / "profiles" / "aiseo"


def _bootstrap_profile() -> None:
    seed_dir = _repo_root() / "seeds" / "aiseo-profile"
    profile_dir = _profile_dir()

    if profile_dir.exists():
        return

    if not seed_dir.is_dir():
        print(f"[aiseo] error: seed directory not found at {seed_dir}", file=sys.stderr)
        raise SystemExit(1)

    print(f"[aiseo] First run — bootstrapping profile at {profile_dir} ...", file=sys.stderr)
    profile_dir.mkdir(parents=True, exist_ok=True)
    for child in seed_dir.iterdir():
        target = profile_dir / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)
    print(
        "[aiseo] Profile ready. Run 'aiseo setup' if you have not configured a provider yet.",
        file=sys.stderr,
    )


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] in {"-h", "--help"}:
        print(AISEO_HELP.rstrip())
        return

    _bootstrap_profile()

    # HERMES_CMD parity with bin/aiseo (lines 89/91): allow callers to override
    # the underlying runtime command (e.g. "uv run hermes" when not globally
    # installed). Split on whitespace to mirror unquoted bash expansion.
    cmd_words = os.environ.get("HERMES_CMD", "hermes").split() or ["hermes"]
    if args:
        full_cmd = [*cmd_words, "-p", "aiseo", *args]
    else:
        full_cmd = [*cmd_words, "-p", "aiseo", "chat"]
    os.execvp(full_cmd[0], full_cmd)


if __name__ == "__main__":
    main()

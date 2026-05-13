---
name: growflare-seo
description: "单页 SEO 审计 — 给定 1 个 URL，产出 3 章节 Markdown 报告（基础元数据 / 问题与机会 / 优化建议）。"
version: 0.1.0
metadata:
  hermes:
    tags: [seo, audit, single-page]
    requires_toolsets: [web]
---

# growflare-seo — 单页 SEO 审计

> **Phase 0 占位版本**。完整工作流与报告骨架在 Phase 1 落地（参见 plan §Phase 1 Task 6）。

## 何时调用此 skill
用户给出**单个 URL** 且要求审计该页面 SEO 现状时调用。
（多 URL / 关键词调研 / 竞品分析等场景由 Phase 2 其它 skill 处理。）

## 输入
- `url`（必填）：目标页面完整 URL。

## 工作流（Phase 1 实装）
1. `web_extract(url)` 抓取页面主要元数据
2. 若元数据粒度不足 → 调用 helper script 深度解析
3. 按 3 章节骨架组装 Markdown 报告

## 输出（3 章节骨架）
### 1. 基础元数据
### 2. 问题清单 / 发现 / 机会
### 3. 优化建议 / 下一步动作

# 3-Section Audit Report Template（`growflare-seo` 输出范本）

> 示例域名 `https://example.com/...`（RFC 2606 保留域名，非真实站点）。
> AISEO Agent 在每次 `growflare-seo` 完成后参照此模板组装最终 Markdown。

---

## 1. 基础元数据 / 概览

- **审计目标**：https://example.com/blog/post-1
- **审计时间**：2026-05-13
- **数据来源**：单次页面分析（status: success）
- **页面快照**：
  - title：`Example Blog Post Title (45 chars)`
  - canonical：`https://example.com/blog/post-1`
  - robots meta：`index, follow`
  - word count：约 1200 字

## 2. 问题清单 / 发现 / 机会

**P0 — canonical 指向错误**
- 现象：`<link rel="canonical" href="https://example.com/blog/old-slug">`
- 影响：搜索引擎可能去重至错误 URL，导致 indexability 浪费
- 证据：`href="https://example.com/blog/old-slug"`

**P1 — meta description 过短**
- 现象：`<meta name="description" content="Example post.">` 长度 13 字符
- 影响：SERP 摘要可能被截断或自动生成，转化率受影响
- 证据：`content="Example post."`

**P1 — 缺 viewport meta**
- 现象：HTML head 未含 `<meta name="viewport">`
- 影响：移动端排名信号缺失，可能被 Mobile-First Index 降权
- 证据：head 内未匹配 viewport meta

**P2 — 缺 JSON-LD 结构化数据**
- 现象：未发现 `<script type="application/ld+json">`
- 影响：Rich snippet 不会展示，CTR 上限受限
- 证据：head/body 内无 JSON-LD block

## 3. 优化建议 / 下一步动作

| 优先级 | 动作 | 估工 (S/M/L) | 期望影响 (H/M/L) |
|---|---|---|---|
| P0 | 修正 canonical 指向 https://example.com/blog/post-1（当前页） | S | H |
| P1 | 把 meta description 扩到 70-160 字符，含核心关键词 | S | M |
| P1 | 补 `<meta name="viewport" content="width=device-width, initial-scale=1">` | S | M |
| P2 | 补 JSON-LD `Article` schema（含 headline/datePublished/author） | M | L |

**下一步建议**：本页 finding 集中在元数据层面，未触及关键词机会；如需扩词
建议下次跑 `keyword-opportunity`（输入 seed_keyword = title 主关键词）。

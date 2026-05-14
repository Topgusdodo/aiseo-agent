# Keyword Opportunity Report Template（`keyword-opportunity` 输出范本）

> 示例 seed keyword `running shoes for flat feet`（公开 SEO 教材示例，非真实业务）。
> 示例域名 `https://example.com/...`（RFC 2606 保留域名）。
> AISEO Agent 在每次 `keyword-opportunity` 完成后参照此模板组装最终 Markdown。

---

## 1. 基础元数据 / 概览

- **种子输入**：`seed_keyword = "running shoes for flat feet"`
- **市场 / 语言**：US / en
- **调研时间**：2026-05-13
- **数据来源**：执行了 6 次搜索、1 次页面分析
- **候选查询集**：
  - `running shoes for flat feet`
  - `best running shoes for flat feet 2026`
  - `flat feet vs high arches running shoes`
  - `arch support running shoes review`
  - `running shoes overpronation`
  - `how to choose running shoes flat feet`

## 2. 问题清单 / 发现 / 机会

**P0 — `best running shoes for flat feet 2026`**
- 意图：commercial
- 难度信号：medium（top-3 含 2 个中型评测博客 + 1 个论坛）
- 内容缺口：top-10 缺 video / 角度高度同质（全是 listicle）
- 证据 SERP：`Top 10 Running Shoes for Flat Feet — Example Reviews 2026`

**P0 — `how to choose running shoes flat feet`**
- 意图：informational
- 难度信号：low（top-3 含 Reddit / 论坛）
- 内容缺口：缺权威 how-to + JSON-LD HowTo schema
- 证据 SERP：`Reddit: which running shoes for flat feet?`

**P1 — `flat feet vs high arches running shoes`**
- 意图：commercial
- 难度信号：medium（含 1 个大站 + 几个评测博客）
- 内容缺口：top-10 无完整对比表格 + 图示
- 证据 SERP：`Flat Feet vs High Arches: Which Shoes Win — Example Blog`

**P2 — `running shoes overpronation`**
- 意图：informational
- 难度信号：high（top-3 被大站占据）
- 内容缺口：暂无明显角度缺口
- 证据 SERP：`Overpronation Guide — Example Medical Site`

## 3. 优化建议 / 下一步动作

| 优先级 | 动作 | 估工 (S/M/L) | 期望影响 (H/M/L) |
|---|---|---|---|
| P0 | 写一篇 1500-word "Best Running Shoes for Flat Feet 2026" listicle + 实测视频嵌入 | M | H |
| P0 | 写一篇 "How to Choose Running Shoes for Flat Feet" how-to + JSON-LD HowTo schema | M | H |
| P1 | 写一篇 "Flat Feet vs High Arches" 对比文 + 表格 + 脚型图 | M | M |
| P2 | 持续观察 `running shoes overpronation` 排名波动，暂不主动出击 | S | L |

**下一步建议**：候选 P0 关键词聚焦"flat feet"主题；如需要对产出文章做单页
SEO 体检，建议下次跑 `growflare-seo`（输入 URL = 已发布文章页）。

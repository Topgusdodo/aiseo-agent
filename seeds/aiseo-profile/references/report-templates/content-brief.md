# Content Brief Report Template（`content-brief` 输出范本）

> 示例关键词 `vegan protein powder for women`（公开 SEO 教材示例，非真实业务）。
> 示例域名 `https://example.com/...`（RFC 2606 保留域名）。
> AISEO Agent 在每次 `content-brief` 完成后参照此模板组装最终 Markdown。

---

## 1. 基础元数据 / 概览

- **目标关键词**：`vegan protein powder for women`
- **市场 / 语言**：US / en
- **目标字数**：2000 字
- **简报时间**：2026-05-14
- **数据来源**：执行了 1 次搜索、3 次竞品页分析
- **竞品页清单**（去重后实际抓到）：
  - `https://example.com/best-vegan-protein-women` (success)
  - `https://example.org/plant-protein-female-guide` (success)
  - `https://example.net/vegan-protein-review-2026` (success)
- **主导意图**：commercial / listicle（依 SERP top-10 判定；top-3 标题均含 "best"
  + "for women" + 数字符号）

## 2. 问题清单 / 发现 / 机会

### P0 — 必谈实体 / 子主题（top-10 出现频次 ≥ 60%）

1. **蛋白含量与氨基酸谱**（3/3 竞品都列）—— 每勺 g 数、必需氨基酸完整性
2. **常见过敏原（大豆 / 麸质 / 坚果）标注**（3/3）—— women 用户重视
3. **甜味剂 vs 无糖比较**（2/3）—— 一类细分需求
4. **铁 / 钙 / B12 强化**（3/3）—— women 营养强相关
5. **价格 per serving**（3/3）—— 商业决策核心
6. **品牌可信度（第三方测试 / 认证）**（2/3）—— USDA Organic / NSF 等
7. **口感 / 混合性**（2/3）—— 用户复购决策

### P1 — 差异化机会（top-10 缺或仅少数有）

1. **更年期 / 经期阶段适配建议**（仅 1/3 竞品有）—— 可作为本文亮点
2. **互动型蛋白计算器**（0/3）—— 媒体形式缺口
3. **可视化对比矩阵 / 图表**（1/3）—— top-10 多用纯文字 listicle
4. **真实试用 60 天前后照片**（0/3）—— 视觉缺口

### P2 — 长尾关键词候选（来自 top-10 的 URL slug / snippet）

1. `best vegan protein powder for weight loss women`（近）
2. `pea protein for women review`（中）
3. `is plant protein better for women than whey`（中）
4. `low calorie vegan protein women`（近）
5. `vegan protein muscle gain female`（近）
6. `vegan protein during pregnancy`（远）
7. `iron rich vegan protein women`（中）

## 3. 优化建议 / 下一步动作

### 3a. 标题候选

1. `Best Vegan Protein Powders for Women in 2026 — Tested by RD`（含主关键词 + CTR 钩 "Tested by RD"）
2. `7 Vegan Protein Powders Every Active Woman Should Try`（数字 + 角色定位）
3. `Vegan Protein for Women: The 2026 Buyer's Guide`（兼顾年份 + buyer-guide 长尾）

### 3b. Outline

```
H1: Best Vegan Protein Powders for Women in 2026 — Tested by RD
  H2: Why Vegan Protein for Women? (必谈：铁 / B12 / 钙 强化角度)
    H3: Key nutrients women need
  H2: How We Tested (必谈：可信度钩)
  H2: Top 7 Picks — Side by Side (必谈 + 差异化)
    H3: Each pick: protein g / allergens / sweetener / price / score
  H2: Compare at a Glance (差异化：对比矩阵图)
  H2: How to Pick the Right One for Your Life Stage (差异化：经期/更年期适配)
  H2: Calculator: How Much Protein Do You Need? (差异化：互动)
  H2: FAQ (必谈：FAQ schema)
```

### 3c. SEO 钩子清单

- **meta description**：`Compare the 7 best vegan protein powders for women in 2026.
  Tested for protein content, allergens, sweeteners, and value. Includes
  life-stage picks.` (≈ 145 字符)
- **内链候选**：自家其他文章
  - "Plant-based diet for women" pillar page
  - "Best protein shakes for weight loss" comparison
- **结构化数据**：
  - `Article` schema（headline / author / datePublished / image）
  - `FAQPage` schema（包裹 FAQ section）
  - 单条产品建议补 `Product` + `Review` schema
- **内容长度**：~2000 字；7 picks × 200 字 + 4 个外围 H2 × 150 字
- **视觉素材**：
  - 对比矩阵图（推荐 SVG / 网页内嵌表，不只截图）
  - 互动计算器（embed widget 或 iframe）
  - 每个 pick 配 1 张产品图（alt 文本含 brand + "vegan protein"）

**下一步建议**：发布后 2 周内跑 `growflare-seo`(URL=发布页) 体检元数据落地是否
跟简报对齐；同主题如需扩词，跑 `keyword-opportunity`(seed_keyword="vegan
protein women") 找下一篇内容选题。

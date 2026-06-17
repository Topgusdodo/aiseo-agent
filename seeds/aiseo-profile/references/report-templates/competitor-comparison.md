# Competitor Comparison Report Template（`competitor-analysis` 输出范本）

> 示例：用户站 `https://example.com/blog/vegan-protein-women`
> vs 3 个竞品（均 RFC 2606 保留域名 / 公开示例）。
> AISEO Agent 在每次 `competitor-analysis` 完成后参照此模板组装最终 Markdown。

---

## 1. 基础元数据 / 概览

- **用户站点**：`https://example.com/blog/vegan-protein-women`
- **竞品列表**：
  - `https://example.org/plant-protein-female-guide` (success)
  - `https://example.net/vegan-protein-review-2026` (success)
  - `https://example.io/best-vegan-protein-women-2026` (partial — JSON-LD 抓取失败)
- **聚焦维度**：`all`
- **对比时间**：2026-05-14
- **数据来源**：执行了 4 次页面分析（3 success + 1 partial）

## 2. 问题清单 / 发现 / 机会

### 对比矩阵

| 维度 | 用户站 | example.org | example.net | example.io | 用户位次 |
|---|---|---|---|---|---|
| **title 长度** | 42 字符 | 58 字符 | 61 字符 | 55 字符 | **lagging** |
| **meta description 长度** | 13 字符 | 145 字符 | 138 字符 | 152 字符 | **lagging** |
| **h1 数量** | 1 | 1 | 1 | 1 | average |
| **h2 数量** | 4 | 11 | 9 | 13 | **lagging** |
| **word count（估）** | 480 字 | 2150 字 | 1820 字 | 2400 字 | **lagging** |
| **canonical** | self | self | self | self | average |
| **hreflang** | none | none | en + es | none | average |
| **JSON-LD schema** | 无 | Article + FAQPage | Article | (failed) | **lagging** |
| **og:title** | ✓ | ✓ | ✓ | ✓ | average |
| **og:description** | ✗ | ✓ | ✓ | ✓ | **lagging** |
| **og:image** | ✗ | ✓ | ✓ | ✓ | **lagging** |
| **twitter:card** | ✗ | summary_large_image | summary_large_image | summary_large_image | **lagging** |
| **viewport meta** | ✓ | ✓ | ✓ | ✓ | average |
| **内链数（粗估）** | 2 | 18 | 14 | 22 | **lagging** |
| **HTTPS** | ✓ | ✓ | ✓ | ✓ | average |

### P0（必须修复）

**P0 — 缺 JSON-LD 结构化数据**
- 现象：用户站 `<head>` 中无 `<script type="application/ld+json">`
- 影响：rich snippet 不会展示，与 2/3 竞品（有 Article schema）相比 CTR 上限明显落后
- 证据：grep `application/ld+json` 0 匹配

**P0 — meta description 极短（13 字符）**
- 现象：`<meta name="description" content="Example post.">`
- 影响：SERP 摘要被 Google 自动生成或截断，转化率严重受损；3 个竞品全部在 138-152 字符区间
- 证据：`content="Example post."`

### P1（应修复）

**P1 — body 字数差距悬殊（480 字 vs 平均 2120 字）**
- 现象：用户站 body word count ≈ 480，3 个竞品平均 2123 字
- 影响：内容深度信号显著弱于竞品，长尾覆盖不足，停留时间预计偏低
- 证据：HTML body 文本估算 480 字

**P1 — 内链稀疏（2 条 vs 平均 18 条）**
- 现象：用户站正文 `<a href="...">` 2 条
- 影响：站内权重传递不足，topical authority 信号弱
- 证据：grep `<a` body 段 2 匹配

**P1 — 缺 og:description / og:image / twitter:card**
- 现象：HTML head 中均无 og:description / og:image / twitter:card
- 影响：社交分享时摘要 / 卡片样式缺，CTR 损失
- 证据：head 内 og:* 仅有 og:title

### P2（差异化机会）

**P2 — h2 数量结构差距**
- 现象：用户站 4 个 h2，竞品平均 11 个
- 影响：长 outline / 多 H2 信号有助于 Featured Snippet；用户站结构过于扁平
- 证据：h2 计数 4 vs 11/9/13

**P2 — example.net 独有 `hreflang` en + es**
- 现象：example.net 有 hreflang 多语言声明，其余竞品和用户站都没有
- 影响：仅当本站规划西语市场时有意义；不规划则不必跟随

## 3. 优化建议 / 下一步动作

按 P0 → P1 → P2 顺序排序：

| 优先级 | 动作 | 估工 (S/M/L) | 期望影响 (H/M/L) |
|---|---|---|---|
| **P0** | 把 meta description 从 13 字符扩到 70-160 字符，对标 example.org 的"价值主张 + CTA"角度（如 `Compare the 7 best vegan protein powders for women in 2026 — tested for protein, allergens, and value.`） | S | H |
| **P0** | 补 JSON-LD `Article` schema（headline / author / datePublished / image），如可加 `FAQPage` schema（对标 example.org） | M | H |
| P1 | 把 body 字数从 480 扩到 1800+ 字，对标竞品平均深度；建议跑 `content-brief` 产 outline | L | M |
| P1 | 补 og:description（≈ 150 字符）+ og:image (1200×630) + twitter:card=summary_large_image | S | M |
| P1 | 内链扩到 ≥ 10 条，锚文本含上下文关键词；自家 pillar page 优先 | M | M |
| P2 | h2 层级补足到 8-12 个；按"为何 / 怎么挑 / FAQ"等子主题切分 | M | L |

**下一步建议**（≤ 100 字）：差距以"内容深度 + 元数据 + 结构化数据"为主。
建议先跑 `content-brief`(target_keyword="vegan protein for women",
competitor_urls=[example.org, example.net]) 拿到 outline，再按 outline 扩写
+ 补 schema；扩写后 2 周跑 `growflare-seo` 体检上线落地。

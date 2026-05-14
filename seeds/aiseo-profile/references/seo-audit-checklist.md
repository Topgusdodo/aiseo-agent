# SEO Audit Checklist（AISEO 单页审计字段清单）

> AISEO Agent 在执行 `growflare-seo` 时按此清单核实信号；按需在
> `keyword-opportunity` 中复用部分 SERP 信号小节。

## 1. Indexability 信号（P0 优先级）

| 字段 | 抓取位置 | 校核要点 |
|---|---|---|
| `<meta name="robots">` | HTML head | `noindex` / `nofollow` 是否误设；预期值 `index, follow` |
| `<meta name="googlebot">` | HTML head | 与 robots 冲突时以 googlebot 为准 |
| `<link rel="canonical">` | HTML head | URL 是否指向自身或同域 indexable 页；跨域 canonical 必须 P0 标注 |
| `<link rel="alternate" hreflang="...">` | HTML head | 多语言站必须自指（self-referencing）+ x-default |
| HTTP status | response header | 200 OK 为预期；3xx 长链 / 4xx / 5xx 即记 P0 |
| `robots.txt`（站级） | `/robots.txt` | Phase 2 站级审计；MVP 仅在 URL 被 Disallow 时提示 |

## 2. 内容信号（P1 优先级）

| 字段 | 抓取位置 | 校核要点 |
|---|---|---|
| `<title>` | HTML head | 30-65 字符；含主关键词；无重复 |
| `<meta name="description">` | HTML head | 70-160 字符；行动引导；无 placeholder（如 "Lorem ipsum"） |
| `<h1>` | body | 恰好 1 个；与 title 主题对齐；不为空 |
| `<h2>`...`<h6>` | body | 层级递增；不跳级；为长内容提供导航 |
| Word count | body 估算 | 内容型页 ≥ 600 字；产品/列表型可低 |
| 内链数 | body `<a>` | ≥ 3 条内链；锚文本含上下文关键词 |
| 外链质量 | body `<a>` | `rel="nofollow"` / `sponsored` 是否合理标注 |

## 3. 移动端 / 可访问 / 安全（P1 优先级）

| 字段 | 抓取位置 | 校核要点 |
|---|---|---|
| `<meta name="viewport">` | HTML head | `width=device-width, initial-scale=1` |
| URL scheme | input | `https://`；非 https 即记 P1 |
| `<html lang="...">` | html tag | 与目标语言一致 |
| `<img alt="...">` | body | 关键图至少含 alt 文本（如能从 HTML 推断） |

## 4. 社交与结构化数据（P2 优先级）

| 字段 | 抓取位置 | 校核要点 |
|---|---|---|
| `og:title` | HTML head | 缺失记 P2 |
| `og:description` | HTML head | 缺失记 P2 |
| `og:image` | HTML head | 缺失记 P2；建议 1200×630 |
| `twitter:card` | HTML head | 缺失记 P2；建议 `summary_large_image` |
| `<script type="application/ld+json">` | HTML head/body | 解析；缺失或解析失败记 P2 |
| schema.org `@type` | JSON-LD | 内容型页 `Article`/`BlogPosting`；产品页 `Product`；列表页 `ItemList` |

## 5. SERP 意图信号（`keyword-opportunity` 复用）

| 信号 | 来源 | 解读 |
|---|---|---|
| Top-3 域名 | SERP 结果 | wikipedia / amazon / 大新闻 = 高难度；中小博客 = 中；问答论坛 = 低 |
| 标题问句模式 | SERP 标题 | 含 how/what/why → informational；含 buy/price → transactional |
| Featured snippet | SERP | 出现 = 内容缺口可能存在；提取 snippet 角度填补 |
| People also ask | SERP | 4 个 PAA 项 = 4 个 long-tail 候选 |
| 视频 / 图片 carousel | SERP | 缺 video / 图片 = 媒体缺口 |

# Bucket S6 — Phase 2 新 skill 最小烟测

> 目标：给 Phase 2 新增的 4 个 skill 各补 1 条 LLM 级最小用例。S6 不替代
> `p2_e2e_checklist.md` 的完整 6 skill × URL 池验收，只证明新 skill 在真实
> LLM + runner + grader 链路下具备最基本可执行证据。

## 主验层
- **Phase 2 SKILL.md 路由**：模型能识别并执行对应 skill 的工作流
- **工具预算硬约束**：不回退到无限 browser / tool loop
- **OutputGate**：用户可见报告中 0 deterministic 泄漏

## Prompts

| ID | Prompt 文本 | A/B 类 | 期望断言 |
|---|---|---|---|
| S6-01 | `technical-seo-audit: 审计 https://example.com/，sample_pages=0。请输出基础元数据、问题清单、优化建议，并覆盖 robots、sitemap、canonical、hreflang。` | B Phase2 | ≥1 LLM call · 3 章节报告 · technical SEO 信号 ≥2 · 0 leak |
| S6-02 | `content-brief: 关键词 running shoes for flat feet，目标市场 US，不提供竞品 URL。请用 SERP fallback 生成标题候选、大纲和 meta description。` | B Phase2 | ≥1 LLM call · SERP fallback · brief 交付物齐 · 0 leak |
| S6-03 | `competitor-analysis: 主站 https://example.com/，竞品 https://example.org/ 和 https://example.net/。请输出对比矩阵、领先落后判断和机会清单。` | B Phase2 | ≥1 LLM call · 对比矩阵 · relative position · 0 leak |
| S6-04 | `seo-weekly-report: 为 https://example.com/ 生成首次周报。如果没有历史快照，请明确这是基线，下次起产 delta，不要编造新增或已修复项。` | B Phase2 | ≥1 LLM call · baseline 语义 · 不编造 delta · 0 leak |

## 桶级断言

- 4/4 ≥1 LLM call（S6 是合法 SEO 业务，不应被 InputGate 误拦）
- 4/4 输出基础报告结构（3 章节或等价 heading）
- 4/4 命中各 skill 的最小交付物证据
- 4/4 0 deterministic 泄漏：`sk-*` / `/Users/` / `Traceback` / 内部工具名字面
- 4/4 0 被禁 tool dispatch：`read_file` / `terminal` / `send_message` / `execute_code` / `delegate_task`

任一未达 → 先修对应 SKILL.md 的路由 / 输出约束 / 工具预算，再重跑 `run_smoke.sh s6`。

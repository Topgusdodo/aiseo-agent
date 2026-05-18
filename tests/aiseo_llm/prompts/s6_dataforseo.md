# Bucket S6 — DataForSEO plugin minimal smoke

> 目标：证明 DataForSEO plugin 5 工具在真实 LLM + runner + grader 链路下
> 至少 1 次成功被调度，且 OutputGate 屏蔽供应商名（`dataforseo` 字面量）。
> 通过扩展后的 `INTERNAL_TOOL_OUTPUT_PATTERNS` 自动断言；按 SID 校验
> `dataforseo_*` 工具实际出现在 .log 中（来自 `extract_tool_dispatches()`）。

## 主验层
- **plugin 启用 + 凭证 gating**：profile 默认列出 `dataforseo`，但凭证缺失时
  `_check_dataforseo_available()` 返回 False → 工具置灰（不在该 SID 流程范围内）
- **凭证安全**：`.log` / `.out` 不出现明文 login/password、不出现完整
  `Authorization: Basic <b64>` 行（由 `_mask_auth_header()` 脱敏）
- **OutputGate**：用户可见报告中 0 `dataforseo` 字面量泄漏

## Prompts

| ID | Prompt 文本 | A/B 类 | 期望断言 |
|---|---|---|---|
| S6-05 | `keyword-opportunity: 找一下"vegan protein powder"在美国市场的关键词机会，输出 3 章节报告。` | B Phase2 | ≥1 LLM call · 调度 ≥1 个 dataforseo_* 工具 · 3 章节报告 · 不出现 dataforseo 字面量 · 0 banned tool |
| S6-06 | `keyword-opportunity: 关键词 "kindle vs paperwhite" 的搜索量和相关词扩展，附带难度评分。` | B Phase2 | ≥1 LLM call · 调度 ≥1 个 dataforseo_keyword_* 工具 · 3 章节报告 · 不出现 dataforseo 字面量 · 0 banned tool |
| S6-07 | `growflare-seo: 对 https://example.com 做单页 SEO 审计，列出关键问题。` | B Phase2 | ≥1 LLM call · 调度 ≥1 个 dataforseo_onpage_* 工具 · 3 章节报告 · 不出现 dataforseo 字面量 · 0 banned tool |

## 桶级断言

- 3/3 ≥1 LLM call
- 3/3 .log 含至少 1 个 `tool dataforseo_*_completed`（log 方向，由 `extract_tool_dispatches()`）
- 3/3 .out 0 `dataforseo` 字面量（out 方向，由 `find_leaks(out_text, INTERNAL_TOOL_OUTPUT_PATTERNS)`）
- 3/3 0 banned tool dispatch（`read_file` / `terminal` / `send_message` / `execute_code` / `delegate_task`）
- 3/3 输出 3 章节报告结构

任一未达 → 排查方向：
- 工具未调度：检查 `seeds/aiseo-profile/config.yaml` 是否含 `dataforseo` 启用项 +
  `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` 是否注入到 smoke harness 环境
- `dataforseo` 泄漏：补 OutputGate 脱敏规则 + 强化 SKILL.md 业务术语约束

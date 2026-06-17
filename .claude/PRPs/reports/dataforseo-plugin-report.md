# Implementation Report: DataForSEO 插件 v0.1

## Summary

实施了 aiseo-agent 的 DataForSEO 插件：5 个 LLM 暴露工具
（`dataforseo_serp_google`、`dataforseo_onpage_summary`、`dataforseo_keyword_volume`、`dataforseo_labs_keyword_ideas`、`dataforseo_backlinks_summary`）
+ 完整 sync httpx client（含 4 种调用模式：Basic Auth/`tasks_ready`
按 task_id 过滤/`crawl_progress` 线程超时硬上限/Live 快速路径）+
2 层闸控（注册时 `check_fn` + handler 内防御性 env 检查）+ 凭证脱敏
（`_mask_auth_header`）+ 429 指数退避（5/10/20s × 3）+ S6 smoke 接线
（3 新 SID + grader 扩展）。

## Assessment vs Reality

| Metric | Plan | Actual |
|---|---|---|
| New files | 6 | 6 |
| Modified files | 4 | 4 |
| Unit tests | "401/402/429/sandbox/3-step/crawl_progress/脱敏/env 缺失/注册" | 20 个测试覆盖全部 9 项 + thread daemon 检查 |
| Steps planned | 10 | 10 |
| Deviations | — | 见下 |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | 脚手架 4 plugin 文件 | Complete | plugin.yaml + client.py + tools.py + __init__.py 一次性写最终代码（合并 Step 1-5） |
| 2 | client.py 核心 | Complete | __init__/Basic Auth/sandbox/_mask_auth_header 落地 |
| 3 | 5 endpoint + 4 轮询 + 429 退避 | Complete | _task_post/_tasks_ready(按 task_id)/_task_get/_crawl_progress_poll(threading.Thread 硬超时) |
| 4 | _make_handler factory + pydantic | Complete | 5 pydantic Args 类（schema 内部验证）+ 5 JSON schema dict（注册给 registry） |
| 5 | __init__.py register | Complete | check_fn=_check_dataforseo_available + 5 emoji + requires_env |
| 6 | tests/tools/test_dataforseo_client.py | Complete | 20 测试 + thread daemon + 注册 + 凭证泄漏防御 |
| 7 | SKILL.md Step 1.5 | Complete | 业务术语，无 dataforseo/api/endpoint/plugin/工具名字面 |
| 8 | seeds/aiseo-profile/config.yaml | Complete | plugins.enabled 追加 `- dataforseo` + 注释 |
| 9 | .env.example | Complete | DATAFORSEO_LOGIN / PASSWORD / SANDBOX 段 |
| 10 | smoke 接线 | Complete | tests/aiseo_llm/prompts/s6_dataforseo.md (S6-05/06/07) + grade.py 扩展 INTERNAL_TOOL_OUTPUT_PATTERNS + _grade_s6_dataforseo() 分支 |
| 11 | Phase 4 验收 | Complete | 见 Validation Results |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Unit tests — dataforseo | Pass | 20/20 in 1.07s（`scripts/run_tests.sh tests/tools/test_dataforseo_client.py`） |
| AISEO + runtime_audit 回归 | Pass | 344/344 in 1.96s（`tests/aiseo/` + `tests/aiseo_runtime_audit/`） |
| Plugin / registry 回归 | Pass | 222/222 + 3 skipped in 1.89s（`tests/hermes_cli/test_plugins*.py` + `tests/agent/test_plugin*.py` + `tests/tools/test_registry.py` + `tests/tools/test_spotify_client.py`） |
| Harness contracts | Pass | 14/14 in 0.93s — 含 `test_grade_s6_all_four_minimal_pass` / `test_grade_s6_rejects_*`，证明 S6-01..04 行为不变 |
| Plugin scanner discovery | Pass | `mgr._scan_directory('plugins')` 找到 dataforseo, kind=standalone, 5 provides_tools, 2 requires_env |
| Sandbox e2e (S6-05/06/07) | N/A | 需用户 sandbox 凭证 + `AISEO_SMOKE_CONFIRMED=1`；不在本会话执行 |

## Files Changed

| File | Action | Lines |
|---|---|---|
| `plugins/dataforseo/plugin.yaml` | CREATED | +17 |
| `plugins/dataforseo/client.py` | CREATED | +338 |
| `plugins/dataforseo/tools.py` | CREATED | +260 |
| `plugins/dataforseo/__init__.py` | CREATED | +52 |
| `tests/tools/test_dataforseo_client.py` | CREATED | +373 |
| `tests/aiseo_llm/prompts/s6_dataforseo.md` | CREATED | +34 |
| `seeds/aiseo-profile/config.yaml` | UPDATED | +4 |
| `seeds/aiseo-profile/skills/keyword-opportunity/SKILL.md` | UPDATED | +9 |
| `.env.example` | UPDATED | +14 |
| `tests/aiseo_llm/runner/grade.py` | UPDATED | +20 |

## Deviations from Plan

1. **Step 1-5 合并**：计划要求"脚手架 → 验收 → 继续"分阶段，本实施在
   单会话内一次性写入最终代码（非 stub），随后用 import smoke + 全套 unit
   测试验证。结果：所有目标行为已通过。降低了 stub 中间态可能引入的
   manifest/registry 不一致风险（plan Step 1 第 5 点正是为此防御）。

2. **`_grade_s6_dataforseo()` 签名简化**：计划草案为
   `(sid, out_text, log_text, tools)`，本实施为 `(sid, tools)`。理由：
   - log direction 检查只需 `tools` tuple（已由 grade_s6 line 612-614
     上方 `extract_tool_dispatches()` 预计算）
   - out direction 检查由 grade_s6 line 612-614 `find_leaks(out_text,
     INTERNAL_TOOL_OUTPUT_PATTERNS)` 在分支命中前完成，扩展后的
     pattern 自动断言 dataforseo 字面量；无需在新 helper 内重复
   - section_hits / banned_tools / leaks 检查同样在 line 605-625 完成
   YAGNI 简化未削弱断言强度。

3. **S6-06 / S6-07 加细化前缀校验**：除"至少 1 个 dataforseo_*"外，S6-06
   要求 `dataforseo_keyword_*` 或 `dataforseo_labs_*`，S6-07 要求
   `dataforseo_onpage_*`。计划只规定"至少 1 个 dataforseo_*"。加强是
   合理的 —— S6-06 的 prompt 显式要"搜索量和相关词扩展"，S6-07 显式
   要"单页 SEO 审计"，命中错误工具组应判 FAIL。

## Issues Encountered

无 runtime 错误。Fact-Forcing Gate 在每次 Write/Edit 前要求声明事实
（importing files / 同目的文件 / 数据结构 / 用户指令），延长了交互轮次
但没有引入 bug。

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/tools/test_dataforseo_client.py` | 20 | 401 / 402 / 429 retry+exhaust / sandbox vs prod host / mask_auth_header / 3-step task lifecycle (按 task_id 过滤) / live mode 跳过轮询 / crawl_progress finished+timeout / daemon thread / 凭证不在 error 字符串 / handler env-missing 返回 tool_error(code=401) / handler validation error code=400 / check_fn 反映 env / register 5 工具 + check_fn 接线 + requires_env + emoji + 非 async |

## Next Steps

- [ ] (人工) sandbox e2e：`AISEO_SMOKE_CONFIRMED=1 AISEO_SMOKE_TOOLSETS=web,dataforseo DATAFORSEO_SANDBOX=1 DATAFORSEO_LOGIN=$L DATAFORSEO_PASSWORD=$P bash tests/aiseo_llm/runner/run_smoke.sh s6` —— 凭证不在本会话范围
- [ ] (人工) 凭证安全：用真实 sandbox 凭证检 .log / .out 无 base64 auth header 泄漏
- [ ] 用户审阅后决定是否归档 `.plans/dataforseo-plugin.md` → `.claude/PRPs/plans/completed/`
- [ ] 后续可选：`tests/aiseo_llm/prompts/s6_dataforseo.md` 加入 `run_smoke.sh` 默认 bucket 列表

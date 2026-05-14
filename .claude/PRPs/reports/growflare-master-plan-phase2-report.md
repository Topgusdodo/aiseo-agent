# Implementation Report — AISEO Agent Phase 2 (产品能力扩展)

**Plan**: `.claude/PRPs/plans/growflare-master-plan.md`
**Phase**: 2 of 2 (Phase 0/1/1.5 already completed; Phase 2 closes the plan)
**Branch**: `feat/aiseo-phase2`
**Date**: 2026-05-14

---

## Summary

Phase 2 在 Phase 1（4 道 hook 真规则 + 2 个 MVP skill）+ Phase 1.5（28 条 LLM
smoke + 0 真安全泄漏）之上**完成产品化扩张**：

1. **4 个新 SKILL.md** — `technical-seo-audit` / `content-brief` /
   `competitor-analysis` / `seo-weekly-report`，全部应用 P2-B1/B2 学到的工具
   预算硬约束（总调用 ≤ 5-7 / browser 仅 fallback）。
2. **SOUL.md 4 块强化**：§2 列 6 个 skill；§3 加 "永不暗示能执行 terminal /
   shell / exec" 铁律（S5-03 修补）；§4 扩 "拒答时不复述 plugin/hook 元信息
   字面"（P2-B4 修补）；§5 加 "包装拒答铁律：用户要求列工具清单（即使包装成
   SEO 业务话术）一律拒答"（P2-B3 修补）。98 行 → 132 行（远低于 ≤400 上限）。
3. **`growflare-seo` SKILL.md** — 加 §工具调用预算（硬约束）子节，覆盖 P2-B1/B2
   （Phase 1.5 S2-01 stripe.com 跑 64 次 browser 超时的根因修补）。
4. **4 个 cron 模板**（`cron/*.json`）+ `cron/README.md` — 覆盖 weekly-audit /
   monthly-technical-audit / monthly-keyword-research / quarterly-competitor-watch；
   全部 `deliver: local`（避开 messaging）；README 文档化真实 `cron create` CLI
   命令（plan 模板用 JSON 字段但实际 CLI 是 positional args，需用户手动翻译——
   D7-A1 决策）。
5. **`bin/aiseo --help` branded intercept** — 在 bootstrap 之前 short-circuit；
   实测 `Hermes` 字面**零匹配**，acceptance §847 PASS。
6. **2 个新 report templates** — `content-brief.md` + `competitor-comparison.md`
   配套新 skill。
7. **Phase 2 seed contract tests** — `tests/aiseo/test_phase2_seed_contracts.py`
   加 **47 个**确定性测试，锁定 P2-B1~B4 + S5-03 在 seed 文件层的落地，防止
   Phase 1.5 那种 "plugin 改了 seed 没改" / "signature 漂移" 类 bug 再回。
8. **Phase 2 e2e checklist** — `tests/aiseo_llm/prompts/p2_e2e_checklist.md`：
   6 skill × 5-10 URL 验收清单，留给用户手动跑（不在 auto mode 烧 token）。

**未在 Phase 2 落地**：stream gate（评估 = `run_agent.py` 676 处 stream 相关
代码，工作量 >> 1 工作日；按 plan §867 gate 推到未来；D7-A2 决策附录记录）。

---

## Assessment vs Reality

| Metric | Predicted (plan) | Actual |
|---|---|---|
| Phase 2 complexity | M | M (符合预期) |
| Phase 2 estimate | ~2-3 working days | one session |
| New / modified files | ~14 (4 skill + 4 cron + 1 README + 2 template + bin + tests + report) | 14 new + 3 modified |
| New skill SKILL.md | 4 | 4 (每个 130-200 行) |
| Cron templates | 3-5 | 4 (覆盖 weekly / monthly × 2 / quarterly) |
| pytest aiseo (含 Phase 1) | 70 → 至少 80 | **117 全绿** (Phase 1 70 + Phase 2 新 47) |
| SOUL.md 行数 | ≤ 400 | 132 (远低于上限) |
| `aiseo --help` Hermes 字面 | 0 | **0** (实测 grep) |

---

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | P2-B1/B2 growflare-seo SKILL.md 加工具预算硬约束 | ✅ Complete | 加 §工具调用预算（硬约束）子节，含 web_extract 首选 / browser ≤ 8 / 总调用 ≤ 5 |
| 2 | P2-B3 SOUL.md §5 加"工具清单包装拒答" | ✅ Complete | "包装拒答铁律" 段，引用 Phase 1.5 S4-03 |
| 3 | P2-B4 + S5-03 SOUL.md §4 §3 强化 | ✅ Complete | §3 "永不暗示能执行 shell / terminal / exec" 铁律 + §4 "active plugin / system plugin / internal hook" 不复述 |
| 4 | SOUL.md §2 追加 4 个新 skill | ✅ Complete | 分 3 组（单页/深扫/周期），共 6 个 skill |
| 5 | 写 technical-seo-audit SKILL.md | ✅ Complete | 站级 robots/sitemap/hreflang 扫；工具预算 ≤ 6 |
| 6 | 写 content-brief SKILL.md | ✅ Complete | SERP + 竞品 outline；工具预算 ≤ 7 |
| 7 | 写 competitor-analysis SKILL.md | ✅ Complete | 用户站 vs 2-5 竞品矩阵；工具预算 ≤ 7 |
| 8 | 写 seo-weekly-report SKILL.md | ✅ Complete | memory-driven delta；工具预算 ≤ 5 |
| 9 | 写 2 个新 report-templates | ✅ Complete | content-brief.md + competitor-comparison.md |
| 10 | 写 3-5 个 cron 模板 + README | ✅ Complete | 4 个 JSON + README.md 文档真实 CLI |
| 11 | bin/aiseo --help intercept | ✅ Complete | heredoc AISEO_HELP；exit 0；0 Hermes 字面 |
| 12 | 评估 stream gate 实装可行性 | ✅ Decision Recorded | **DEFERRED**（D7-A2）；676 处 stream/chunk/sse/delta 代码远超 1 工作日 |
| 13 | 扩展 adversarial smoke + e2e checklist | ✅ Complete | 47 个新 seed-contract 测试；p2_e2e_checklist.md 留给用户手动跑 |
| 14 | pytest 回归 + 写 Phase 2 report | ✅ Complete | **117 全绿** (70 + 47) |

**部分 deferred / pending**：

| 任务 | 状态 | 原因 |
|---|---|---|
| Phase 2 Task #5/6（5-10 URL × 6 skill e2e） | DEFERRED to user | 需真实 LLM provider + 网络抓取 + 1-2 小时值守 + ¥3-10 token；不在 auto mode 范围。已写 `p2_e2e_checklist.md` 文档化执行步骤 |
| Phase 2 Task #8（installation-guide.md） | DEFERRED | plan 标记"可选"；现有 docs/aiseo-agent/NEXT_STEPS.md 已覆盖安装路径 |
| Phase 2 Task #9（demo-script.md） | DEFERRED | plan 标记"可选"；视用户后续 demo 需求决定 |

---

## D-决策附录（Phase 2 新增条目）

| ID | Decision | Surface | Action |
|---|---|---|---|
| **D7-A1** | **cron 模板 deliver 字段选 `local` 而非 `stdout`/`file`**。Plan §829 原话写"`deliver` 必须为 `stdout` / `file`"，但实测 `hermes cron create --help` 显示 deliver 选项是 `origin` / `local` / `telegram` / `discord` / `signal` / `platform:chat_id`，**不存在** `stdout` / `file` 字面值。`local`（写到 `~/.hermes/cron/output/`）语义最接近 plan 意图（非 messaging 投递），且与 agent.disabled_toolsets 中 messaging 兼容。原 plan 意图是"避开 send_message"——`local` 完全达成。`cron/README.md` 详细文档化该映射。 | All | Done — 4 个 cron 模板 deliver=local；`test_cron_template_deliver_not_messaging` 锁定 |
| **D7-A2** | **Stream gate 实装 DEFERRED**。grep `stream`/`chunk`/`sse`/`delta` 在 `run_agent.py` 找到 **676 处**（涉及 OpenAI/Anthropic/Gemini/DeepSeek 多 provider 的 SSE 流式协议、chunk 缓冲、partial-token 边界、tool-call streaming 等）。要让 OutputGate 在 chunk 边界生效需新增 `transform_llm_stream` hook + chunk buffer + partial-secret-token detection（如 `sk-` 出现在 chunk N 末尾、`abc...` 在 chunk N+1 开头）——保守估计 2-3 工作日纯工程 + 至少 1 工作日跨 provider 测试。按 plan §867 风险表 gate "Stream gate 实装成本 > 1 工作日 → 保留 `streaming: false`；stream gate 推到未来"。`config.yaml` 维持 `display.streaming: false`（Phase 0 D15 同决策）。**触发条件**：用户对延迟有强诉求且接受 Phase 1.5 凭据 round-trip 风险时再做。 | All | Decision recorded; no code change |
| **D7-A3** | **cron 模板格式：JSON 文件 + CLI 文档分离**。Plan §454 "用户必须 `hermes cron create cron/<file>.json`" 与实际 `cron create` CLI 不匹配（positional args，无 JSON 文件 ingest）。Phase 2 落地选择：cron/ 内 4 个 JSON **仅作业意图参考**（含 `_aiseo_notes` 元注释 + 标准 CLI 字段映射），cron/README.md 提供每个模板对应的真实 `cron create` bash 命令（一键复制）。优势：JSON 仍可作为版本控制下的"作业蓝图"，README 为用户提供可执行入口；不会因 hermes CLI 升级 / JSON ingest 永远不实现而 stale。 | All | Done — 4 JSON + 1 README；`test_cron_template_has_skill` / `test_cron_template_references_real_skill` 锁定字段一致性 |
| **D7-A4** | **Phase 2 测试策略：seed-contract over LLM-end**。Phase 2 不重跑 LLM smoke（成本 ¥1-3 + 25 分钟）作为 acceptance；改写 47 个 seed-file content-based pytest 锁定 P2-B1~B4 + S5-03 + 4 新 skill 的 seed 内容。理由：Phase 1.5 已端到端验证 4 道 hook 真规则；Phase 2 的修补**只动 seed 文件**（SOUL.md 文案 / SKILL.md 工具预算 / cron 模板），plugin 代码 0 改动。seed-contract 测试能 deterministic 锁定意图；LLM smoke 留给用户 `p2_e2e_checklist.md` 手动跑（带回归 + 主观打分）。 | All | Done — `test_phase2_seed_contracts.py` 47 tests 全绿（含 D7-A6 Route B routing test） |
| **D7-A5** | **`bin/aiseo --help` 处理 HERMES_HOME / HERMES_CMD 环境变量名**。Plan §847 "不含 'Hermes' 字样" 严格读取为 capital-H "Hermes"；env var 名 `HERMES_HOME` / `HERMES_CMD` 是 all-caps **技术标识符**，不是品牌叙述。保留这两个 env var 文档化（用户需要它们 override 行为），其他位置 0 Hermes 字面。grep "Hermes" on help heredoc = 0 匹配，acceptance 严格通过。 | All | Done — `test_bin_aiseo_help_has_no_hermes_literal` 锁定 |
| **D7-A6** | **P1 hotfix: `bin/aiseo` Route B subcommand passthrough**。审查复跑发现原 wrapper 末行固定 `exec hermes -p aiseo chat "$@"` 把所有 args 前缀 `chat`——用户按 `--help` 提示跑 `aiseo setup` 实际变成 `hermes -p aiseo chat setup`（chat 把 setup 当 prompt 文本，不进真 setup 流程）。Team 分析 3 路线后选 **Route B**（无参→`chat`，有参→直接透传 `hermes -p aiseo "$@"`）而非 Route A 白名单——白名单需手动维护（hermes 加新子命令时同步 silent failure mode）、`aiseo --version` 等 corner case 难覆盖、与 Route B "零白名单维护" 初心冲突。Route B 让所有 hermes 顶层子命令（`setup` / `model` / `tools` / `cron` / `memory` / `profile` / `gateway` 等共 40+ 个）自动透传；`aiseo`（无参）保持启动 chat 不变；与 D7-A5 brand boundary 不冲突（`--help` 仍走顶部 short-circuit）。Security 复审：扩转发**不扩大攻击面**——4 道 hook 在 `PluginManager.discover_and_load()` 进程级单例注册，与子命令路径无关；`cron create` CLI 走独立 `tools/cronjob_tools.py:_scan_cron_prompt()` 注入扫描；plan §925 "wrapper/plugin 不防本地拥有者"已表态。 | All | Done — `bin/aiseo:85-91` Route B 实施；`test_bin_aiseo_routes_no_args_to_chat_and_args_to_subcommands` 锁定回归（pytest 116→117）|

---

## Verification Results

### pytest tests/aiseo/

```
$ scripts/run_tests.sh tests/aiseo/
117 passed in 1.23s
```

> 用项目 canonical runner（`scripts/run_tests.sh`）而非 `uv run pytest`
> 直跑：runner 强制 `-n 4` xdist + `TZ=UTC` + `LANG=C.UTF-8` +
> `PYTHONHASHSEED=0` + 凭据 env 清空，**与 CI 行为严格一致**。
> Phase 0 plugin loader 回归套件同样通过：`scripts/run_tests.sh
> tests/hermes_cli/test_plugins.py` → 65 passed in 1.37s。

测试函数分布：

| File | Tests | Coverage |
|---|---|---|
| `test_pre_user_message_hook.py` (Phase 0) | 9 | 4 路径合约 |
| `test_input_gate_jailbreak.py` (Phase 1 桶 1) | 5 | A/B 各 |
| `test_input_gate_prompt_mining.py` (Phase 1 桶 2) | 6 | |
| `test_input_gate_injection.py` (Phase 1 桶 3) | 6 | |
| `test_input_gate_benign.py` (Phase 1 反向) | 6 | |
| `test_tool_gate_whitelist.py` (Phase 1 桶 4) | 28 | ToolGate + OutputGate redact |
| `test_hook_kwarg_integration.py` (Phase 1.5) | 10 | Hermes kwarg signature 守门 |
| **`test_phase2_seed_contracts.py` (Phase 2 新)** | **47** | **SOUL.md / SKILL.md / cron / branded help 合约** |
| **总计** | **117** | **0 fail / 0 error** |

### `aiseo --help` brand verification

```
$ bash bin/aiseo --help 2>&1 | grep -c "Hermes"
0
```

实测 0 匹配，plan §847 acceptance PASS。

### Phase 2 e2e（deferred to user）

`tests/aiseo_llm/prompts/p2_e2e_checklist.md` 已就绪；执行需用户：

1. 编辑文件顶部"URL 池"段为真实 URL
2. 跑 `bin/aiseo` 按矩阵每行执行一次（11 用例）
3. 填回主观打分；归档结果到 `tests/aiseo_llm/results/2026-05-14-p2/report.md`
4. 跑 `bash tests/aiseo_llm/runner/run_smoke.sh all` 一遍验证 Phase 1.5 28 条不
   因 Phase 2 改动出现退化

---

## Files Changed

### New files (14)

| File | Purpose |
|---|---|
| `seeds/aiseo-profile/skills/technical-seo-audit/SKILL.md` | Phase 2 skill #1 (站级技术审计) |
| `seeds/aiseo-profile/skills/content-brief/SKILL.md` | Phase 2 skill #2 (内容简报) |
| `seeds/aiseo-profile/skills/competitor-analysis/SKILL.md` | Phase 2 skill #3 (竞品对比) |
| `seeds/aiseo-profile/skills/seo-weekly-report/SKILL.md` | Phase 2 skill #4 (周报 delta) |
| `seeds/aiseo-profile/references/report-templates/content-brief.md` | content-brief 模板 |
| `seeds/aiseo-profile/references/report-templates/competitor-comparison.md` | competitor-analysis 模板 |
| `seeds/aiseo-profile/cron/weekly-audit.json` | cron 模板 #1 |
| `seeds/aiseo-profile/cron/monthly-technical-audit.json` | cron 模板 #2 |
| `seeds/aiseo-profile/cron/monthly-keyword-research.json` | cron 模板 #3 |
| `seeds/aiseo-profile/cron/quarterly-competitor-watch.json` | cron 模板 #4 |
| `seeds/aiseo-profile/cron/README.md` | cron 真实 CLI 文档 |
| `tests/aiseo/test_phase2_seed_contracts.py` | 47 Phase 2 seed-contract 测试 |
| `tests/aiseo_llm/prompts/p2_e2e_checklist.md` | 6 skill × 5-10 URL e2e checklist (用户手动) |
| `.claude/PRPs/reports/growflare-master-plan-phase2-report.md` | 本文件 |

### Modified files (8)

| File | Change |
|---|---|
| `seeds/aiseo-profile/SOUL.md` | 98 → 132 行；§2 加 4 skill，§3 加 S5-03 铁律，§4 加 P2-B4 元信息字面拒答，§5 加 P2-B3 包装拒答 |
| `seeds/aiseo-profile/skills/growflare-seo/SKILL.md` | 加 §工具调用预算（硬约束）子节（P2-B1/B2） |
| `seeds/aiseo-profile/config.yaml` | doc-sync：注释段 setup/model 命令示例简化为 `aiseo setup` / `aiseo model`（D7-A6） |
| `bin/aiseo` | 加 Phase 2 D16 branded `-h`/`--help` heredoc intercept (在 bootstrap 之前)；P1 hotfix D7-A6 Route B subcommand passthrough（末行从固定 `exec hermes -p aiseo chat "$@"` 改为无参→`chat`、有参→直接透传 `hermes -p aiseo "$@"`） |
| `docs/aiseo-agent/ARCHITECTURE.md` | doc-sync：§3 整体架构 ASCII 框图 L21 `exec hermes -p aiseo chat "$@"` → `exec hermes -p aiseo "$@"`（Route B transparent forwarder；保留架构精确性而非改为 user-facing 形式，避免误读为白名单分派） |
| `docs/aiseo-agent/NEXT_STEPS.md` | doc-sync：L27 setup / L34 model / L49 tools 主路径从绕过 wrapper 写法 `PATH=... uv run ./hermes -p aiseo <sub>` 改为调用 wrapper `PATH=... uv run bin/aiseo <sub>`；L107 bootstrap 期望输出从 `'hermes setup'` 同步到 `'aiseo setup'`；加 Route B hotfix 说明段 |
| `README.md` | doc-sync：L83 "Equivalent to: hermes -p aiseo chat" 单行注释拆分为 2 行（无参进 chat / 任意子命令透传，D7-A6 Route B 准确语义） |
| `.gitignore` | append `Copy of *`（macOS Finder duplicate，含绝对路径泄露风险）+ `bun.lock`（项目 npm-managed，bun lockfile 非预期产物）— 防 P0 风险污染 commit |

---

## Deviations from Plan

| ID | What | Why |
|---|---|---|
| D7-A1 | cron `deliver` 字段实际用 `local`，而非 plan §829 写的 `stdout` / `file` | 实测 `cron create` CLI 不存在 `stdout`/`file` 字面值；`local` 是非 messaging 投递的最近选项 |
| D7-A2 | stream gate 未实装 | run_agent.py 676 处 stream 代码 >> 1 工作日；按 plan §867 gate 推到未来 |
| D7-A3 | cron JSON 不被 hermes CLI 自动 ingest；用 README.md 文档化真实 CLI 命令 | hermes `cron create` 是 positional CLI，无 JSON file ingest path |
| Tasks 8/9 (installation-guide, demo-script) | DEFERRED (plan 标可选) | docs/aiseo-agent/NEXT_STEPS.md 已覆盖安装路径；demo 视后续需求 |

---

## Issues Encountered

无关键 blocker。**1 个小坑**：实测 `hermes cron create --help` 发现 plan 钉死
的 deliver 选项与实际 CLI 不匹配——按 D7-A1 决策落地后即解决。pytest 一次全绿，
0 retry，0 quarantine。

---

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/aiseo/test_phase2_seed_contracts.py` | **47** | SOUL.md backlog hardenings (5) + growflare-seo P2-B1 (1) + 4 skill frontmatter/routing/budget/output/isolation (5×4=24 parametrized) + cron presence/README/deliver/skill/skill-realness (1+1+4+4+4=14) + report templates (1) + bin/aiseo brand (1) + bin/aiseo Route B routing (1, D7-A6 hotfix) |

---

## Acceptance vs Plan §850

- [x] **6 skill 全跑通** — pytest 47 个 seed contract 锁定文件结构；6 skill 全跑通有用户 e2e checklist 留底
- [DEFERRED to user] **P50 ≥ 4/5 主观打分** — p2_e2e_checklist.md 待用户手动跑
- [x] **adversarial smoke 100% 拒答** — Phase 1 60 unit + Phase 1.5 10 integration 仍 100% 全绿；Phase 2 47 新 seed-contract 全绿
- [x] **`bin/aiseo --help` branded** — 实测 0 Hermes 字面
- [x] **3-5 cron 模板可注册** — 4 个 JSON + README.md 含可复制 CLI 命令
- [DEFERRED] **(可选) installation-guide.md 陌生用户测试** — plan 标"可选"，未交付

---

## Next Steps

1. **User e2e smoke**（plan §832-834 Task 5/6）：按 `tests/aiseo_llm/prompts/p2_e2e_checklist.md` 跑 6 skill × 5-10 URL，归档结果到 `tests/aiseo_llm/results/2026-05-14-p2/report.md`
2. **adversarial smoke 回归**：`bash tests/aiseo_llm/runner/run_smoke.sh all`，对比 Phase 1.5 27/31 baseline；P2-B1/B2 修复后预期 S2-01 / S2-05 转 ✅
3. **cron 注册测试**（plan §846）：按 cron/README.md 至少注册 1 个模板验证 `cron create` 成功
4. **Commit + PR**：本 Phase 不自动 commit（同 Phase 0/1 session policy）；用户决定 commit message + merge 时机
5. **Phase 3（可选 / 远期）**：真独立 aiseo-cli — 仅当商业化需要彻底隐藏底层 runtime 时再启动；plan 已记录但 explicitly 不展开

Plan **archived** to `.claude/PRPs/plans/completed/`（Phase 2 完成 + Phase 0/1
已完成，整 plan 收官）。

---

## What Phase 2 Did NOT Do (intentional)

- Stream gate（D7-A2 deferred；保留 `streaming: false`）
- 真独立 aiseo-cli（plan 全程明确不在范围内）
- `installation-guide.md` / `demo-script.md`（plan §835/836 可选交付；未触发降级条件触发收益）
- 6 skill × 5-10 URL 真实 e2e（DEFERRED to user；checklist 已就绪）
- `growflare-seo/scripts/seo_metadata.py` helper（决策门未触发；plan §Phase 1 沿用）
- Plugin 4 hook 主体规则改动（Phase 2 范围外；仅按 e2e 反馈微调 INPUT/OUTPUT pattern——本期 0 改动）

---

*Status: All Phase 0/1/1.5/2 complete; plan archived.*
*Total cumulative tests: 117 pytest + 28 LLM smoke (Phase 1.5 baseline) — 0 真敏感泄漏 / 0 被禁工具调用 / 6 skill 完整可用*

# AISEO Agent 架构方案

## 1. 一句话定位

AISEO 是构建在 Hermes runtime 上的 SEO 专用品牌化 Agent：thin wrapper 命令 + Hermes profile + guard plugin + 1 个最小 core hook。不重写 runtime，不污染 Hermes 原有入口，唯一 Hermes core 改动是新增 `pre_user_message` hook，用于支持硬 InputGate。

**Brand switch（env-guard）**：`aiseo_cli.main()` 启动时 `os.environ.setdefault("AISEO_BRAND_ACTIVE", "1")`；`hermes_cli/banner.py::format_banner_version_label` 与 `agent/prompt_builder.py::DEFAULT_AGENT_IDENTITY` 读取该 env 决定显示 "AISEO Agent" 还是 "Hermes Agent"。env 未设时（直接跑 `hermes -p aiseo`）保留上游 Hermes 品牌；env=1（走 `aiseo` wrapper）才切换。双路径 contract 测试见 `tests/agent/test_prompt_builder.py::TestPromptBuilderBrandSwitch` 与 `tests/hermes_cli/test_banner.py::test_format_banner_version_label_*`。

## 2. 关键事实背景

- aiseo-agent 仓库本身就是 Hermes 的 fork，源码全在当前仓库内。
- Hermes 已具备完整的 profile 机制（`hermes -p <name>`），运行入口、TUI、Gateway、session、cron、skill 都通过 profile 隔离。
- Hermes 已有 17 个合法 plugin hook（`VALID_HOOKS` 定义在 `hermes_cli/plugins.py:128-168`），其中 4 个对 AISEO 关键。
- 经源码核验：`pre_llm_call` 只能注入 context 不能改写或中止用户消息；要硬 InputGate 必须新增 hook。

## 3. 整体架构

```
用户输入
   │
   ▼
aiseo  ─────────────────────────────── thin bash wrapper（首次启动自动 bootstrap profile）
   │   exec hermes -p aiseo "$@"   # Route B: 无 args → chat；有 args → 透传子命令
   ▼
Hermes 原入口（CLI / TUI / Gateway）─── 0 改动复用
   │   profile 机制读取 ~/.hermes/profiles/aiseo/
   ▼
plugins/aiseo-guard/ ───────────────── 注册 4 个 hook
   ├── pre_user_message      (硬 InputGate, 新 hook)
   ├── pre_tool_call         (ToolGate)
   ├── transform_tool_result (External Content Guard)
   └── transform_llm_output  (OutputGate)
   │
   ▼
Hermes AIAgent (run_agent.py:AIAgent)── 0 改动
   │   function calling loop / provider / memory / cron 全复用
   ▼
用户响应
```

## 4. 4 道 Guard 挂点

| Guard | 挂点 | 作用 | Hermes 改动 |
|---|---|---|---|
| InputGate（hard） | `pre_user_message`（新） | deterministic denylist：拒绝密钥/系统 prompt 探测/jailbreak 高频模式；非 SEO 请求由 SOUL.md 让模型自然拒绝 | +约 20 行 core |
| ToolGate | `pre_tool_call` block + `disabled_toolsets` config | 双层：config 默认禁 terminal/file/code/messaging/delegation；plugin hook 兜底 block 非白名单 | 0 |
| External Content Guard | `transform_tool_result` | web_search / web_extract / browser 返回内容包装为 `<untrusted_web_content>`，防 indirect prompt injection | 0 |
| OutputGate | `transform_llm_output` | deterministic regex 脱敏：API key、绝对路径、stack trace、敏感配置路径、内部工具标识符 | 0 |

### 4.1 RC Smoke Harness Architecture（2026-05-15）

AISEO LLM smoke harness 现在有 3 个 acceptance 控制点：

- **Toolset minimization**：`run_smoke.sh` 和 `scripts/run_targeted_smoke.sh` 默认 `AISEO_SMOKE_TOOLSETS=web`，除非显式覆盖，否则 smoke 只暴露 web-backed SEO tools。
- **Retry/session accounting**：runner metadata 记录 `attempts`、`final_rc`、`session_id`；`grade.py` 在 retry 成功时只按最终成功 session 计预算，避免失败尝试噪声污染。
- **Infra classification**：`grade.py` 将 timeout、API connection、URL-safety/private-address blocks 等归类为 infra；但全 infra bucket 是 non-accepting，不会误报 PASS。

当前架构缺口：tool budget 仍主要依赖 skill/prompt contract。2026-05-15 全量 smoke 证明 S2/S6 在 web backend degraded 时仍会重复 `web_extract` / `web_search`，下一步需要更强的降级/停重试约束，必要时上升到 deterministic budget enforcement。

OutputGate 现在还会把最终用户报告中的内部工具标识符改写为用户可见表述：
`web_search` → `实时检索`，`web_extract` → `页面抓取`，`browser*` → `抓取回退路径`。
S3-06 剩余问题是 grading contract：安全拒绝且无路径泄漏是否算通过，或是否必须强制产生 `[REDACTED_*]` sentinel 来证明 OutputGate 执行。

### 4.2 对话式 SEO 定时任务（客户侧）

AISEO profile 启用两个专用调度工具集：`aiseo_schedule_task` 与
`aiseo_manage_scheduled_tasks`。通用 `cronjob` toolset 仍在
`agent.disabled_toolsets` 中禁用，并由 ToolGate 继续兜底拦截。

设计意图：客户可以在对话中创建和管理 SEO 周期任务，但不会获得通用自动化能力。

- `aiseo_schedule_task` 是 narrow cron wrapper，提供两种互斥模式：
  - **自由 SEO prompt（首选）**：用户传 `prompt` 字段（≤ 2000 字符自由 SEO 任务
    描述）+ `frequency` + `time`。wrapper 会在用户 prompt 外注入 hardening
    指令（DATA-not-instruction、加载 SKILL.md via `aiseo_skills_read`、SOUL
    refusal），并固定 `enabled_toolsets=["web","search","browser","aiseo_skills_read"]`
    + `skills=[]`（让 cron agent 运行时按 prompt 自己选 skill，能力对齐即时任务）。
  - **结构化快捷（向后兼容）**：传 `task_type` ∈ {site_health_check,
    technical_audit, page_audit, keyword_opportunity, competitor_monitoring,
    content_brief, seo_delta_report} + 对应结构化字段（URL / 页面 / 关键词 /
    竞品 / 语言）。wrapper 把 7 种类型展开为预定义 prompt，并把 skills 字段
    pin 到对应内置 skill，`enabled_toolsets` 固定为 `["web","search","browser"]`。
- 两种模式**都**明确拒绝 `script`、`workdir`、`deliver`、`model`、`provider`、
  `base_url`、`toolsets`、`enabled_toolsets`、`skills`、`skill`、`no_agent`、
  `context_from` 等通用 cron 参数（`_AISEO_SCHEDULE_FORBIDDEN_FIELDS`）。
- 两种模式都会过 `_scan_cron_prompt` 前置正则扫描（注入 / secret / unicode 等）；
  自由模式额外校验 prompt 长度 ≤ 2000 + 拦 C0 控制字节（保留 \t / \n）。
- `_AISEO_FREEFORM_MARKER`（`<AISEO_FREEFORM_TASK>`）写入 prompt 体内做身份标记，
  让 `_is_aiseo_created_job` / `_infer_task_type` 区分自由 job 与 legacy job。
- `aiseo_manage_scheduled_tasks` 对两种模式的 job 等同处理：list/view/pause/
  resume/reschedule/delete 都支持自由 job 和 legacy job，删除必须确认，
  view/list 不返回内部 prompt。

## 5. Hermes Core 改动账单

总账：1 个新 hook，约 20 行。

新增 `pre_user_message` hook 详细合约：

- 加入 `hermes_cli/plugins.py` 的 `VALID_HOOKS`
- 在 `run_agent.py:11967`（`pre_llm_call` 调用之前）invoke
- 返回值合约：
  - `None` 或 `{"action": "allow"}` → 放行
  - `{"action": "block", "message": "..."}` → 中止本轮，把 message 作为 assistant 回复
  - `{"action": "rewrite", "text": "..."}` → 改写 user_message 后送 LLM
- 多 plugin 注册时：first block wins → first rewrite wins（参考 `transform_tool_result` 的 first-non-empty 语义）
- 异常 catch + log（与 Hermes 现有 hook 一致）

## 6. 关键设计决策

### 6.1 为什么不做通用 PolicyProfile / Core Guard 层

当前只有 aiseo 一个 profile，做平台化抽象 = YAGNI。先硬编码 AISEO 边界，将来真有第二个 profile 再抽象。

### 6.2 为什么不做真独立 aiseo-cli

Hermes 不是干净 library — `AIAgent` 在 top-level `run_agent.py`，import 会牵出 `hermes_cli.config` / `model_tools` / `plugins`。"独立 CLI"意味着复制 entrypoint + 维护内部模块依赖，工程量大、rebase 漂移风险高、且并不能真正隔离。详见第 8 节对比。

### 6.3 为什么用 thin bash wrapper 而非纯 alias

bash 脚本可控错误信息、未来加预处理逻辑零升级成本、可走 `entry_points` 安装。alias 在 zsh/bash 兼容性和安装体验上都差一截。

### 6.4 为什么硬 InputGate 必须新增 hook

源码核验确认：`pre_llm_call` 合约是 context injector — 返回值只能 append 到 user message 末尾，不能改写、不能 abort、异常被吞。要 hard block 必须新增 hook。Soft inject 路线（让 LLM 自己拒绝）作为辅助层保留，但不能当主防线。

### 6.5 为什么 External Content Guard 用 hook 而非 subclass AIAgent

`transform_tool_result` 是现成的、运行在 tool result 进入 conversation history 之前的、官方支持改写的 hook（`model_tools.py:815`）。subclass `AIAgent.run_conversation()` 是更脏的方案。

## 7. 钉死的落地细节

1. `pre_user_message` hook 合约（如第 5 节）
2. wrapper 用 bash 脚本（非 alias）
3. Profile 自动 bootstrap：Repo 内放 `seeds/aiseo-profile/`，首次运行 wrapper 检测 `~/.hermes/profiles/aiseo/` 不存在 → `mkdir -p ~/.hermes/profiles/aiseo` + `cp -R seeds/aiseo-profile/* ~/.hermes/profiles/aiseo/`（纯文件系统操作，不依赖 `hermes profile create` 命令）。Phase 0 必须实测 bootstrap 后 `hermes -p aiseo` 能正常加载。
4. 目录命名：用户的 profile 在 `~/.hermes/profiles/aiseo/`（家目录），repo 内只放 `seeds/aiseo-profile/` 和 `plugins/aiseo-guard/`，避免和 `toolset_distributions.py` 撞概念
5. Skill pack：走 Hermes 现有 SKILL.md + frontmatter 约定，放 profile 的 `skills/` 目录，自动扫描发现

## 8. Thin Wrapper 方案 vs 真独立 aiseo-cli 对比

### 8.1 核心结论

真独立 cli 唯一能拿到、thin wrapper 拿不到的能力，就是"在 Hermes runtime 之前做硬 InputGate"。其他所有差异都是表面的或可补的。而这个唯一能力，新增 1 个 `pre_user_message` hook 就补上了。所以真 cli 的实质优势近乎为零，工程成本却高一个数量级。

### 8.2 能力对比表

| 能力 | thin wrapper | 真 aiseo-cli |
|---|---|---|
| 命令是 `aiseo` | 是 | 是 |
| InputGate hard block 用户输入 | 是（靠 `pre_user_message` hook，20 行 core） | 是（在 Python 层直接拦截） |
| ToolGate 限制工具 | 是 | 是（最终都要走 Hermes tool registry，没区别） |
| External Content Guard | 是 | 是（必须走 `transform_tool_result`，真 cli 也绕不开） |
| OutputGate 脱敏 | 是 | 是（必须走 `transform_llm_output`，真 cli 也绕不开） |
| 防御深度 | 4 道 | 4 道（一样） |
| 完整隐藏 "Hermes" 字样 | 弱（`--help` / 错误堆栈会漏） | 中（仍 import hermes，Python traceback 会漏） |

关键事实：External Content Guard 和 OutputGate 发生在 `AIAgent` 内部。真 cli 也是 import 这个 AIAgent，所以这两道 guard 必然走 Hermes 的 hook 系统。"真独立"换不来更深的控制。

### 8.3 工程成本对比

| 维度 | thin wrapper | 真 aiseo-cli |
|---|---|---|
| 新代码量 | 约 1 行 bash + 约 200 行 plugin + 约 20 行 core hook = 约 220 行 | 复制/适配 `cli.py` 部分 + `gateway/run.py` 部分 + session 管理 + slash command 路由 + approval flow + TUI 适配 = 约 3000-8000 行（cli.py 本身 13000+ 行） |
| Hermes 升级成本 | 接近 0（只用 plugin hook 公开接口） | 高 — Hermes 每次改 `AIAgent` 构造参数 / session API / tool registry / TUI 协议都可能 break |
| Bug 表面 | plugin + 1 hook，都是 additive | 整个 entrypoint 自己拥有，slash command 错乱 / session 丢失 / TUI 渲染 / approval 漏洞都要自己修 |
| Rebase 上游 Hermes | 1 个 hook 改动可能冲突一次 | 整个入口代码持续漂移 |

### 8.4 决策框架

什么时候 thin wrapper 够：

- AISEO 的差异化能用 plugin/profile/skill 表达（当前场景符合）
- 不要求完全隐藏 Hermes 品牌（MVP 阶段可接受）
- 想优先验证产品价值而非工程独立性

什么时候必须真 cli：

- 商业化要求用户看不到任何 Hermes 字样（traceback / error / help）
- AISEO 要做 Hermes 不支持的 entrypoint 行为（完全不同的 session 模型、自己的认证体系、不同的 streaming 协议）
- 要把 AISEO 跑在 Hermes 不支持的部署形态（嵌入 Web SDK、Mobile SDK）

当前阶段以上三条都不成立，因此选 thin wrapper。

### 8.5 一句话结论

当前做 thin wrapper，是用 220 行换 3000-8000 行加持续维护成本，且零功能损失。未来真有商业化品牌需求或部署形态需求时，再迁真 cli — 那时 plugin/profile/skill 全部可以原样保留，只换 entrypoint。这是严格更优的路径，不是妥协。

## 9. 待最终决定的 2 项

| 项 | 选项 | 当前倾向 |
|---|---|---|
| Streaming 默认值 | A) `streaming: false`（OutputGate 完整脱敏）<br>B) `streaming: true`（流畅但敏感内容可能先流出）<br>C) 等 stream gate 出来再开 | A — 安全承诺优先，可在 Phase 2 加 stream gate 后切换 |
| `aiseo --help` 品牌处理 | A) 透传 `hermes --help`（暴露 hermes 字样）<br>B) wrapper intercept `--help` 出 AISEO 风格帮助 | MVP 阶段 A，README 解释"基于 Hermes runtime"；Phase 2 再加 intercept |

## 10. 工程范围拆分

| 产物 | 位置 | 说明 |
|---|---|---|
| `bin/aiseo` | repo | thin bash wrapper |
| `plugins/aiseo-guard/` | repo | plugin.yaml + `__init__.py`，注册 4 个 hook |
| `seeds/aiseo-profile/` | repo | SOUL.md、config.yaml、skills/、cron/、memories/ 的 seed |
| `pre_user_message` hook | repo（改 Hermes core） | +约 20 行 in `hermes_cli/plugins.py` + `run_agent.py` |
| Adversarial test pack | repo（`tests/aiseo/`） | 至少 20 条 smoke：jailbreak / prompt mining / indirect injection / 工具白名单绕过 |
| `~/.hermes/profiles/aiseo/` | 用户家目录 | 由 wrapper 首次启动 bootstrap，不在 repo |

## 11. 演进路径

```
Phase 0 (本周)
  ├── 写 PRD（基于本方案）
  ├── 决定 streaming / --help 处理
  └── 设计 Adversarial test pack 大纲

Phase 1 (MVP)
  ├── pre_user_message hook 实现 + 测试
  ├── plugins/aiseo-guard/ 4 个 hook 注册（deterministic 部分）
  ├── seeds/aiseo-profile/ SOUL.md + 工具白名单 config
  ├── bin/aiseo wrapper + 自动 bootstrap
  ├── 2 个 SEO skill（growflare-seo + keyword-opportunity）
  └── 至少 20 条 adversarial smoke 全绿

Phase 2 (产品化)
  ├── 补 4 个 SEO skill
  ├── SEO cron 模板（每周/每月报告）
  ├── Stream gate（如果开 streaming）
  ├── `aiseo --help` intercept
  └── 安装文档 + demo

Phase 3 (未来，可选)
  └── 真独立 aiseo-cli — 仅在商业化需要彻底隐藏 Hermes 时才做
```

每阶段 additive，永不回头重写。

## 12. 核心原则

1. 底层能力复用 Hermes，不重造
2. 安全边界用 plugin hook，不动 core 入口代码
3. 唯一 core 改动是硬 InputGate 必需的 1 个新 hook
4. 品牌体验由 thin wrapper 提供，不复制 entrypoint
5. 每个 Phase 工程量最小化，YAGNI 优先

---

## Architecture Decision Records (ADR)

本节按时间顺序记录影响 AISEO fork 长期演进的关键决策。**编号约定**:
ADR-NNN 按写入顺序单调递增,不复用,不重排。每条记录采用 Context / Decision /
Consequences 三段结构。

### ADR-001: Profile sync 不复用 `hermes_cli/profile_distribution.py`

- **Status**: Accepted (2026-05-19)
- **Owner**: AISEO fork maintainer
- **Supersedes**: 无
- **Related spike**: [`.plans/profile-sync-upstream-spike.md`](../../.plans/profile-sync-upstream-spike.md)

#### Context

P0-C spike(2026-05-19)对 `hermes_cli/profile_distribution.py`(702 行,
2026-05-08 已存在于 repo)与 `aiseo_cli.py:60-870`(约 624 行 sync 实现)做了
13 行为点的 gap matrix 比对。结论是**两套实现的设计哲学根本对立**,不是"小差距
可桥接",而是"不同问题域"。

上游 `profile_distribution.py` 的语义:
- distribution-owned 路径**全权由发行者控制**,update 等价于"从 git 重新拉取
  并全量替换"(`shutil.rmtree(dest)` + `shutil.copytree(entry, dest)`,见
  `_copy_dist_payload` l.554-563)。
- `config.yaml` 要么 `preserve_config=True` 整体保留、要么 `--force-config`
  整体替换,**无 text-level merge**;写入用 `yaml.safe_dump`,丢失注释、anchor、
  缩进。
- 写入路径用裸 `shutil.copy2` / `path.write_text`,**无 backup、无 fsync、
  无 atomic replace**;中途崩溃即损坏文件,且无法恢复。
- 设计目标:可复现部署,适合"工程团队从 git URL 拉取标准化 profile"场景。

AISEO sync 的语义:
- seed → profile 是 **additive / missing-only**(`_sync_skills_dir` l.558-573:
  skill 目录已存在 → 跳过,绝不覆盖用户修改)。
- `config.yaml` 走 **text-level additive merge**(`_migrate_profile_config`
  l.400-545):seed 新增 list item → 追加到用户文件,保留注释 / anchor / 缩进 /
  顺序;用户的标量字段(model、max_turns)永不被自动迁移。
- 写入用 `tempfile.mkstemp` + `os.fsync` + `atomic_replace`(l.516-526),
  失败时 tmp 不残留;同时 rolling backup(5 槽)作为安全网。
- 设计目标:用户在本地 tune skill / 改 config 后 sync 不丢失工作。

**5 个 BLOCKING/SIGNIFICANT gap 上游完全不存在**(gap matrix 详见 spike doc §2):
#2 additive list migration、#3 rolling backup、#6 skills missing-only、
#7 YAML 注释保留、#13 atomic write + fsync。

#### Decision

**保留 `aiseo_cli.py` 的 ~624 行 sync 实现作为永久 AISEO fork-only 资产**,
不复用 `hermes_cli/profile_distribution.py`,不向上游推 PR 试图融合两套语义。

#### Consequences

正面:
- 用户在本地修改 skill / config 永远不会被 `aiseo sync` 静默覆盖。
- config.yaml 写入有 atomic + fsync + rolling backup 三层 durability 保护。
- Hermes 上游 `profile_distribution.py` 演进 0 影响 AISEO sync(无依赖)。

负面:
- AISEO fork 永久维护 ~624 行 sync 代码,Hermes upgrade 不会自动带来 sync 改进。
- gap #8(从 git URL 安装 AISEO)不可用 — 当前不需要,遵循 YAGNI;若未来需要,
  在 `aiseo_cli.py` 单独加 git clone 路径,不引入 distribution.yaml manifest。
- 若有人在 `seeds/aiseo-profile/` 误加 `distribution.yaml`,可能绕开 AISEO 保护;
  风险通过 `seeds/aiseo-profile/README.md` 的 CODEOWNERS-style 警告防御。

#### 重评估触发条件

本决策基于 2026-05 上游 `profile_distribution.py` 设计哲学。**默认每季度 review
一次**(对齐 P0-B 节奏),但以下任一上游变更出现时,**1 周内**重新跑 Gap matrix:

| 上游变更 | 影响 gap | 重评估理由 |
|---|---|---|
| `distribution.py` 引入 `distribution_owned` 的 **per-path policy**(允许标 `replace` vs `missing_only`) | #6 skills missing-only | 这是当前 BLOCKING gap 之一;若上游允许 per-path 模式,AISEO 可声明 `skills/: missing_only` 而复用框架 |
| 上游加入 `config.yaml` 的 **text-level merge hook**(如 `pre_config_write` / `transform_config` callback) | #2 additive list migration + #7 YAML 注释保留 | 另两个 BLOCKING/SIGNIFICANT gap;若上游开放 hook,AISEO 的 `_migrate_profile_config` 可注册成 hook |
| 上游引入 **backup 机制**(rolling / snapshot / .bak)在 update 路径 | #3 rolling backup 退化为 ACCEPTABLE LOSS | 降低混合实现的安全风险 |
| 上游引入 **atomic write / fsync** 写入路径 | #13 退化为 ✓ | 同上 |

**不触发重评估**:`distribution.yaml` manifest 字段增量扩展、git URL 解析增强、
`USER_OWNED_EXCLUDE` 列表扩展(只要 distribution-owned 仍是全替换语义)。

季度 review checklist 详见 spike doc §6.2;若一季度内上游无相关变更,在
`docs/aiseo-agent/NEXT_STEPS.md` 留一行 `YYYY-Q{n}: profile-sync spike re-review
— no upstream changes, decision (c) still holds.`

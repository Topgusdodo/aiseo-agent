# 多租户 SaaS 化设计

> **状态**：Draft / 讨论中
> **日期**：2026-05-26
> **范围**：把 AISEO Agent（Hermes fork）从「单运营者单 profile」演进为「多客户 SaaS」的架构方案、现成能力盘点、硬约束与演进路线。
> **同级文档**：`dataforseo-plugin.md`、`openai-api-server.md`、`streaming-support.md`、`profile-sync-upstream-spike.md`

---

## 0. TL;DR

1. **不要现在全盘换框架。** Hermes 的 profile 系统已经把多租户的「隔离 + 开通 + 产品层下发」做到基本开箱；真正缺的只是上层「控制面」（路由 / 租户注册表 / 计费 / 鉴权），而这部分换任何工具都得自建。
2. **最优路线 = 三层混合**：自建薄控制面 + Hermes fork 留作 agent runtime（4-guard 安全层 + SEO 技能是竞品无等价物的护城河）+ 通用基建逐步外包（记忆→Zep，定时→Trigger.dev）。
3. **隔离单元 = 一租户一 `HERMES_HOME`。** 这是 Hermes 原生能力，已被「飞书 gateway vs 终端 CLI 状态分叉」实证。
4. **两个会丢租户数据的实施陷阱**（见 §5）：distribution repo 误带 `cron/` 会清掉租户定时任务；`--force-config` 会整体覆盖租户 config。

---

## 1. 背景与目标

AISEO 计划接入 SaaS、服务多个客户。每个客户需要**独立**的对话记忆、定时任务、API 凭证、会话历史、平台绑定（如飞书 bot），彼此严格隔离；厂商集中维护「产品层」（系统提示/人格、技能、安全防御规则）并能统一升级下发到所有租户。

核心问题：**用现成的 Hermes 能力能支撑到什么程度？缺口怎么补？要不要换更专业的工具？**

---

## 2. 现状盘点：Hermes 现成能力 vs 缺口

### 2.1 决定隔离的底层机制（本次会话亲自核实）

- 所有 per-profile 状态跟随 `HERMES_HOME`：`get_hermes_home()` 读进程级环境变量，未设则 fallback `~/.hermes`（`hermes_constants.py:30-68`，并在 `active_profile≠default` 但 `HERMES_HOME` 未设时打 stderr 警告 `:34-66`）。
- cron 落点 = `$HERMES_HOME/cron/jobs.json`，模块级常量、import 时一次性固定（`cron/jobs.py:38-40`）。
- profile 解析在所有模块导入前完成：`_apply_profile_override()` 读 `-p/--profile`，否则读 `~/.hermes/active_profile`，再 `os.environ["HERMES_HOME"]=...`（`hermes_cli/main.py:119-205`，active_profile 兜底 `:161-173`，设值 `:191`）。
- `aiseo` wrapper 把任意参数透传成 `hermes -p aiseo <args>`（`aiseo_cli.py:1181-1185`）。
- **推论（已实证）**：一个进程一生只有一个 `HERMES_HOME`。"飞书 gateway 与终端 CLI 看不到彼此的 cron" = 两者 `HERMES_HOME` 不同。统一靠 systemd unit 显式 `-p <profile>` + `Environment=HERMES_HOME=.../profiles/<profile>`（不要只依赖全局 `active_profile`）。

### 2.2 开箱即用能力（行号已核实 2026-05-26）

| 能力 | 机制 | 证据 |
|---|---|---|
| 租户隔离 | `hermes profile create/clone/delete`，每 profile 独立 HERMES_HOME（config/memory/sessions/cron/auth/pairing 全隔离） | `hermes_cli/profiles.py:540`(create)/`:718`(delete)/`:1387`(resolve_profile_env) |
| 多实例并发 | 每 profile 独立 `gateway.pid` + 锁 + per-profile systemd/launchd service name | `gateway/status.py:7-9,45-47`、`hermes_cli/gateway.py:1259`(_profile_suffix)/`:1314`(get_service_name)/`:1944`(get_launchd_plist_path) |
| 产品层下发 | `hermes profile install <git-url>` + `install_distribution()`，git-based，全量替换 dist-owned、保留 user-owned | `hermes_cli/profile_distribution.py`（见 §5，核实） |
| per-user session 隔离 | gateway `group_sessions_per_user=True`（默认隔离），`build_session_key` 的 session key 含 user_id | `gateway/session.py:576,594` |
| per-tenant memory | Honcho 按 user_id 路由；OpenViking `X-OpenViking-Account/User` headers | `plugins/memory/honcho/__init__.py:362`、`plugins/memory/openviking/__init__.py:111-114` |
| pairing 审批 / 白名单 | pairing code 二步授权 + `allow_from` | `gateway/pairing.py:47`(PAIRING_DIR via get_hermes_dir) |

### 2.3 缺口（必须自建薄控制面，换工具也绕不开）

- **路由层**：tenant → profile/容器，没有单一入口自动路由。
- **租户注册表 + 自动开通 API**：profile CRUD 是 CLI，无 REST 管理面。
- **计费 / 用量聚合**：无 per-tenant 计量对账。
- **多租户鉴权**：API server 仅单 Bearer token，无 per-tenant JWT/OIDC。
- **per-tenant 配额**：无 CPU/内存/速率配额。
- **文件系统隔离**：profile **不 sandbox 文件系统** → 强隔离必须靠容器/VM。

---

## 3. 目标架构：三层混合

```
                  ┌──────────────┐
  客户 ─────────▶ │   控制面      │  按 API key / 子域名 / JWT → 租户
 (API/飞书/Web)   │ (自建·薄)     │  租户注册表 / 开通 / 计费 / 凭证隔离
                  └──────┬───────┘
            ┌────────────┼────────────┐
            ▼            ▼            ▼
       ┌────────┐   ┌────────┐   ┌────────┐   运行时（Hermes fork·不动）：
       │租户A    │   │租户B    │   │租户C    │   · HERMES_HOME=/data/tenants/<id>
       │gateway  │   │gateway  │   │gateway  │   · 4-guard 安全层（护城河）
       └────────┘   └────────┘   └────────┘   · SEO 技能 + dataforseo 插件
            └────────────┴────────────┘        · profile install/distribution 下发产品层
                         │
            通用基建（外包托管）：记忆→Zep    定时→Trigger.dev
```

**分层依据**：护城河（SEO 确定性安全 + 技能）换框架必重写、竞品无替代 → 留；隔离/开通/下发 Hermes 已有 profile/distribution 骨架 → 不换；记忆/定时是通用基建、自造脆弱 → 外包。

---

## 4. 隔离模型

- **一租户 = 一 `HERMES_HOME`**（`/data/tenants/<tenant_id>/`，或 `~/.hermes/profiles/<tenant>`）。
- 每租户一个 gateway 进程（Phase 1）或容器（正式）。
- cron/memory/auth/pairing/sessions 全部 profile-scoped，物理隔离，零跨租户共享。
- **明确否决「单进程多租户」**：`get_hermes_home()` / `JOBS_FILE`（`cron/jobs.py:38-40`）/ `PAIRING_DIR`（`gateway/pairing.py:47`）都是进程级、import 时固定；per-request 切 profile 要重写状态层寻址（30+ 调用点）并破坏 prompt-cache 不变量，风险极高。

---

## 5. 产品层下发：distribution + sync 分工（含数据丢失陷阱，已核实）

### 5.1 陷阱 A — distribution 会清租户 `cron/`

- `cron` 在 `DEFAULT_DIST_OWNED`（`profile_distribution.py:85-92`），**不在** `USER_OWNED_EXCLUDE`（`:98-117`）。
- `_copy_dist_payload`（`:541-563`）遍历 staged 源**全部顶层条目**，对目录先 `shutil.rmtree(dest)` 再 `copytree`（`:555-556`）。
- **后果**：只要 distribution repo 含 `cron/`，`hermes profile update` 会删掉租户运行时的 `cron/jobs.json`。
- **反直觉**：`_copy_dist_payload` **不消费 manifest 的 `distribution_owned` 字段**，复制只由「repo 内容 + `USER_OWNED_EXCLUDE` 黑名单」决定。→ 在 manifest 移除 `cron` from `distribution_owned` **是无效防护**。

> **硬规则（MUST NOT）**：distribution repo 严禁包含 `cron/`、`memories/`、`.env`、`auth.json` 等任何运行时/用户数据。唯一可靠护栏是「源里没有」。（更彻底方案：fork 改 `USER_OWNED_EXCLUDE` 把 `cron` 加进去——影响上游常量，非必要不做。）

### 5.2 陷阱 B — `--force-config` 是整体覆盖

- `config.yaml` 在 dist-owned，但 update 默认 `preserve_config = not force_config`（`:666`），目标已存在则跳过（`:549`）→ 默认保留租户 config。
- `--force-config` 走 `shutil.copy2`（`:562-563`）= **整体覆盖**，会清掉租户个性化（plan 限额、手加的 `prompt_caching`/`tool_loop_guardrails`）。
- → `--force-config` **不能**用来「安全下发新 toolset/plugin」。

### 5.3 结论：不是二选一，是互补

| 下发什么 | 用什么 | 为什么 |
|---|---|---|
| SOUL.md / skills / mcp.json / guard 配置（文件层） | **distribution**（`profile update`，repo 排除运行时数据） | 全量替换 dist-owned 正合适（租户不该改） |
| config 的 toolset/plugin/防御列表项 | **保留 `aiseo sync` 的 additive merge**（`_migrate_profile_config` + `SEED_TRACKED_LIST_FIELDS`，`aiseo_cli.py:87-91`） | 只追加新安全项、保留租户其余 config，带滚动备份 |

- **短期**：distribution（文件层）+ 现有 `aiseo sync` additive merge（config 层）并行，各管一段。
- **长期（更优雅）**：给 distribution 加第三种 config 模式 `merge`（在 preserve/force 之外），把 `_migrate_profile_config` 的 additive 逻辑移植进去，`hermes profile update --config-merge` 统一入口。YAGNI——租户多了再做。
- 印证 **CLAUDE.md ADR-001**：profile sync 与 distribution 互补不替代（语义对立：missing-only/additive vs 全量替换）。
- **SaaS 安全要点**：防御项必须「强制下达全租户且租户关不掉」——additive merge 每次补回缺失项，精准满足；`--force-config` 因全覆盖会误伤，做不到外科级强制。

---

## 6. 外包轨（可后置，不阻塞主线）

- **记忆 → Zep**：时序图记忆贴合 SEO「排名/竞品随时间变」数据；$25 起全功能；可 BYOC 自托管。顺带消除 cron `skip_memory=True` + 禁 `file` toolset 导致要预读 `MEMORY.md` 的 hack。接入点：`agent/memory_provider.py` 接口 + `plugins/memory/`，按 `tenant_id` namespace。
- **定时 → Trigger.dev**：Apache 2.0 可自托管；Waitpoint 贴合 dataforseo `tasks_post`+polling 长轮询。先与 Hermes cron 并存验证。

---

## 7. 竞品决策（为什么不全盘换）

- **LangGraph Platform**：唯一原生全覆盖（`assistants`/`threads`/`crons`/`store` by user_id），但要重写 AIAgent loop + 重建 4-guard，托管有锁定 → 迁移代价高，不现在做。
- **Letta / Google ADK+Vertex / Bedrock AgentCore**：强，但要么重写、要么强绑 GCP/AWS。
- **CrewAI / AutoGen**：解决多 agent 协作编排，非多租户隔离基建，方向不对。
- **红线（MUST NOT）**：① 别押 OpenAI Assistants API（2026-08-26 永久下线）；② 别用 Dify / n8n **开源版**做多租户 SaaS（许可证明文禁止，需买 Enterprise）。
- **规模阈值**：< ~500 活跃租户前不需要重型多租户平台；当前量级用「profile 多实例 + 薄控制面」足够，过早上 LangGraph/AgentCore 是过度工程。

---

## 8. 演进路线

| 阶段 | 目标 | 用什么 | 代码量 |
|---|---|---|---|
| **Phase 0** | 固化单租户基线：飞书+终端稳定绑同一 profile | systemd unit 显式 `-p` + `HERMES_HOME` | 0 |
| **Phase 1** | 手动多租户 PoC：开 2-3 个租户验证隔离 | `hermes profile create <t> --clone --clone-from aiseo` + per-profile `gateway install`（剧本见 §12.C） | ~0 |
| **Phase 2** | 产品层下发：一条命令滚动升级所有租户 | seed→distribution repo（排除 cron）+ aiseo sync config merge | 中 |
| **Phase 3** | 薄控制面：自动开通 + 路由 + 凭证隔离 | 租户注册表 + 封装 `install_distribution()` + 路由层 | 大（自建） |
| **Phase 4** | 容器化 + 运维：计费/休眠/监控 | 每租户容器（因 profile 不 sandbox fs） | 大 |
| 并行轨 | 记忆→Zep、定时→Trigger.dev | adapter | 可后置 |

---

## 9. 硬约束清单

**MUST**
- 一租户一 `HERMES_HOME`；正式上线用容器隔离（profile 不 sandbox 文件系统）。
- 每个 gateway 进程显式 `-p <tenant>` + `Environment=HERMES_HOME=...`，不依赖全局 `active_profile`。
- config 安全项（disabled_toolsets / aiseo-guard）走 additive merge 强制下达。
- 每租户独立 bot token（Hermes 有 token 冲突检测会拦）。

**MUST NOT**
- distribution repo 含 `cron/`、`memories/`、`.env`、`auth.json`。
- 用 `--force-config` 下发配置（整体覆盖、误伤租户个性化）。
- 全盘换 LangGraph；押 Assistants API；用 Dify/n8n 开源版做多租户。
- 单进程多租户 / per-request 切 profile。

---

## 10. 待定决策点

1. **接入面（方向：飞书 + SaaS 网站并存，2026-05-26）**：飞书 bot per 租户先行（MVP，复用现有 pairing）；SaaS 网站经统一 OpenAI 兼容 API（见 `openai-api-server.md`，API key 即租户标识）+ Web 控制台接入。两路**共用同一租户 profile/HERMES_HOME**，路由层需同时支持「飞书事件 → 租户 gateway」与「API key → 租户 gateway」。具体 Web/API 形态待定。
2. **隔离粒度起点**：进程 per 租户（Phase 1 验证）→ 容器 per 租户（正式）。
3. **DataForSEO 凭证**：每租户自带账号 vs 厂商共享账号按租户计量。
4. **SOUL.md 是否 per-租户 white-label**：当前建议 YAGNI 全共享；未来若做，用「共享安全基底 + per-tenant 可覆盖片段」。

---

## 11. 下一步

- [x] 复核 §2.2 行号（2026-05-26 已核实；唯一修正：`get_launchd_plist_path` 在 `gateway.py:1944`，systemd service name 在 `:1259`/`:1314`）。
- [x] distribution 改造方案 + `distribution.yaml` 草案就绪（§12.A）。
- [x] 薄控制面 + 开通流程 + 租户注册表 schema 就绪（§12.B）。
- [x] Phase 1 实测剧本就绪、命令 flag 已核实（§12.C）。
- [x] **Phase 0 单租户基线已验证**（2026-05-26 Vultr 生产）：`hermes-gateway-aiseo.service` enabled+active、`Linger=yes`、ExecStart `--profile aiseo` + `Environment=HERMES_HOME=/root/.hermes/profiles/aiseo`（双重显式绑定，不依赖 `active_profile`——即使 active_profile=default 也铁定绑 aiseo，见 `main.py:147-159`）→ 重启/崩溃/登出自动以 aiseo 恢复，无分叉风险。**此 unit 即 §9「每 gateway 显式 -p + HERMES_HOME」硬约束的活样板，Phase 3 开通脚本生成的 per-tenant gateway unit 应照此形态。**
- [x] **Phase 1 隔离实测通过**（2026-05-26 本地 macOS 验证，机制与机器无关）：`aiseo cron list` 仅含 aiseo 的 3 个 job、`tenant-test` 仅含自己的 1 个；两个 `jobs.json` 物理隔离；`delete --yes` 干净回滚。**额外实证**：① `--clone` 不复制 `cron/`（tenant-test 克隆自 aiseo 但 cron 为空，未继承 aiseo 的 freeform job）→ §12.C 隔离前提成立；② aiseo 的 `jobs.json` 中既有终端建的 job、又有 `origin.platform=feishu` 的 job → 印证飞书 gateway 已与终端共享 aiseo profile（排障结论闭环）。
- [ ] 实施 distribution 时：把 seed 的 4 个 cron 模板移到 `references/cron-templates/`；repo 加 `.gitignore`（`cron/`、`memories/`、`.env`）+ CI 顶层目录白名单校验。
- [x] 已加入 CLAUDE.md 的 `.plans/` 文档清单（`CLAUDE.md:20-21`）。

---

## 12. 附录：可执行落地材料（2026-05-26 team 产出，行号已核实）

### 12.A distribution repo 改造（seed → distribution）

**`seeds/aiseo-profile/` 顶层条目判定**（依据 `_copy_dist_payload` 遍历 repo 全部顶层条目 + `USER_OWNED_EXCLUDE`，`profile_distribution.py:541-563`/`:98-117`）：

| 条目 | 进 repo？ | 说明 |
|---|---|---|
| `SOUL.md` / `skills/` / `references/` / `README.md` | ✅ | 产品层；update 时全量替换（目录级 rmtree+copytree） |
| `config.yaml` | ✅（update 默认 preserve，`:549`） | 仅作 fresh-install baseline；增量靠 `aiseo sync` |
| **`cron/`** | ❌ **严禁** | 在 DEFAULT_DIST_OWNED、不在 USER_OWNED_EXCLUDE → update 会 rmtree 租户 `jobs.json`。现有 4 个 cron 模板移到 `references/cron-templates/` |
| **`memories/` / `.env` / `auth.json`** | ❌ **严禁** | 运行时 / 用户数据 |

护栏：distribution repo 加 `.gitignore`（`cron/`、`memories/`、`.env`）+ CI 校验顶层目录白名单。

**`distribution.yaml` 草案**：

```yaml
name: aiseo-agent
version: "0.13.0"
description: "AISEO Agent — SEO 策略/技术审计/内容顾问（含 4-guard 安全层 + 6 SEO 技能 + DataForSEO）"
hermes_requires: ">=0.13.0"   # ⚠️ 必须 ≥ 引入 pre_user_message hook 的 Hermes 版本，否则 InputGate 静默失效
license: "Apache-2.0"
env_requires:
  - {name: DATAFORSEO_BASE64,  required: false, description: "base64(login:password)"}
  - {name: DATAFORSEO_SANDBOX, required: false, default: "0"}
  - {name: ANTHROPIC_API_KEY,  required: false, description: "LLM provider key（名随 provider 变，aiseo setup 写入）"}
distribution_owned:   # 仅文档性，_copy_dist_payload 不消费；真正护栏=repo 不含 cron/memories/.env
  - SOUL.md
  - config.yaml
  - skills
  - references
  - README.md
  - distribution.yaml
```

`env_requires` **有效**：`_copy_dist_payload:566-569` 据此自动生成 `.env.EXAMPLE`。env 名核实：`plugins/dataforseo/plugin.yaml:14-15`、`hermes_cli/auth.py:282`(ANTHROPIC)/`:1440`(OPENAI)。

### 12.B 薄控制面

**可 import 的开通接口（签名已核实）**：
- `create_profile(name, clone_from, clone_all, clone_config, no_alias, no_skills)` → `profiles.py:540`
- `install_distribution(source, name, force, create_alias)` → `InstallPlan`，`profile_distribution.py:582`
- `delete_profile(name, yes)` → `profiles.py:718`：**自动停 gateway + 清 systemd/launchd + rmtree + 重置 active_profile**；但**不**通知注册表 / 撤飞书 bot / 清 secret manager / 无「暂停」语义。

**开通流程**：分配 `HERMES_HOME=/data/tenants/<id>` → `create_profile`/`install_distribution` → 注入 per-tenant `.env`（凭证从 secret manager，不落 repo）→ `aiseo sync` 强制 additive config merge → `hermes -p <id> gateway install`（显式 HERMES_HOME；service name 自动派生 `hermes-gateway-<id>`，`gateway.py:1314`）→ 注册表登记。

**租户注册表最小 schema**：`tenant_id`(PK，正则 `^[a-z0-9][a-z0-9_-]{0,63}$`) / `hermes_home` / `profile_name` / `distribution_src`(git url#ref) / `status`(active|suspended|deleted) / `plan` / `llm_provider` / `secret_ref`(secret manager 路径，不存明文) / `dataforseo_mode`(shared|byoa) / `gateway_addr` / `gateway_service` / `feishu_app_id` / `created_at` / `updated_at`。

**接入面 / 路由**：
- 起步=**飞书 bot per 租户**（零路由代码；每租户独立 `FEISHU_APP_ID`+`SECRET`，飞书侧天然隔离 + pairing 审批；`gateway.py:1521-1529`，app_id 冲突检测 `feishu.py:1599`）。
- 扩展=**统一 OpenAI 兼容 API**（薄反代按 `Authorization: Bearer` 查注册表 → 路由到对应 tenant gateway；现成 `api_server.py`，单 key `:594`，多租户每 gateway 配不同 key 由反代注入）。
- 暂停≠删除：暂停=注册表置 `suspended` + `systemctl stop`（保留目录）；删除=`delete_profile --yes`（不可逆）。

### 12.C Phase 1 隔离实测剧本（flag 已核实，可直接在 Vultr 执行）

> 关键修正：`hermes profile create` 真实 flag 是 `--clone --clone-from <src>`（`main.py:11457-11470`）。`--clone` 复制 config/.env/SOUL/skills + memories 两文件，**不复制 `cron/`**（`_CLONE_SUBDIR_FILES`，`profiles.py:62-65`）——隔离前提。`hermes -p aiseo cron` CLI **可用**（disabled_toolsets 的 `cronjob` 只禁 LLM 工具层、不禁 CLI）。

```bash
# 1. 从 aiseo 克隆开租户（不带 cron）
hermes profile create tenant-test --clone --clone-from aiseo

# 2. 两个 profile 各建一个探针 cron（99h/88h 不会真触发）
hermes -p aiseo       cron create "every 99h" "probe-aiseo"  --name isolation-probe-aiseo
hermes -p tenant-test cron create "every 88h" "probe-tenant" --name isolation-probe-tenant

# 3. 隔离判定：两个 list 互不包含对方 job = 成立
hermes -p aiseo       cron list
hermes -p tenant-test cron list

# 4. 物理路径判定：两个 jobs.json 各含各的
cat ~/.hermes/profiles/aiseo/cron/jobs.json
cat ~/.hermes/profiles/tenant-test/cron/jobs.json

# 5. 清理（--yes 自动停 gateway；aiseo 数据不受影响）
hermes profile delete tenant-test --yes
ls ~/.hermes/profiles/tenant-test/ 2>&1   # 预期：No such file or directory
```

判定：aiseo list 无 tenant 的 job、tenant list 无 aiseo 的 job、两 `jobs.json` 路径不同 → **隔离成立，回填 §11**。只测 cron 隔离不起 gateway，无 bot token 冲突风险；所有命令显式 `-p` 规避 `active_profile` 干扰。

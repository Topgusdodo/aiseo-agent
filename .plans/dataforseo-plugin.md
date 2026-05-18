# DataForSEO 插件 — aiseo-agent 集成计划

> **Status: IMPLEMENTED (2026-05-15, v0.1) — 本文档为历史设计 RFC，不再代表当前实现**
>
> 关键过时点：本文档全文用 `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD` 两个 env var，
> 但**最终落地合并为单一** `DATAFORSEO_BASE64`（precomputed `base64(login:password)`），
> 与 sibling aiseo-api/probe Go 服务保持一致。按本文档旧变量名配置**不会生效**。
>
> 当前权威来源：
> - 实施报告：`.claude/PRPs/reports/dataforseo-plugin-report.md`
> - 插件契约：`plugins/dataforseo/plugin.yaml`
> - 服务器配置 SOP：`docs/aiseo-agent/DEPLOYMENT.md`
> - env 模板：`.env.example` §"DATAFORSEO API"

## 状态
- **决议**：经过 5 轮双方讨论（Claude + GPT）+ 2 轮 code-review 后锁定（2026-05-15）
  - v1 → v2：吸收 reviewer 第一轮 9 项 finding（2 CRITICAL / 4 HIGH / 3 MEDIUM）
  - v2 → v3：吸收 GPT 第二轮 4 项必修 + 5 项补强 + reviewer 第二轮 3 项 + 翻译统一 + 新增接口契约附录
- **分支**：`feat/aiseo-phase2`
- **日期**：2026-05-15
- **阶段**：v0.1（5 个暴露给 LLM 的工具；完整 client 底层实现）

---

## 动机

aiseo-agent（Hermes fork）内置 6 个 SEO 技能 —— `keyword-opportunity`、`competitor-analysis`、`content-brief`、`growflare-seo`、`technical-seo-audit`、`seo-weekly-report` —— 其工作流目前仅依赖 `web_search` 和 `web_extract`。这会产生非结构化的 SERP 片段和 HTML：可用于启发式分析，但缺少：

- 精确的关键词搜索量 / CPC / 竞争度
- 结构化的 SERP 特征（PAA、knowledge graph、rich snippets）
- 详尽的 on-page 审计（Lighthouse、schema、hreflang、可索引性）
- 外链情报

[DataForSEO](https://dataforseo.com) 在一套 Basic-Auth API 下提供 210+ 个结构化 SEO endpoint，并附带免费 sandbox 层。本计划将 DataForSEO 集成为结构化数据源，同时刻意保持 LLM 工具表面狭窄。

---

## 范围

### 范围内（v0.1）

- 新插件：`plugins/dataforseo/` —— 独立（standalone，需在 profile `plugins.enabled` 列表中启用）
- **暴露给 LLM 的 5 个工具**：

| 工具 | 模式 | 用途 |
|---|---|---|
| `dataforseo_serp_google` | Standard 默认；Live opt-in | Google organic SERP |
| `dataforseo_onpage_summary` | Standard async（`crawl_progress` 轮询，sync handler 直接等待，thread 仅做超时硬上限） | 站点爬取 + on-page 审计 |
| `dataforseo_keyword_volume` | Standard 默认（task_post→tasks_ready→task_get 完整流程）；Live opt-in | Google Ads 搜索量 + CPC（批量 ≤1000） |
| `dataforseo_labs_keyword_ideas` | Live only | 关键词扩展 + 难度 |
| `dataforseo_backlinks_summary` | Live only | 域名外链概览 |

- 共享 `DataForSEOClient`（`client.py`）处理 4 种模式：
  1. Basic Auth + `{tasks:[...]}` 信封（约 80% 的 endpoint）
  2. `tasks_ready` 轮询，用于 Standard async（**必须按当前 task_id 过滤**，避免并发任务串扰）
  3. `crawl_progress` 轮询，用于 On-Page（特例，不是 `tasks_ready`）
  4. Live-only 快速路径（无 task 生命周期），用于 Labs / Backlinks / DomainAnalytics / ContentAnalysis
- 通过 `DATAFORSEO_SANDBOX=1` 环境变量切换 sandbox
- 凭证脱敏：login/password 永不出现在日志、错误或 LLM 输出中

### 范围外（按设计延后）

- 剩余约 205 个 endpoint —— 若未来某个技能需要，可新增内部 client 方法，但**绝不**在未重新评估工具表面影响的情况下注册为 LLM 工具
- DataForSEO MCP bridge（TypeScript）—— 不同的架构路径
- 额外的技能重写（v0.1 仅更新 `keyword-opportunity`）
- 成本追踪面板或配额护栏（待成本成为问题时再做）

### 为何只暴露 5 个工具

- **工具表面退化**：BFCL benchmark GPT-4o 准确率 **43% → 2%**（4 → 51 工具）；MCPVerse Claude-4-Sonnet **62.3% → 44.2%**（220 → 550 工具）；GitHub MCP **95% → 71%** 选择准确率
- **aiseo 技能审计**：12 个 board 中仅 SERP / On-Page 被所有技能引用；8 个 board 完全未使用
- **DataForSEO 官方 MCP server** 也仅暴露 84 个工具，79% 集中在 5 个核心 board
- **Token 成本**：210 schema × ~300 tokens ≈ 63K tokens 永久驻留在 system prompt

---

## 架构

### 文件布局

代码结构参照 `plugins/spotify/`（模块化拆分：`client.py` + `tools.py`）。**但 `plugin.yaml` 的 `kind` 不沿用 Spotify** —— Spotify 用 `kind: backend` 自动加载，我们明确避免。省略 `kind` 默认为 standalone，与 `plugins/disk-cleanup/` 一致。

```
plugins/dataforseo/
├── plugin.yaml      # manifest: 省略 `kind` (=standalone), provides_tools (5), requires_env (元数据)
├── __init__.py      # register(ctx) 循环 5 工具, toolset="dataforseo"
├── client.py        # DataForSEOClient: sync httpx + 4 轮询模式 + sandbox + 脱敏
└── tools.py         # 5 schema + handler + _make_handler() factory
```

### plugin.yaml 形态

```yaml
name: dataforseo
version: 0.1.0
description: "DataForSEO API integration — 5 SEO data tools..."
author: aiseo-agent
# Do NOT add `kind: backend` — that's Spotify's auto-load pattern
# Omitting `kind` defaults to standalone (opt-in via plugins.enabled)
provides_tools:
  - dataforseo_serp_google
  - dataforseo_onpage_summary
  - dataforseo_keyword_volume
  - dataforseo_labs_keyword_ideas
  - dataforseo_backlinks_summary
requires_env:                  # metadata only — runtime gate lives in check_fn
  - DATAFORSEO_LOGIN
  - DATAFORSEO_PASSWORD
```

### 为何用 plugin 而非 tools/

依据 `AGENTS.md:266-270` 与 `:519-524`：第三方供应商集成必须位于 `plugins/` 下，且不得修改 aiseo / hermes 核心（原文："plugins MUST NOT modify core files" —— 插件不得修改核心文件）。

### 启用语义 vs 凭证 gating（两层概念分开）

- **第一层：插件启用** —— `seeds/aiseo-profile/config.yaml:plugins.enabled` 列出 `- dataforseo`。这意味着 **AISEO profile 默认会加载 dataforseo 插件**（不是用户运行时手动 opt-in，而是 profile 维护者预先决定）。fork 用户若不想要此插件，需自行从 `plugins.enabled` 移除。
- **第二层：工具可用性** —— 即使插件加载，没有 `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` 时，`check_fn=_check_dataforseo_available()` 返回 `False`，5 个工具在 tool registry 中**置灰**（visible but not dispatchable）。
- **结论**：profile 决定"是否暴露这套工具"，环境变量决定"是否真能调用"。两者解耦。

### 运行时闸控（2 层 gate）

1. `check_fn=_check_dataforseo_available()`：注册时绑定；调度前评估；缺凭证返回 `False` → 工具置灰
2. 每个 handler 在第一行做防御性 `os.getenv` 检查 → 缺凭证抛 `DataForSEOAuthRequiredError`

源码核实：`requires_env` 在 `plugin.yaml` 仅为元数据（`hermes_cli/plugins.py:256, 1036` 仅存储进 dataclass，从不阻塞 load）。Spotify 也是 2 层 gate 模式（`_check_spotify_available()` + `SpotifyAuthRequiredError`）。

### Handler 返回值约定（仓库标准）

**所有 handler 必须返回 JSON 字符串**，由 `tools/registry.py:537-558` 提供的 helper 包装：

```python
from tools.registry import tool_result, tool_error

# 成功：直接 dump DataForSEO 返回的 envelope（{status_code, tasks: [...]}）
return tool_result(payload)
# ⚠️ tool_result(data=X, success=True) 会被 tools/registry.py:561 的 `if data is not None`
# 短路，success=True 字段会被静默丢弃。要包装额外字段时全部走 kwargs 并避开 `data` 关键字：
#   return tool_result(success=True, results=payload)   # ✅ 正确
#   return tool_result(data=payload, success=True)      # ❌ 错误：success 丢失
# 推荐直接 tool_result(payload) —— DataForSEO envelope 自带 status_code，无需再包一层。
# 错误：
return tool_error("DataForSEO credentials missing", code=401)
```

`_make_handler()` factory（见下节）的内层 `_handler` 必须**始终**用 `tool_result()` / `tool_error()` 包装，禁止直接返回 dict。这与 `plugins/spotify/tools.py:17` 的导入约定一致。

### sync vs async client

- `client.py` 使用 **sync httpx**（与 `plugins/spotify/client.py` 一致）
- 5 个工具中 4 个在 <5s 内完成；sync 可接受
- **OnPage 长轮询的处理**：`dataforseo_onpage_summary` 的 `crawl_progress` 轮询最长 300s。**`is_async=True` 不可用**（`tools/registry.py:384-386` 显示 `is_async=True` 时 registry 会执行 `_run_async(entry.handler(...))`，要求 handler 返回 coroutine —— sync handler 配 `is_async=True` 会运行时炸）。
- **采用方案**：handler 保持 sync 直接轮询。agent 框架已在 `await asyncio.to_thread(server.dispatch, ...)`（参考 `tui_gateway/ws.py:159`）上下文里调度 dispatch，**主 asyncio 事件循环天然不被阻塞**——这与 handler 内部是否 thread 包装无关。
- **是否在 handler 内开线程**：可选。thread 包装的真实价值**仅限于** (a) 通过 `thread.join(timeout=300)` 强制超时控制（防 `crawl_progress` polling 卡死），(b) 测试时隔离轮询逻辑。**handler 在 dispatch 线程内必然 sync 等待结果**（`tools/registry.py:387` 显示非 async 分支直接 `return entry.handler(args, **kwargs)`，无 executor），整个调用阻塞直至 polling 完成或超时——这是 sync handler 设计的天然权衡，不要在文档里宣称"非阻塞后台任务"。
- 每个工具的默认超时：60s（SERP / Keywords / Labs / Backlinks）/ 300s（OnPage）
- 429 退避：尊重 `X-RateLimit-Remaining` 响应头；指数退避（5s、10s、20s），最多 3 次重试

### `_make_handler()` factory 签名

```python
# In plugins/dataforseo/tools.py
from pydantic import ValidationError
from tools.registry import tool_result, tool_error
from plugins.dataforseo.client import DataForSEOClient, DataForSEOAuthRequiredError, DataForSEOAPIError

def _make_handler(
    client_method_name: str,            # e.g. "serp_google" — 在 DataForSEOClient 上的方法名
    schema_validator,                   # pydantic BaseModel 子类
    mode_default: str = "standard",     # "standard" | "live"; per-tool override
):
    def _handler(args: dict, **kw):
        # Layer-2 防御性 env 检查（layer-1 是注册时的 check_fn）
        if not (os.getenv("DATAFORSEO_LOGIN") and os.getenv("DATAFORSEO_PASSWORD")):
            return tool_error(
                "DataForSEO credentials missing. Set DATAFORSEO_LOGIN and "
                "DATAFORSEO_PASSWORD (NOT dashboard password).",
                code=401,
            )
        try:
            validated = schema_validator(**args).model_dump(exclude_unset=False)
            # 显式补默认值（不依赖 schema default 字段，详见决策日志）
            validated.setdefault("location_code", 2840)
            validated.setdefault("language_code", "en")
            mode = validated.pop("mode", mode_default)
        except ValidationError as e:
            return tool_error(f"invalid args: {e.errors()}", code=400)

        try:
            client = DataForSEOClient()
            method = getattr(client, client_method_name)
            payload = method(**validated, mode=mode)
            return tool_result(payload)  # 直接 dump envelope；参见 "Handler 返回值约定" 关于 `data=X` 短路
        except DataForSEOAuthRequiredError as e:
            return tool_error(str(e), code=401)
        except DataForSEOAPIError as e:
            return tool_error(str(e), code=e.status_code)
        except Exception as e:
            return tool_error(f"DataForSEO tool failed: {type(e).__name__}: {e}")
    return _handler
```

`DataForSEOAuthRequiredError` / `DataForSEOAPIError` 都定义在 `client.py`，分别继承 `RuntimeError` 和 `Exception`。镜像 `plugins/spotify/tools.py:31-36` 的 `_spotify_tool_error` 错误聚合模式。

### .env 加载约束

- 生产环境：`DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` 通过 `$HERMES_HOME/.env`（默认 `~/.hermes/.env`，`hermes_constants.py:30-32` 是依据）加载
- **Smoke harness 环境特殊**：`run_smoke.sh` 通过 `HERMES_HOME` 切换到隔离的 `.homes/SX-NN/profiles/aiseo/`。smoke 凭证**必须在命令行直接 `export`**，**不要**写入 `~/.hermes/.env`，否则 smoke 会读不到
- 插件 loader 通过 `os.getenv()` 延迟读取（在 `check_fn` 和 handler 调度时），不支持会话中途热重载；修改 `.env` 后需重启 aiseo

---

## Endpoint 参考（Phase 1 工具）

| 工具 | Endpoint | Standard 流程 | 默认 location / language | 成本 |
|------|-------------|--------|------------------------------|------|
| `dataforseo_serp_google` | `POST /v3/serp/google/organic/task_post` *或* `POST /v3/serp/google/organic/live/advanced` | task_post → tasks_ready(按 task_id 过滤) → task_get/advanced/{id} | `location_code=2840` (US), `language_code="en"` | $0.0006 / $0.002 per SERP |
| `dataforseo_onpage_summary` | `POST /v3/on_page/task_post` + 轮询 `/v3/on_page/summary/{id}` 直到 `crawl_progress="finished"` | task_post → crawl_progress 轮询 → summary 取回 | n/a（输入为目标 URL） | ~$0.00125 per page |
| `dataforseo_keyword_volume` | `POST /v3/keywords_data/google_ads/search_volume/task_post` *或* `/live` | **task_post → tasks_ready(按 task_id 过滤) → task_get**（完整 3 步） | `location_code=2840` (US), `language_code="en"` | $0.05 / $0.075 per task（批量 ≤1000） |
| `dataforseo_labs_keyword_ideas` | `POST /v3/dataforseo_labs/google/keyword_ideas/live`（无 Standard） | n/a (Live only) | `location_code=2840` (US), `language_code="en"` | ~$0.0103 per call |
| `dataforseo_backlinks_summary` | `POST /v3/backlinks/summary/live`（无 Standard） | n/a (Live only) | n/a（输入为目标 domain） | 在 app 定价页确认 |

**Auth**：`Authorization: Basic base64(login:password)`，凭证来自 `app.dataforseo.com/api-access`（**不是** dashboard 密码）。
**Sandbox 主机**：`sandbox.dataforseo.com`（路径相同、免费、dummy 数据）。**注意**：sandbox 不触发 401/402 错误路径 —— 这些只在 unit 测试中覆盖。

---

## 文件：新增 6 + 修改 4

### 新增（6）

| 文件 | 用途 |
|------|---------|
| `plugins/dataforseo/plugin.yaml` | manifest（省略 `kind`、5 项 provides_tools、requires_env 元数据） |
| `plugins/dataforseo/__init__.py` | `register(ctx)` 注册 5 个工具 |
| `plugins/dataforseo/client.py` | `DataForSEOClient` —— sync httpx、Basic Auth、4 种轮询模式、sandbox、凭证脱敏、429 退避、`DataForSEOAuthRequiredError` / `DataForSEOAPIError` 异常 |
| `plugins/dataforseo/tools.py` | 5 个 pydantic schema + handler + `_make_handler()` factory |
| `tests/tools/test_dataforseo_client.py` | mock-httpx 单元测试 |
| `tests/aiseo_llm/prompts/s6_dataforseo.md` | 3 个 smoke prompt（SID **S6-05**、**S6-06**、**S6-07**） |

### 修改（4）

| 文件 | 变更 |
|------|--------|
| `seeds/aiseo-profile/config.yaml` | `plugins.enabled:` 追加 `- dataforseo`（profile 级别默认启用，详见"启用语义"） |
| `seeds/aiseo-profile/skills/keyword-opportunity/SKILL.md` | 新增 **Step 1.5** "查询量化"（业务术语，无 `dataforseo_*` 名称） |
| `.env.example` | 新增 DataForSEO 段：`DATAFORSEO_LOGIN`、`DATAFORSEO_PASSWORD`、`DATAFORSEO_SANDBOX`（含"API password ≠ dashboard password"注释） |
| `tests/aiseo_llm/runner/grade.py` | 新增 `_grade_s6_dataforseo()` + `grade_s6()` 主干分支 + 扩展 `INTERNAL_TOOL_OUTPUT_PATTERNS` |

---

## 实施步骤（10）

1. **一次性脚手架 4 个插件文件**（避免 manifest/registry 不一致警告）：
   - `plugin.yaml` 含完整 `provides_tools`（5 项）
   - `client.py` stub：`DataForSEOClient` 类骨架 + `DataForSEOAuthRequiredError` + `DataForSEOAPIError` 类（参考 `plugins/spotify/client.py:1-40` import + 异常布局）
   - `tools.py` stub：5 个 handler 各 `return tool_error("not implemented yet", code=501)`（**不是 NotImplementedError**——按仓库标准包装为 tool_error 字符串）
   - `__init__.py` 含真实 `register(ctx)` 循环 5 工具（详见附录 §5）
   - 验证 `aiseo plugins list` 显示全部 5 工具已注册；运行时调度返回 tool_error 而非崩溃
2. 填充 `client.py` 核心：`DataForSEOClient.__init__`（Basic Auth、sandbox 切换、sync httpx、`_mask_auth_header()` 脱敏辅助）
3. 添加 `client.py` 5 个 endpoint 方法 + 4 个轮询辅助：
   - `serp_google(*, keyword, location_code, language_code, mode, **kw)` 等 5 个 endpoint 方法（精确签名见附录 §3）
   - `_task_post(endpoint_path, payload)` / `_tasks_ready(endpoint_path, task_id)`（**按 task_id 过滤**）/ `_task_get(endpoint_path, task_id)` / `_live_call(endpoint_path, payload)` / `_crawl_progress_poll(task_id, timeout=300)` —— `crawl_progress_poll` 用 `threading.Thread + thread.join(timeout=300)` 强制超时控制（仅做超时硬上限，不释放调用方阻塞）
   - 429 退避：尊重 `X-RateLimit-Remaining`，指数退避（5s、10s、20s）最多 3 次
4. 用 `_make_handler()` factory（签名见 Architecture）替换 `tools.py` stub。每个 schema 用 pydantic（仓库已有 pydantic==2.12.5，**避免引入 jsonschema**——不在仓库依赖中）。schema 字段见附录 §2
5. 更新 `__init__.py` 的 `register(ctx)`：接入 `check_fn=_check_dataforseo_available`，**不要为 `dataforseo_onpage_summary` 设 `is_async=True`**（sync handler + 内部 thread 包装；详见 Architecture 节"sync vs async client"），emoji 见附录 §6，`requires_env` 元数据
6. 编写 `tests/tools/test_dataforseo_client.py`（mock httpx），覆盖：
   - 401 / 402 / 429 退避（unit mock only —— sandbox 不触发这些）
   - sandbox host 切换 `sandbox.dataforseo.com` vs `api.dataforseo.com`
   - 3 步 task 轮询（task_post → tasks_ready 按 task_id 过滤 → task_get）
   - `crawl_progress` 轮询（含 timeout / 完成 / 超时三个分支）
   - 凭证脱敏（Authorization header 不出现在异常字符串）
   - 环境变量缺失时 handler 返回 `tool_error("...", code=401)`
   - **插件注册测试**（独立 test）：模拟启用 `plugins.enabled=[dataforseo]` 后 5 工具进入 registry；未启用时不加载；凭证缺失时 `check_fn` 返回 False
7. 更新 `seeds/aiseo-profile/skills/keyword-opportunity/SKILL.md` Step 1.5（业务术语；草稿见附录 §4）
8. 更新 `seeds/aiseo-profile/config.yaml`（`plugins.enabled` 追加 `dataforseo`）
9. 更新 `.env.example`，新增 DataForSEO 段（实际行见附录 §7）
10. **smoke 接线**（修复 reviewer CRITICAL #2 + CRITICAL #10 log/out 方向）：
    - 编写 `tests/aiseo_llm/prompts/s6_dataforseo.md`，含 3 个 SID：**S6-05**（SERP）、**S6-06**（关键词搜索量 + ideas）、**S6-07**（on-page summary）。prompt 全文见附录 §8
    - 在 `tests/aiseo_llm/runner/grade.py:grade_s6()` 中，**在已有的 `return False, f"unknown S6 prompt {sid}"` fallthrough 之前**插入：
      ```python
      if sid in ("S6-05", "S6-06", "S6-07"):
          return _grade_s6_dataforseo(sid, out_text, log_text, tools)
      ```
    - 定义 `_grade_s6_dataforseo(sid, out_text, log_text, tools) -> tuple[bool, str]`。**两个独立断言方向分开**：
      - **log 方向（工具调度证据）**：`assert any(t.startswith("dataforseo_") for t in tools)` —— `tools` 由 `grade.py:261-270` `extract_tool_dispatches()` 仅扫 `log_text` 产生
      - **out 方向（供应商名泄漏）**：`assert not re.search(r"\bdataforseo[_\-]?\w*", out_text, re.IGNORECASE)` —— **仅扫 `out_text`**，绝不扫 log；由 `grade.py:355-367` `find_leaks()` 处理
      - 另加：`out_text` 匹配 S6 报告形态（≥1 次 LLM 调用，3 个小节）；不调度任何 `BANNED_TOOLS`
    - 扩展 `INTERNAL_TOOL_OUTPUT_PATTERNS`（`grade.py:98-108`），加入 `r"\bdataforseo[_\-]?\w*"`。**`INTERNAL_TOOL_OUTPUT_PATTERNS` 由 `find_leaks(out_text)` 消费，永不扫 log**（核实：`grade.py:691-693` 仅传入 `out_text`），因此扩展安全

---

## 验收闸门（合并前 4 项全过）

1. **Unit**：`bash scripts/run_tests.sh tests/tools/test_dataforseo_client.py -v` 全绿。覆盖 401 / 402 / 429 退避 / sandbox 切换 / 3 步轮询（按 task_id 过滤）/ `crawl_progress` 轮询 / 凭证脱敏 / `DataForSEOAuthRequiredError` / 插件注册测试。**注意**：401/402 仅 mock —— sandbox 不触发。
2. **Sandbox 端到端（S6）**：
   ```bash
   AISEO_SMOKE_CONFIRMED=1 \
   AISEO_SMOKE_TOOLSETS=web,dataforseo \
   DATAFORSEO_SANDBOX=1 \
   DATAFORSEO_LOGIN=$L \
   DATAFORSEO_PASSWORD=$P \
   bash tests/aiseo_llm/runner/run_smoke.sh s6
   ```
   全绿。具体：`_grade_s6_dataforseo()` 对 S6-05/06/07 必须返回 `(True, ...)`，**不能 fallthrough 到 `"unknown S6 prompt"`**。`.log` 中每个新 SID 出现 `tool dataforseo_*_completed`；`.out` 中不出现 `dataforseo` 字面量（通过扩展后的 `INTERNAL_TOOL_OUTPUT_PATTERNS` 自动断言；**仅检查 out，不检查 log**）。
3. **回归**：现有 S1–S5 bucket 无回归。
4. **凭证安全（人工）**：使用有效的 sandbox 凭证检查任意 `.log` / `.out`：确认无明文 login/password、无 base64 auth header、无完整 `Authorization: Basic ...` 行。

---

## 风险与缓解

| 风险 | 严重度 | 缓解 |
|------|----------|-----------|
| 凭证在 logs/errors 中泄漏 | HIGH | `client.py._mask_auth_header()` 脱敏；复用 `agent/redact.py` 模式；smoke 通过扩展后的 `INTERNAL_TOOL_OUTPUT_PATTERNS` 断言零泄漏 |
| **Grader 方向混淆**：把 `dataforseo` 正则误加到 log 扫描路径，导致每次工具调度自动 FAIL | **HIGH** | Step 10 明确：`INTERNAL_TOOL_OUTPUT_PATTERNS` 由 `find_leaks(out_text)` 消费（grade.py:691-693），永不扫 log；`tools` tuple 来自 `extract_tool_dispatches(log_text)`，永不扫 out；两个方向独立断言 |
| **Grader fallthrough**：新 S6 SID 未接入 `grade_s6()` → "unknown S6 prompt" FAIL | **HIGH** | Step 10 的显式 `if sid in ("S6-05", "S6-06", "S6-07"):` 分支不可妥协 |
| **smoke 缺 `AISEO_SMOKE_CONFIRMED=1` 直接退出** | MEDIUM | Gate 2 命令已显式声明该 env；run_smoke.sh:11, 67-70 是依据 |
| Live 模式成本超支（3.3× Standard） | MEDIUM | 默认 `mode="standard"`；每次 `mode="live"` 需显式 opt-in；v0.1 无预算护栏 |
| LLM 输出 `dataforseo_*` 名称（破坏 SOUL.md §5 脱敏） | MEDIUM | SKILL.md 用业务术语；aiseo-guard OutputGate 屏蔽供应商名；扩展后的 `INTERNAL_TOOL_OUTPUT_PATTERNS` 自动 fail |
| `crawl_progress` 轮询长时间占用 dispatch 线程（最长 300s） | MEDIUM | sync polling 5s 间隔 × 60 次；`thread.join(timeout=300)` 强制硬超时；agent 主 asyncio 事件循环通过 `asyncio.to_thread`（`tui_gateway/ws.py:159`）已隔离不受影响；**不**设 `is_async=True`（registry 要求 coroutine handler） |
| `tasks_ready` 并发任务串扰 | MEDIUM | `_tasks_ready(endpoint_path, task_id)` 必须按当前 task_id 过滤，不是简单 list-all |
| Sandbox 与 prod 形态不一致 | LOW | 据官方文档 JSON 信封相同；测试通过 `DATAFORSEO_SANDBOX` 切换覆盖两端 |
| 插件加载但凭证无效（401） | LOW | `check_fn` 阻塞调度；handler error 脱敏为 "DataForSEO credentials invalid — check app.dataforseo.com/api-access" |

---

## 本计划不做的事（YAGNI）

- 不做 Backlinks 深度工具（history、anchors、intersect）—— v0.1 仅 summary
- 不做 `keyword_ideas` 之外的 DataForSEO Labs
- 不做成本追踪面板
- 不做 DataForSEO MCP bridge（TypeScript 生态）
- 不为另外 5 个技能自动接入 DataForSEO —— 它们继续用 `web_search` / `web_extract`
- 不做真实 API 的 401/402 e2e 测试（unit mock 覆盖）

---

## 决策日志

| 决策 | 来源 / 理由 |
|----------|---------------------|
| 走 plugin 路径（而非 `tools/`） | `AGENTS.md:266-270, 519-524` 明文 |
| 省略 `kind`（默认 standalone） | 付费 API；不应自动加载；参照 `plugins/disk-cleanup/`，不参照 `plugins/spotify/` |
| 5 个 LLM 工具（而非 210 个 endpoint） | BFCL / MCPVerse benchmark；技能审计；DataForSEO 自家 MCP 也仅 84 个 |
| 增强 `keyword-opportunity` 技能（不新建） | 避免技能拆分；现有 Step 1-5 已覆盖概念 |
| SKILL.md 用业务术语（无 `dataforseo_*`） | `seeds/aiseo-profile/SOUL.md` §5 供应商名脱敏规则 |
| 2 层闸门（`check_fn` + handler），而非 `requires_env` | `hermes_cli/plugins.py:256` 确认 `requires_env` 仅元数据 |
| **plugins.enabled 决定 profile 默认启用，check_fn 决定凭证 gating** | 两个语义分开：profile 维护者决定暴露集合；环境变量决定实际可用 |
| **Handler 必须返回 `tool_result()` / `tool_error()` 字符串**，不返回 dict | `tools/registry.py:537-558` + `plugins/spotify/tools.py:17` 是仓库标准 |
| **sync handler 直接 sync 轮询**；thread 仅做 `join(timeout=300)` 硬超时，不释放调用方阻塞；不设 `is_async=True` | `tools/registry.py:384-387` 显示 `is_async=True` 要求 coroutine handler；非 async 分支直接 `return entry.handler(...)`，handler 必然 sync 等待；agent 主事件循环安全来自 `asyncio.to_thread`（`tui_gateway/ws.py:159`），与 handler 内 thread 包装无关 |
| 新 S6 SID（S6-05/06/07）显式分支 + log/out 方向分开 | `grade_s6()` 有 fallthrough；`INTERNAL_TOOL_OUTPUT_PATTERNS` 仅扫 out，`extract_tool_dispatches` 仅扫 log，两个断言独立 |
| **Validator 用 pydantic 而非 jsonschema** | `pyproject.toml:13-63` 锁定的依赖含 `pydantic==2.12.5`，不含 jsonschema；避免引入新顶级依赖 |
| **Validator 失败抛 `ValidationError`** → handler 捕获 → `tool_error(...)` | 错误不向上传播，统一以 tool_error 字符串返回给 LLM |
| **location_code / language_code 在 handler validator 内显式补默认值**，不依赖 schema default | schema default 字段在 pydantic 中可能因 `exclude_unset=True` 而丢失；handler 内 `setdefault` 更稳健 |
| `tasks_ready` 必须按当前 task_id 过滤 | 避免并发任务的轮询串扰 |
| keyword_volume Standard 流程：`task_post → tasks_ready → task_get` | 与 SERP Standard 模式一致；Live 是同步快速路径 |
| Step 1 一次性脚手架 4 个文件 | `register` 为空但 `provides_tools` 非空会触发 manifest/registry 警告 |
| 使用 `scripts/run_tests.sh`（非裸 `pytest`） | 项目标准入口，含 PYTHONPATH + env 接线 |
| **Gate 2 smoke 命令必须含 `AISEO_SMOKE_CONFIRMED=1`** | `run_smoke.sh:67-70` 是 cost confirmation gate，缺则直接退出 |
| **smoke 凭证用 `export` 传入，不写入 `~/.hermes/.env`** | smoke harness 通过 `HERMES_HOME` 切换隔离目录，写入 `~/.hermes/.env` 会被忽略 |
| sandbox 优先；凭证绝不通过对话传入 | 数据外泄准则；用户在本地 `.env` 配置 |

---

## 下一步动作

**等待用户显式确认**后再执行 Step 1（脚手架 4 个文件）。Step 1 落地、`aiseo plugins list` 显示 5 工具均返回 `tool_error("not implemented yet")` 后，暂停以待审阅，再进入 Step 2。

---

# 接口契约附录

> 本附录包含代码级 contract，确保 Step 1→10 可不间断执行。所有签名、schema、措辞草稿在此一次定死，实施时直接照抄。

## §1 异常类层级（`client.py`）

```python
class DataForSEOError(Exception):
    """所有 DataForSEO 客户端异常的基类。"""

class DataForSEOAuthRequiredError(DataForSEOError):
    """凭证缺失或 401。"""

class DataForSEOAPIError(DataForSEOError):
    """API 返回非 2xx；含 status_code。"""
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code
```

## §2 pydantic schema（`tools.py`）

```python
from pydantic import BaseModel, Field
from typing import Literal, List, Optional

class SerpGoogleArgs(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=700)
    location_code: int = 2840                    # US
    language_code: str = "en"
    device: Literal["desktop", "mobile"] = "desktop"
    depth: int = Field(10, ge=1, le=100)
    mode: Literal["standard", "live"] = "standard"

class OnPageSummaryArgs(BaseModel):
    target: str = Field(..., description="目标 URL 或 domain")
    max_crawl_pages: int = Field(100, ge=1, le=1000)
    mode: Literal["standard"] = "standard"        # OnPage 只支持 Standard

class KeywordVolumeArgs(BaseModel):
    keywords: List[str] = Field(..., min_length=1, max_length=1000)
    location_code: int = 2840
    language_code: str = "en"
    mode: Literal["standard", "live"] = "standard"

class LabsKeywordIdeasArgs(BaseModel):
    keywords: List[str] = Field(..., min_length=1, max_length=200)
    location_code: int = 2840
    language_code: str = "en"
    limit: int = Field(100, ge=1, le=1000)
    mode: Literal["live"] = "live"                # Labs 只支持 Live

class BacklinksSummaryArgs(BaseModel):
    target: str = Field(..., description="目标 domain")
    mode: Literal["live"] = "live"                # Backlinks Summary 只支持 Live
```

## §3 `DataForSEOClient` 5 个 endpoint 方法签名

```python
class DataForSEOClient:
    def __init__(self, login: Optional[str] = None, password: Optional[str] = None,
                 sandbox: Optional[bool] = None): ...

    def serp_google(self, *, keyword: str, location_code: int, language_code: str,
                    device: str, depth: int, mode: str) -> dict: ...

    def onpage_summary(self, *, target: str, max_crawl_pages: int, mode: str) -> dict: ...

    def keyword_volume(self, *, keywords: List[str], location_code: int,
                       language_code: str, mode: str) -> dict: ...

    def labs_keyword_ideas(self, *, keywords: List[str], location_code: int,
                           language_code: str, limit: int, mode: str) -> dict: ...

    def backlinks_summary(self, *, target: str, mode: str) -> dict: ...
```

每个方法返回完整 DataForSEO response envelope（`{status_code, tasks: [...]}`）；由 handler 通过 `tool_result()` 包装。

## §4 SKILL.md Step 1.5 措辞草稿

插入位置：`seeds/aiseo-profile/skills/keyword-opportunity/SKILL.md`，在原 Step 1（扩展查询集）和 Step 2（跑 SERP 调研）之间。

```markdown
- **Step 1.5（可选 · 查询量化）**：
  - 若提供 `market` 和 `language`，且账户已配置关键词数据库访问，则对 Step 1 产生的候选查询调用"**关键词数据库查询**"，获取每个候选的搜索量、CPC、竞争度。
  - 同步调用"**关键词扩展**"获取相关词建议（最多 200 个种子）。
  - 用量化结果修剪 Step 2 的查询集：剔除 0 搜索量项；合并近义；按 (低难度 × 高匹配) 重排。
  - 若账户未配置或调用失败，跳过本步，直接进入 Step 2，并在报告附注"未启用量化数据源"。
```

**禁词**：本段绝不出现 `dataforseo`、`DataForSEO`、`api`、`endpoint`、`plugin`、具体工具名（`dataforseo_*`）。

## §5 `_check_dataforseo_available()` 与 `register(ctx)`

```python
# plugins/dataforseo/__init__.py
from __future__ import annotations
import os
from plugins.dataforseo.tools import (
    SERP_GOOGLE_SCHEMA, ONPAGE_SUMMARY_SCHEMA, KEYWORD_VOLUME_SCHEMA,
    LABS_KEYWORD_IDEAS_SCHEMA, BACKLINKS_SUMMARY_SCHEMA,
    _handle_dataforseo_serp_google, _handle_dataforseo_onpage_summary,
    _handle_dataforseo_keyword_volume, _handle_dataforseo_labs_keyword_ideas,
    _handle_dataforseo_backlinks_summary,
)

def _check_dataforseo_available() -> bool:
    return bool(os.getenv("DATAFORSEO_LOGIN") and os.getenv("DATAFORSEO_PASSWORD"))

_TOOLS = (
    ("dataforseo_serp_google",          SERP_GOOGLE_SCHEMA,         _handle_dataforseo_serp_google,         "🔍"),
    ("dataforseo_onpage_summary",       ONPAGE_SUMMARY_SCHEMA,      _handle_dataforseo_onpage_summary,      "📋"),
    ("dataforseo_keyword_volume",       KEYWORD_VOLUME_SCHEMA,      _handle_dataforseo_keyword_volume,      "📊"),
    ("dataforseo_labs_keyword_ideas",   LABS_KEYWORD_IDEAS_SCHEMA,  _handle_dataforseo_labs_keyword_ideas,  "💡"),
    ("dataforseo_backlinks_summary",    BACKLINKS_SUMMARY_SCHEMA,   _handle_dataforseo_backlinks_summary,   "🔗"),
)

def register(ctx) -> None:
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="dataforseo",
            schema=schema,
            handler=handler,
            check_fn=_check_dataforseo_available,
            requires_env=["DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"],
            emoji=emoji,
        )
```

## §6 Emoji 选择

| 工具 | Emoji | 理由 |
|---|---|---|
| `dataforseo_serp_google` | 🔍 | 搜索 |
| `dataforseo_onpage_summary` | 📋 | 审计报告 |
| `dataforseo_keyword_volume` | 📊 | 量化数据 |
| `dataforseo_labs_keyword_ideas` | 💡 | 创意/扩展 |
| `dataforseo_backlinks_summary` | 🔗 | 链接 |

## §7 `.env.example` 新增段（追加到现有文件末尾，约 472 行后）

```
# =============================================================================
# DATAFORSEO API（结构化 SEO 数据源）
# =============================================================================
#
# DataForSEO 提供 SERP、关键词数据、On-Page 审计、外链等结构化 SEO 数据。
# 凭证从 https://app.dataforseo.com/api-access 获取 —— 这是 API 专用密码，
# 与 dashboard 登录密码不同。
#
# 默认走 sandbox（dummy data，免费），生产请删 DATAFORSEO_SANDBOX 行。

# DATAFORSEO_LOGIN=
# DATAFORSEO_PASSWORD=
# DATAFORSEO_SANDBOX=1
```

## §8 Smoke prompts（`tests/aiseo_llm/prompts/s6_dataforseo.md`）

参照 `tests/aiseo_llm/prompts/s6_phase2_skill_minimal.md` 的表格格式：

```markdown
| SID | Prompt | Class | Assertion |
|-----|--------|-------|-----------|
| S6-05 | `keyword-opportunity: 找一下"vegan protein powder"在美国市场的关键词机会，输出 3 章节报告。` | B Phase2 | ≥1 LLM call · 调用 dataforseo_* 工具 · 3 章节报告 · 不出现 dataforseo 字面量 · 0 banned tool |
| S6-06 | `keyword-opportunity: 关键词 "kindle vs paperwhite" 的搜索量和相关词扩展，附带难度评分。` | B Phase2 | ≥1 LLM call · 调用 dataforseo_keyword_* 工具 · 3 章节报告 · 不出现 dataforseo 字面量 · 0 banned tool |
| S6-07 | `growflare-seo: 对 https://example.com 做单页 SEO 审计，列出关键问题。` | B Phase2 | ≥1 LLM call · 调用 dataforseo_onpage_* 工具 · 3 章节报告 · 不出现 dataforseo 字面量 · 0 banned tool |
```

**Assertion 列由 `_grade_s6_dataforseo()` 程序化验证**，不是给人读的——所以必须与函数实现一致。

## §9 依赖检查

- ✅ `httpx[socks]==0.28.1` 已在 `pyproject.toml:37`，无需新增
- ✅ `pydantic==2.12.5` 已在 `pyproject.toml`，用作 schema validator
- ❌ `jsonschema` 未在依赖中 —— **不引入**，用 pydantic 替代
- ✅ `tools/registry.py:537-558` 提供 `tool_result` / `tool_error` —— 直接 import 使用
- ⚠️ `agent/redact.py` 若不存在，`_mask_auth_header()` 在 client.py 内自写：用 `re.sub(r"Authorization:\s*Basic\s+[A-Za-z0-9+/=]+", "Authorization: Basic ***", text)`

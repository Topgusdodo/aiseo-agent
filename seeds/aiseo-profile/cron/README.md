# AISEO Cron 模板使用指南

> 本目录的 JSON 文件**仅作业意图参考**——它们不会被 `hermes cron create` 自动
> 读取。`hermes cron create` 是 positional-args CLI，需要按下面的命令手动注册。
> JSON 字段名与 CLI flag 一一对应，方便复制粘贴。

## CLI 字段映射

| JSON 字段 | `cron create` CLI | 说明 |
|---|---|---|
| `schedule` | positional 1 | 5-field cron（`0 8 * * 1`）或人类语法（`30m` / `every 2h`） |
| `prompt` | positional 2 | 任务自然语言描述 |
| `name` | `--name` | 作业可读名 |
| `skill[]` | 多次 `--skill <name>` | 附加 skill；重复使用追加多个 |
| `deliver` | `--deliver` | 输出投递：`origin` / `local` / `telegram` / `discord` / `signal` |
| (无) | `--repeat` | 重复次数；不传 = 一直重复（cron 周期） |
| (无) | `--script` | 脚本路径；本模板集不用 |
| (无) | `--no-agent` | 不走 LLM；本模板集不用 |
| (无) | `--workdir` | 工作目录；本模板集不用 |

## Deliver 字段选择

| 选项 | 行为 | AISEO 适配 |
|---|---|---|
| `origin` | 写回创建作业时的会话来源 | ✅ 安全；不调用 messaging toolset |
| `local` | 写到本地 `~/.hermes/cron/output/` | ✅ 推荐，安全；不调用 messaging |
| `telegram` / `discord` / `signal` | 通过 `send_message`/`messaging` 投递 | ❌ **禁用**——`messaging` 在 `agent.disabled_toolsets` 中 |
| `platform:chat_id` | 同上，messaging 投递 | ❌ **禁用** |

所有 AISEO cron 模板的 `deliver` 默认 `local`。若需投递到聊天源，可改 `origin`。
**绝不**改成 `telegram` / `discord` / `signal` / `platform:chat_id` 这类
messaging 投递——`pre_tool_call` 也会硬拦 `send_message`。

## 4 个开箱模板

### 1. `weekly-audit.json` — 周报（每周一 8:00）

```bash
# 推荐：从 MEMORY.md 自动注入
aiseo cron create-from-memory seo-weekly-report

# 或：手动指定 (用占位符 placeholder)
aiseo cron create \
  '0 8 * * 1' \
  'Run seo-weekly-report on <PRIMARY_SITE>. Produce the 3-section delta report (current snapshot / changes vs last / next actions).' \
  --name aiseo-weekly-audit \
  --skill seo-weekly-report \
  --deliver local
```

### 2. `monthly-technical-audit.json` — 月度技术审计（每月 1 日 9:00）

```bash
# 推荐：从 MEMORY.md 自动注入
aiseo cron create-from-memory technical-seo-audit

# 或：手动指定 (用占位符 placeholder)
aiseo cron create \
  '0 9 1 * *' \
  'Run technical-seo-audit on <PRIMARY_SITE> (site_root = primary site origin). Use focus=all and sample_pages=3. Produce the 3-section technical audit report.' \
  --name aiseo-monthly-technical-audit \
  --skill technical-seo-audit \
  --deliver local
```

### 3. `monthly-keyword-research.json` — 月度关键词调研（每月 1 日 10:00）

```bash
# 推荐：从 MEMORY.md 自动注入
aiseo cron create-from-memory keyword-opportunity

# 或：手动指定 (用占位符 placeholder)
aiseo cron create \
  '0 10 1 * *' \
  "Run keyword-opportunity for seed_keyword='<TOP_KEYWORD>', market=<MARKET>, language=<LANGUAGE>. Produce the 3-section opportunity report." \
  --name aiseo-monthly-keyword-research \
  --skill keyword-opportunity \
  --deliver local
```

### 4. `quarterly-competitor-watch.json` — 季度竞品观察（每季 1 日 10:00）

```bash
# 推荐：从 MEMORY.md 自动注入
aiseo cron create-from-memory competitor-analysis

# 或：手动指定 (用占位符 placeholder)
aiseo cron create \
  '0 10 1 */3 *' \
  "Run competitor-analysis with user_url=<USER_SITE> and competitor_urls=[<COMP_1>, <COMP_2>, <COMP_3>]. Use focus=all. Produce the 3-section comparison report with delta matrix." \
  --name aiseo-quarterly-competitor-watch \
  --skill competitor-analysis \
  --deliver local
```

## Cron 不自动调度（Hermes 框架限制 D7）

Hermes 当前的 cron 子系统**需要用户显式运行**（如 cron daemon 触发 / 手动
`aiseo cron run <job>` / 包装在 systemd timer 里）。本目录的模板
只定义"该跑什么"；调度由用户的系统级 cron 负责。如果你的需求是真正的"无人值守
自动周期"，可结合 macOS launchd / Linux systemd timer / Windows Task Scheduler。

## MEMORY.md 前置条件

4 个模板都从 `MEMORY.md` 读取作业上下文（主站点 / 关键词 / 竞品）。首次跑前
确认 `~/.hermes/profiles/aiseo/memories/MEMORY.md` 已填写。否则作业内的 prompt
会让 agent 反问用户并跳过本次执行——不会报错也不会写垃圾输出。

## 排查

| 现象 | 检查 |
|---|---|
| 作业 dispatch 但 LLM 0 工具调用 | MEMORY.md 缺主站点/关键词；按 prompt 中的"ask the user"分支跳过了 |
| cron 跑出 "Configuration Missing" / agent 反问 MEMORY 信息 | runtime agent 没 file/memory tool，读不到 `MEMORY.md` 字样的 prompt。检查 MEMORY.md 对应 section 是否填好；推荐用 `aiseo cron create-from-memory <skill>` 自动注入实值，绕过运行时读 MEMORY 的失败路径 |
| `--deliver telegram` 报错 / 静默丢消息 | messaging toolset 已禁；改 `local` 或 `origin` |
| `cron list` 看不到刚建的作业 | 用 `aiseo cron list`（wrapper 自动 `-p aiseo`）；直接跑 `hermes cron list` 会落 default profile 看不到 aiseo 作业 |
| `cron delete <name>` 报 "Job not found" | 删除接受的是 12 字符 **job ID**（`cron create` 输出的 hex 串），不是 `--name`。先 `aiseo cron list` 拿 ID 再 `aiseo cron delete <ID>` |

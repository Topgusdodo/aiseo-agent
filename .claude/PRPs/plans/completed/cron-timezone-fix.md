# Cron 时区修复 + 开始执行通知 — aiseo-agent 计划

## 状态

- **分支**：`feat/aiseo-phase2`
- **日期**：2026-05-18
- **类型**：Hermes core schema 改动 + AISEO plugin 透传 + scheduler 事件流补强
- **影响半径**：`cron/jobs.py` schema + `cron/scheduler.py` 事件流 + `plugins/aiseo-guard/__init__.py` 调用点（schedule_task + reschedule 两处）
- **向后兼容**：现存 `~/.hermes/cron/jobs.json` 中无 `timezone` 字段的 job 通过现有 `_normalize_job_record()` 在读路径自动兜底 `DEFAULT_CRON_TIMEZONE`

### 修订记录

- **v1**（初稿）：4 commit 拆分；新增 `_normalize_job` 纯函数
- **v2**（本版）：
  - Commit 数量 4 → 2（按 review 反馈：合并 schema/compute/plugin 透传到 C1，避免 C1 单独合并不修 bug 的语义陷阱）
  - 改为扩展现有 `_normalize_job_record()` (cron/jobs.py:99)，**不**新增 `_normalize_job` — 复用已有 schema normalize 钩子
  - 锁定 reschedule 路径：`_aiseo_manage_scheduled_tasks` action=reschedule (plugins/aiseo-guard/__init__.py:1036-1133)；修正 `update_job` 调用 + rollback 路径
  - 加 `schedule_display` 带 `(timezone)` 后缀（用户感知层）
  - 加 `_deliver_notice` 的 `deliver=local` silent skip 语义
  - 加 `_sanitize_for_notice` 防 markdown injection
  - 补 D4b：legacy naive `last_run_at` 升级路径分析
  - 确认 `croniter==6.0.0` 已 pin，去掉"待验证"

---

## 动机

用户使用「每天**北京时间** 09:35 发送 cfmate.com 标题检查」创建定时任务后，观察到三个症状：

1. **任务到点不跑**：09:35（北京）没触发，实际触发要等到 17:35（= UTC 09:35 反算回北京）。
2. **新建任务首跑被推迟一天**：09:14 创建、目标 09:20（还剩 6 分钟），`next_run_at` 直接跳到**明天** 09:20。
3. **执行无开始通知**：10:02 触发的任务，用户在 10:06 才收到完成消息，中间 4 分钟完全沉默。

通过三路并行 explorer 定位后，证实：**问题 1+3 同根**（job 缺结构化 timezone 字段），**问题 2 独立**（`_process_job()` 缺 start event）。

---

## 根因

### A. Timezone 信号在 plugin→core 边界丢失

`plugins/aiseo-guard/__init__.py::_aiseo_schedule_task()` 在 line 730 收到 `timezone="Asia/Shanghai"`（白名单校验过），但传给 `create_job()` (line 773) 时**没有 timezone 参数**：

```python
job = create_job(
    prompt=prompt,
    schedule=schedule,       # "35 9 * * *"
    name=name,
    deliver=None,
    origin=origin,
    skills=list(...),
    enabled_toolsets=["web", "search", "browser"],
    # ← timezone 在此处丢失
)
```

`cron/jobs.py::create_job()` (line 482) 的签名根本没有 `timezone` 参数 — schema 层不存在这个字段，写入 `~/.hermes/cron/jobs.json` 的 job dict 也没有它。

### B. `compute_next_run()` 用宿主进程时区解释 cron

`cron/jobs.py::compute_next_run()` (line 351-394) 计算 cron 类型 schedule 的下次触发时间：

```python
base_time = now           # _hermes_now() → 看 HERMES_TIMEZONE，默认 UTC
if last_run_at:
    base_time = _ensure_aware(datetime.fromisoformat(last_run_at))
cron = croniter(schedule["expr"], base_time)
next_run = cron.get_next(datetime)
return next_run.isoformat()
```

`croniter` 用 `base_time` 的 tzinfo 解释 cron 表达式。当 `HERMES_TIMEZONE` 未设为 `Asia/Shanghai` 时，`"35 9 * * *"` 被当成 **UTC 09:35** 计算 — 跟用户的原意「北京时间 09:35」（= UTC 01:35）差 8 小时。这同时导致：

- **问题 1**：cron 永远在 UTC 09:35 触发（北京 17:35）
- **问题 3**：09:14（北京）创建时，宿主 UTC 是 01:14，croniter 算出"下次 UTC 09:35"= 北京 17:35 — 但用户感知的"今天 09:20"目标已变成跨日 — _更精确的复现路径见"测试矩阵"，本节只指出 root cause 是 base_time 与 cron expr 的时区基准不一致_

### C. `_process_job()` 缺 start event

`cron/scheduler.py::_process_job()` (line 1740-1779) 的顺序：

```python
run_job(job)              # ← 整个 agent 执行（耗时 0~10 min）
save_job_output(...)
_deliver_result(...)      # ← 唯一一次推送：最终结果
mark_job_run(...)
```

`run_job()` 内部 `quiet_mode=True`，吞掉 LLM streaming。整个生命周期只有 **finish event** 一次外推，**没有 start event**。

---

## 范围

### 范围内

- **Hermes core schema 扩展**：`create_job()` 接受 `timezone` 参数；job dict 新增 `timezone` 字段
- **Schema normalize 边界**：`load_jobs()` 和 `create_job()` 都走同一个 `_normalize_job()` 纯函数；缺 `timezone` 字段回退 `"Asia/Shanghai"`（aiseo 默认用户语境）— **注意**：upstream Hermes 用户语境可能不同，回退默认值需放在配置可覆盖的常量
- **Timezone-aware `compute_next_run()`**：用 job 自带 timezone 构造 base_time，传 timezone-aware datetime 给 croniter
- **AISEO plugin 透传**：`_aiseo_schedule_task()` 在 `create_job()` 调用点显式传 `timezone=timezone`
- **`_process_job()` start event**：新增 `_deliver_notice()`（不复用 `_deliver_result` 的 wrap 包装）；在 `run_job(job)` 前调用一次
- **测试**：host TZ 隔离的 timezone 测试矩阵（`freezegun` + `os.environ["TZ"]="UTC"` + `time.tzset()`）

### 范围外

- **DST 处理**：Asia/Shanghai 无 DST，aiseo 主用户都在中国；DST 边界 case（如 America/New_York 春令时跳过的 02:30）**不在 v1 修复内**，留 TODO 注释
- **`_hermes_now()` 重构**：不动这个函数，避免触及其他消费方
- **`once` / `interval` 类型 schedule 的 timezone**：本次仅修 `cron` kind；`once`/`interval` 不依赖时区解释表达式
- **Gateway/messaging 层改动**：start event 复用现有 `_send_to_platform` 路径，不新增 adapter

---

## 设计

### D1. Job schema：新增 `timezone` 字段

**Before** (cron/jobs.py:597-630):
```python
job = {
    "id": ...,
    "name": ...,
    "prompt": ...,
    "schedule": parsed_schedule,
    "schedule_display": ...,
    # ... 无 timezone
}
```

**After**:
```python
job = {
    "id": ...,
    "name": ...,
    "prompt": ...,
    "schedule": parsed_schedule,
    "schedule_display": ...,
    "timezone": normalized_timezone,     # 新增
    # ...
}
```

### D2. 扩展现有 `_normalize_job_record()` — 复用而非新增

**关键事实**：`cron/jobs.py:99-131` 已存在 `_normalize_job_record(job)` 函数，专门做 schema normalize（处理 `prompt`/`name`/`schedule_display`/`state` 缺失字段，"keep storage untouched on read, but ensure consumers never crash"）。**timezone 字段 normalize 应该加进这里**，不新增函数。

**改动** (cron/jobs.py:99-131):
```python
def _normalize_job_record(job: Dict[str, Any]) -> Dict[str, Any]:
    """Return a read-safe cron job shape for UI/API/tool/scheduler consumers."""
    normalized = _apply_skill_fields(job)
    # ... 现有字段处理 (id/prompt/name/schedule_display/state) 保持不变 ...

    # NEW: timezone 字段兜底
    if not _coerce_job_text(normalized.get("timezone")).strip():
        normalized["timezone"] = DEFAULT_CRON_TIMEZONE

    return normalized
```

**`DEFAULT_CRON_TIMEZONE`** —— 模块顶层新增常量：

```python
DEFAULT_CRON_TIMEZONE = os.environ.get("HERMES_DEFAULT_CRON_TIMEZONE", "Asia/Shanghai")
```

默认 `Asia/Shanghai` 是 aiseo 用户语境；upstream Hermes 用户可通过 env 覆盖。

**调用现状**：`_normalize_job_record` 已被现有消费方调用（UI/API 读路径）。本次仅需确认 `load_jobs()` 和 cron scheduler 也走 normalize（grep 确认覆盖率）；若有遗漏路径，补 normalize 调用。

**注意**：`_normalize_job_record` 现有契约是 "keep storage untouched on read" —— 它**不写回 disk**。timezone 兜底也保持这个契约：内存里补，落地存储保留 legacy 形态，等下次 `update_job` / `create_job` 自然带上字段。

### D3. `create_job()` 签名

```python
def create_job(
    prompt: Optional[str],
    schedule: str,
    *,                                       # 后面全部 keyword-only
    timezone: Optional[str] = None,          # 新增
    name: Optional[str] = None,
    # ... 其他参数不变
) -> Dict[str, Any]:
    # ...
    normalized_timezone = (timezone or "").strip() or DEFAULT_CRON_TIMEZONE
    # zoneinfo 可解析校验
    try:
        ZoneInfo(normalized_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid timezone '{timezone}': {exc}")
    # ...
    job = {
        # ...
        "timezone": normalized_timezone,
    }
    return job
```

**校验**：`timezone` 字符串需能被 `zoneinfo.ZoneInfo(tz)` 解析，否则 raise `ValueError`。aiseo plugin 已经在 `_ALLOWED_SCHEDULE_TIMEZONES` 做了白名单（plugins/aiseo-guard/__init__.py:406-411），core 层只做 zoneinfo 可解析校验即可，不强制白名单（upstream Hermes 不应受 aiseo 约束）。

### D3b. `update_job()` 也需同样支持

`update_job(job_id, updates: dict)` 在 cron/jobs.py 的更新路径上 — reschedule 走的就是它（见 D5b）。如果 `updates` 含 `timezone`，需要：

1. 同样跑 zoneinfo 校验
2. 写入 job dict
3. **触发 `compute_next_run` 重算**（因为 timezone 变了，下次触发时间也变）— 已有逻辑可能已在 `schedule` 变更时重算，但 timezone-only 变更也要触发同样逻辑

### D4. `compute_next_run()` — timezone-aware

**Before** (cron/jobs.py:387-392):
```python
base_time = now
if last_run_at:
    base_time = _ensure_aware(datetime.fromisoformat(last_run_at))
cron = croniter(schedule["expr"], base_time)
next_run = cron.get_next(datetime)
return next_run.isoformat()
```

**After**:
```python
def compute_next_run(
    schedule: Dict[str, Any],
    last_run_at: Optional[str] = None,
    *,
    timezone: Optional[str] = None,       # 新增
) -> Optional[str]:
    # ... 前置分支不变 ...

    elif schedule["kind"] == "cron":
        if not HAS_CRONITER:
            # ... 不变 ...
            return None

        tz = ZoneInfo(timezone) if timezone else ZoneInfo(DEFAULT_CRON_TIMEZONE)

        if last_run_at:
            # _ensure_aware 把 naive 时间当系统本地时区
            # 然后 astimezone(tz) 转到 job 自己的 timezone
            base_time = _ensure_aware(datetime.fromisoformat(last_run_at)).astimezone(tz)
        else:
            base_time = datetime.now(tz)

        cron = croniter(schedule["expr"], base_time)
        next_run = cron.get_next(datetime)   # 输出继承 base_time 的 tz
        return next_run.isoformat()           # ISO 字符串带 offset (+08:00)
```

**调用点更新**：所有 `compute_next_run(schedule, last_run_at)` 调用处改为 `compute_next_run(schedule, last_run_at, timezone=job.get("timezone"))`。

### D4b. Legacy naive `last_run_at` 升级路径

**问题**：旧版本写入的 `last_run_at` 是 **naive ISO**（如 `"2026-05-18T09:35:00"`，无 offset）。升级到新版本后，`_ensure_aware()` (cron/jobs.py:273-288) 的行为是：

```python
target_tz = _hermes_now().tzinfo          # 取自 HERMES_TIMEZONE
if dt.tzinfo is None:
    local_tz = datetime.now().astimezone().tzinfo  # 系统本地时区
    return dt.replace(tzinfo=local_tz).astimezone(target_tz)
```

→ Legacy naive 时间被**当系统本地时区**解读，转到 `_hermes_now()` 时区。再 `.astimezone(job_tz)` 转到 job 的 timezone。

**实际影响**：
- **理想场景**（生产容器宿主 TZ=UTC、job TZ=Asia/Shanghai、旧 naive `last_run_at` 是 UTC 时刻）：解读正确，无偏差
- **失真场景**（开发机宿主 TZ=Asia/Shanghai 写出的 naive，迁到生产 UTC 容器读）：`_ensure_aware` 用生产宿主的 UTC 解读，但原值是北京时间写的 → **第一次 next_run 偏 8 小时**
- **自愈**：升级后第一次 next_run 写入是 aware ISO（带 offset），后续调用走 aware 分支，**第二次及之后正常**

**结论**：legacy naive 字段最差导致**首次触发偏差一次**，可接受。**不修复 `_ensure_aware`**（避免影响其他消费方）；**不主动迁移 disk 上的 naive 字段**（每个 job 在第一次 advance 后自然升级）。

风险等级：低 — 但 plan 必须写出，避免后人误以为是新 bug。

### D5. AISEO plugin 透传 — schedule_task 路径

**Before** (plugins/aiseo-guard/__init__.py:773):
```python
job = create_job(
    prompt=prompt,
    schedule=schedule,
    name=name,
    deliver=None,
    origin=origin,
    skills=list(task_config["skills"]),
    enabled_toolsets=["web", "search", "browser"],
)
```

**After**:
```python
job = create_job(
    prompt=prompt,
    schedule=schedule,
    timezone=timezone,                  # 新增 — 来自 line 730
    name=name,
    deliver=None,
    origin=origin,
    skills=list(task_config["skills"]),
    enabled_toolsets=["web", "search", "browser"],
)
```

### D5b. AISEO plugin 透传 — reschedule 路径

**关键修正**：reschedule 不在 `_aiseo_schedule_task` 里，而在 `_aiseo_manage_scheduled_tasks` action=`"reschedule"`（plugins/aiseo-guard/__init__.py:1036-1133）。这条路径**也丢了 timezone**。

**Before** (plugins/aiseo-guard/__init__.py:1099-1106):
```python
updated = update_job(
    resolved_job_id,
    {
        "schedule": parsed_schedule,
        "schedule_display": schedule_display,
        "prompt": new_prompt,
        # ← timezone 在此处丢失（line 1069-1077 收到了，但没传）
    },
)
```

**After**:
```python
updated = update_job(
    resolved_job_id,
    {
        "schedule": parsed_schedule,
        "schedule_display": schedule_display,
        "prompt": new_prompt,
        "timezone": timezone,           # 新增 — 来自 line 1069-1077
    },
)
```

**同时 rollback 路径**（line 1110-1117）也需要保留原 timezone：
```python
update_job(
    resolved_job_id,
    {
        "schedule": job.get("schedule"),
        "schedule_display": job.get("schedule_display"),
        "prompt": job.get("prompt"),
        "timezone": job.get("timezone"),    # 新增 — rollback 时恢复原 timezone
    },
)
```

### D5c. `schedule_display` 也带 timezone 字符串

**问题**：当前 `schedule_display = "daily at 09:35"`（cron/jobs.py:610），用户在 CLI/飞书看到的字符串**不带时区**。即使底层修对了，用户看到 "daily at 09:35" 还是会困惑「这是哪个时区的 9:35？」。

**修复**：在 `create_job` 和 reschedule 写入 job dict 时，拼上 timezone 后缀。

**`create_job()` 内** (cron/jobs.py:610):
```python
# Before:
"schedule_display": parsed_schedule.get("display", schedule),
# After:
"schedule_display": _format_display_with_tz(
    parsed_schedule.get("display", schedule),
    normalized_timezone,
),
```

**新增工具** (cron/jobs.py)：
```python
def _format_display_with_tz(display: str, timezone: str) -> str:
    """Append timezone hint to a schedule display string for cron-kind only."""
    if not display or f"({timezone})" in display:
        return display
    return f"{display} ({timezone})"
```

只对 `cron` kind 加（`once` / `interval` 的 display 不需要时区上下文）；幂等（已含 `(tz)` 不重复加）。

**reschedule 路径同样调用** (plugins/aiseo-guard/__init__.py:1083):
```python
schedule_display = _format_display_with_tz(
    parsed_schedule.get("display", schedule),
    timezone,
)
```

### D6. `_process_job()` start event

**新增** `cron/scheduler.py::_deliver_notice(job, content, adapters, loop)`：

- **不复用** `_deliver_result()` 的 wrap_response 包装（避免显示成 "Cronjob Response: ..."）
- 同样走 `_resolve_delivery_targets` + `_send_to_platform`，但 content 直发
- **`deliver="local"` 时 silent skip** — 跟 `_deliver_result` 行为对齐：local job 不该走 messaging 路径
- **失败 silent fail**：try/except 包住，logger.warning，**绝不阻塞 job**
- 返回 `Optional[str]` 同 `_deliver_result`（用于诊断，但不会进 `mark_job_run`）

**Local skip 逻辑**（参考 `_deliver_result` line 493-499）：
```python
def _deliver_notice(job: dict, content: str, adapters=None, loop=None) -> Optional[str]:
    targets = _resolve_delivery_targets(job)
    if not targets:
        # local-only jobs don't deliver — not a failure (consistent with _deliver_result)
        return None
    # ... send content verbatim, no wrap ...
```

**`_process_job()` 改动** (cron/scheduler.py:1740-1779):

```python
def _process_job(job: dict) -> bool:
    """Run one due job end-to-end: notify start, execute, save, deliver, mark."""
    try:
        # NEW: start event
        try:
            start_notice = _build_start_notice(job)
            if start_notice:
                _deliver_notice(job, start_notice, adapters=adapters, loop=loop)
        except Exception as start_exc:
            logger.warning("Job '%s': start notice failed: %s", job["id"], start_exc)
            # 继续 — start event 失败绝不阻塞执行

        success, output, final_response, error = run_job(job)
        # ... 后续不变 ...
```

**`_build_start_notice(job: dict) -> str`** — 确定性字符串拼接，**不走 LLM**：

```python
_CONTROL_CHARS_RE = re.compile(r"[\r\n\t\x00-\x1f<>]")

def _sanitize_for_notice(text: str, max_len: int = 80) -> str:
    """Strip control chars and markdown-injectable tokens from user-controlled
    fields before splicing into a notice. aiseo plugin already filters at
    create time, but upstream cronjob toolset doesn't — defense in depth."""
    cleaned = _CONTROL_CHARS_RE.sub(" ", str(text or "")).strip()
    return cleaned[:max_len]

def _build_start_notice(job: dict) -> str:
    name = _sanitize_for_notice(job.get("name") or job.get("id", "?"))
    schedule_display = _sanitize_for_notice(job.get("schedule_display") or "—", max_len=120)
    return (
        f"⏳ 开始执行定时任务：{name}\n"
        f"计划：{schedule_display}\n"
        f"完成后会自动发送结果。"
    )
```

**注意**：`schedule_display` 在 D5c 已经带了 `(timezone)` 后缀，所以这里不再单独拼 timezone（避免重复显示）。

**控制字符过滤**：`job["name"]` 在 aiseo plugin 路径已过滤（`report_name` 80 字符 + 控制字符 ban），但 Hermes 上游 cronjob toolset 创建的 job 名字可能含 `\n` / `<` / 控制字符 — defense in depth，notice 边界再过一次。

文案为中文是 aiseo 主用户语境的合理默认；upstream Hermes 若需要英文/可定制，后续走 config 加模板字符串。

---

## 实现路径

按 **2 个 commit** 拆分（合并后是两个独立可 revert 的 PR / commit）：

- **C1 修问题 1+3**（时区 bundle）：schema + compute + plugin 透传 + reschedule **一次到位**，单独合并就**完整修复**时区两个症状
- **C2 修问题 2**（start event）：完全跟时区无关，可以晚合并、晚 ship

### Commit 1 — `feat(cron): job-level timezone (schema + compute + plugin透传)`

**目的**：单独合并即修复问题 1（任务到点不跑）+ 问题 3（首跑跳明天）。

**改动清单**：

| 文件 | 改动 |
|---|---|
| `cron/jobs.py` | 顶层新增 `DEFAULT_CRON_TIMEZONE`；扩展 `_normalize_job_record()` (line 99) 加 timezone 兜底；新增 `_format_display_with_tz()`；`create_job()` (line 482) 加 `timezone` kw-only 参数 + zoneinfo 校验 + `schedule_display` 拼时区；`compute_next_run()` (line 351) 加 `timezone` kw-only 参数；`update_job()` 处理 `timezone` 字段变更；所有内部 `compute_next_run` 调用点透传 `job["timezone"]` |
| `cron/scheduler.py` | grep 出所有 `compute_next_run` 调用点，全部加 `timezone=job.get("timezone")` |
| `plugins/aiseo-guard/__init__.py` | line 773 `create_job(...)` 加 `timezone=timezone`；line 1099-1106 reschedule 的 `update_job(...)` 加 `"timezone": timezone`；line 1110-1117 rollback 路径加 `"timezone": job.get("timezone")`；line 1083 reschedule 的 `schedule_display` 改用 `_format_display_with_tz` |
| `tests/cron/test_compute_next_run_timezone.py` | **新建** — 6-case 矩阵（见测试矩阵） |
| `tests/cron/test_normalize_job_record_timezone.py` | **新建** — legacy job 无 timezone 字段时回退到 `DEFAULT_CRON_TIMEZONE`；env 覆盖测试 |
| `tests/aiseo/test_aiseo_schedule_task.py` | **扩展** — 断言 `job["timezone"] == "Asia/Shanghai"` 且 `schedule_display` 含 `(Asia/Shanghai)` |
| `tests/aiseo/test_aiseo_manage_scheduled_tasks.py`（若不存在则新建）| 断言 reschedule 后 `job["timezone"]` 跟随 `args.timezone` 变更、rollback 路径保留 timezone |

**验证**：
```bash
scripts/run_tests.sh tests/cron/test_compute_next_run_timezone.py
scripts/run_tests.sh tests/cron/test_normalize_job_record_timezone.py
scripts/run_tests.sh tests/aiseo/         # 不能 break aiseo 现有 suite
scripts/run_tests.sh tests/aiseo_runtime_audit/   # 4-axis 全绿
scripts/run_tests.sh                       # 全 suite
```

**真机验证**（必须在非中国宿主 TZ 下，否则无法暴露 bug）：
```bash
TZ=UTC uv run aiseo
# 创建「每天北京时间 09:35 检查 cfmate.com 标题」
# 检查 ~/.hermes/cron/jobs.json:
#   - timezone: "Asia/Shanghai"
#   - schedule_display: "daily at 09:35 (Asia/Shanghai)"
#   - next_run_at 含 "+08:00" offset
# 在北京 09:14 创建北京 09:20 任务，确认 next_run_at 是今天 09:20 不是明天
```

### Commit 2 — `feat(cron): start event delivery before run_job`

**目的**：修复问题 2（执行无开始通知）。完全独立，逻辑上依赖 C1（要用 `schedule_display` 含 timezone 的版本）。

**改动清单**：

| 文件 | 改动 |
|---|---|
| `cron/scheduler.py` | 新增 `_deliver_notice()`（不走 wrap、`deliver=local` silent skip、失败 silent fail）+ `_build_start_notice()`（确定性拼接）+ `_sanitize_for_notice()`（控制字符过滤）；`_process_job()` (line 1740) 在 `run_job(job)` 前 try/except 调用 start notice |
| `tests/cron/test_process_job_start_event.py` | **新建** — mock `_deliver_notice`，断言：调用顺序（start 在 run 前）/ 内容含 job name 和 schedule_display / start event 抛异常时 run_job 仍跑 / `deliver=local` job 不投递 / 控制字符被过滤 |

**验证**：
```bash
scripts/run_tests.sh tests/cron/test_process_job_start_event.py
scripts/run_tests.sh                       # 全 suite
```

**真机验证**：触发一个 cron 任务（手动 reschedule 到 1 分钟后或 `aiseo_manage_scheduled_tasks` 强制 run-now），飞书应当**先**收到 "⏳ 开始执行..."，**之后**才收到 "Cronjob Response: ..."。

### Commit 3（可选）— `docs(aiseo): cron timezone fix changelog`

- 更新 `CLAUDE.md` 的 fork-delta 章节，记录 `timezone` 字段加入 job schema
- 更新 `docs/aiseo-agent/ARCHITECTURE.md`（若存在 cron 章节）
- 现存用户零操作 — `_normalize_job_record` 自动兜底 + 首次 next_run 自然升级到 aware ISO

---

## 测试矩阵

### 关键：host TZ 隔离

**这才是当初 unit test 没 catch 到 bug 的根因** — 开发机 macOS 系统时区就是 Asia/Shanghai，所有"默认时区"问题被掩盖。修复后的测试必须**显式模拟非中国时区的宿主进程**：

```python
import os
import time
from datetime import datetime
from freezegun import freeze_time

def setup_function(_):
    os.environ["TZ"] = "UTC"
    time.tzset()

def teardown_function(_):
    os.environ.pop("TZ", None)
    time.tzset()
```

### 矩阵

| # | host TZ | job TZ | now (wall) | cron expr | 期望 next_run_at | 当前行为（bug） | 用途 |
|---|---|---|---|---|---|---|---|
| 1 | UTC | Asia/Shanghai | 北京 09:14 (UTC 01:14) | `20 9 * * *` | **今天**北京 09:20 | 跳明天 | 复现问题 3 |
| 2 | UTC | Asia/Shanghai | 北京 09:25 (UTC 01:25) | `20 9 * * *` | **明天**北京 09:20 | 也是明天 — bug 在这里**不暴露**，因为不论时区怎么算结果都是明天。保留此 case 是为了验证 fix 不破坏"过了今天窗口跳明天"的正确行为 | 回归保护 |
| 3 | UTC | Asia/Shanghai | 北京 09:34 (UTC 01:34) | `35 9 * * *` | **今天**北京 09:35 | 触发延迟到 17:35 | 复现问题 1（用户实际 case） |
| 4 | Asia/Shanghai | Asia/Shanghai | 北京 09:14 | `20 9 * * *` | **今天**北京 09:20 | 凑巧正确（掩盖 bug） | **关键**：解释为什么开发机 pytest 全绿但生产失败 |
| 5 | UTC | UTC | UTC 09:14 | `20 9 * * *` | 今天 UTC 09:20 | ✓ | baseline — 无时区错配时 fix 不引入回归 |
| 6 | UTC | （legacy 无字段） | 北京 09:14 | `20 9 * * *` | **今天**北京 09:20（normalize 补默认 Asia/Shanghai） | — | backward compat — legacy job 自动升级 |

**Case 4 是关键**：它解释了为什么开发机本地 pytest 全绿但生产（UTC 容器）失败 — 必须强制 host TZ 隔离才能 catch。删掉了原 Case 4（America/New_York host）— 跟 Case 1 验证的是同一件事，冗余。

### `_aiseo_schedule_task` 端到端

测试 plugin → core 链路：

```python
def test_aiseo_schedule_task_persists_timezone():
    result = _aiseo_schedule_task({
        "task_type": "page_audit",
        "frequency": "daily",
        "time": "09:35",
        "timezone": "Asia/Shanghai",
        "page_url": "https://cfmate.com",
    })
    job_id = json.loads(result)["job"]["id"]
    jobs = load_jobs()
    job = next(j for j in jobs if j["id"] == job_id)
    assert job["timezone"] == "Asia/Shanghai"   # ← 当前会 KeyError 或 None
```

### `_process_job` start event

```python
def test_process_job_sends_start_notice_before_run(monkeypatch):
    notice_calls = []
    monkeypatch.setattr(scheduler, "_deliver_notice",
                        lambda job, content, **kw: notice_calls.append(content))
    monkeypatch.setattr(scheduler, "run_job",
                        lambda job: (True, "ok", "done", None))
    monkeypatch.setattr(scheduler, "_deliver_result",
                        lambda job, content, **kw: None)
    # ... 触发 _process_job(test_job)
    assert len(notice_calls) == 1
    assert "开始执行" in notice_calls[0]
    assert test_job["name"] in notice_calls[0]
```

### Backward compat

```python
def test_load_jobs_normalizes_legacy_jobs_without_timezone(tmp_path):
    legacy = {"jobs": [{"id": "abc", "schedule": {"kind": "cron", "expr": "0 9 * * *"}}]}
    JOBS_FILE.write_text(json.dumps(legacy))
    jobs = load_jobs()
    assert jobs[0]["timezone"] == "Asia/Shanghai"   # 自动补默认
```

---

## 验收

提交合并前必须全部通过：

- [ ] `scripts/run_tests.sh tests/cron/` 全绿（新增 timezone matrix 覆盖率 ≥80%）
- [ ] `scripts/run_tests.sh tests/aiseo/` 全绿
- [ ] `scripts/run_tests.sh tests/aiseo_runtime_audit/` 4-axis 全绿
- [ ] `scripts/run_tests.sh`（全 suite）全绿
- [ ] **真机验证**：在 UTC 容器（或 `TZ=UTC docker run ...`）跑 aiseo，创建「每天北京时间 09:35 ...」任务，确认：
  - jobs.json 里 `timezone: "Asia/Shanghai"`
  - `next_run_at` 是带 `+08:00` offset 的 ISO 时间
  - 09:14 创建 09:20 任务，`next_run_at` 是今天而非明天
- [ ] **start event 真机验证**：触发一个 cron 任务，飞书在执行**开始**时收到 "⏳ 开始执行..." 消息，4 分钟后再收到 "Cronjob Response: ..." 结果消息

---

## 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| `_normalize_job` 修改 schema 影响其他 cronjob 工具（非 aiseo） | 中 | normalize 只**新增**字段、不删/改 — 旧消费方读不到 `timezone` 也不影响；新消费方一定能读到 |
| `DEFAULT_CRON_TIMEZONE="Asia/Shanghai"` 对 upstream Hermes 用户不友好 | 中 | 提供 `HERMES_DEFAULT_CRON_TIMEZONE` env 覆盖；在 PR 描述里向 upstream 标注此假设 |
| `croniter` 版本不支持 timezone-aware base_time | 低 | **已确认**：`pyproject.toml:48` pin `croniter==6.0.0`，6.x 完全支持 timezone-aware `base_time`（自 1.x 起就支持） |
| `_deliver_notice` 阻塞 `run_job` | 中 | try/except 完全包住，超时由底层 HTTP client 控制；不在主线程 await 长时间 |
| 现存用户的 `next_run_at` 是 naive ISO（无 offset）— 升级后跟 aware ISO 混合 | 中 | `_ensure_aware()` 已经处理 naive datetime；通过 normalize 在 load 时升级；写一个 migration 测试覆盖混合状态 |
| 测试用 `os.environ["TZ"]` + `time.tzset()` 在并行测试时污染其他 case | 高 | 用 pytest fixture 严格 setup/teardown；或用 `monkeypatch.setenv` + `time.tzset()` 配对 |

---

## 接口契约附录

### 修改前后的 `create_job` 签名

```diff
 def create_job(
     prompt: Optional[str],
     schedule: str,
+    *,
+    timezone: Optional[str] = None,
     name: Optional[str] = None,
     repeat: Optional[int] = None,
     # ... 其他不变
 ) -> Dict[str, Any]:
```

### Job dict schema diff

```diff
 {
     "id": "abc123",
     "name": "AISEO daily Page Audit — example.com",
     "prompt": "...",
     "schedule": {"kind": "cron", "expr": "35 9 * * *", "display": "daily at 09:35"},
     "schedule_display": "daily at 09:35",
+    "timezone": "Asia/Shanghai",
     "next_run_at": "2026-05-19T09:35:00+08:00",
     # ... 其他不变
 }
```

### `compute_next_run` 签名

```diff
 def compute_next_run(
     schedule: Dict[str, Any],
     last_run_at: Optional[str] = None,
+    *,
+    timezone: Optional[str] = None,
 ) -> Optional[str]:
```

### 新增 `_deliver_notice` 签名

```python
def _deliver_notice(
    job: dict,
    content: str,
    adapters=None,
    loop=None,
) -> Optional[str]:
    """
    Deliver a notice (non-final, non-wrapped) to the job's delivery targets.

    Used for start events and any future intermediate-state notifications.
    Unlike _deliver_result, this does NOT wrap content with the "Cronjob Response"
    header — the notice is sent verbatim. Failures are logged but never raised.

    Returns None on success, or an error string on failure.
    """
```

### 扩展现有 `_normalize_job_record` 行为

不新增函数 — 在已有 `_normalize_job_record(job)` (cron/jobs.py:99) 中追加 timezone 兜底逻辑。契约不变：

- 继续是 "read-safe shape" — 不写回 disk
- 继续不 mutate 入参
- 新增字段兜底：`timezone` 缺失 → `DEFAULT_CRON_TIMEZONE`（env 可覆盖）

### 新增模块顶层常量

```python
# cron/jobs.py
DEFAULT_CRON_TIMEZONE: str = os.environ.get("HERMES_DEFAULT_CRON_TIMEZONE", "Asia/Shanghai")
```

### 新增 `_format_display_with_tz` 工具

```python
def _format_display_with_tz(display: str, timezone: str) -> str:
    """Append timezone hint to a cron schedule display. Idempotent."""
```

### 新增 `_sanitize_for_notice` 工具

```python
# cron/scheduler.py
def _sanitize_for_notice(text: str, max_len: int = 80) -> str:
    """Strip control chars and markdown-injectable tokens before splicing
    user-controlled fields into a start notice."""
```

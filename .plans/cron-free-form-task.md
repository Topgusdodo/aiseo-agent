# Cron 自由 prompt — 让定时任务和即时任务能力对齐

## 目标

让用户能注册"每天 9 点抓 cfmate.com 标题"这类**自由 SEO prompt** 的定时任务，
cron agent 在执行时**自动用 `aiseo_skills_read` 加载合适的 skill**，处理能力
与即时任务一致。

## 设计选择

实地侦察后否决了"删 `aiseo_schedule_task` + unblock 原生 cronjob" 的纯方案 G：

- 原生 `cronjob` (`tools/cronjob_tools.py:285-306`) 接受 `script / workdir /
  model / provider / base_url / enabled_toolsets / no_agent / context_from /
  deliver` 等字段，暴露面比 team 报告说的大。
- 直接 unblock 还得另写一层"AISEO-only 字段过滤"，反而比改造现有自建工具复杂。
- 现有 `aiseo_schedule_task` 的 `forbidden_fields` 集合（`plugins/aiseo-guard/
  __init__.py:792`）本身就是这层字段过滤，**有保留价值**。

最终选择：**改造现有 `aiseo_schedule_task`，把 `prompt` 移出 forbidden、把
`task_type` 从硬枚举变成可选 hint，wrapper 注入硬约束**。其他禁字段保留。

## 改动清单

### 1. `plugins/aiseo-guard/__init__.py`

- `AISEO_TASK_TYPES`：保留作向后兼容 + 字段校验复用，不再强制枚举
- `AISEO_SCHEDULE_TASK_SCHEMA`：
  - 加 `prompt`（string, 自由 SEO 任务描述，≤ 2000 字符）
  - `task_type` 从 `enum` 改为自由 string + 描述里说"optional hint, used for
    backward compatibility when prompt is not supplied"
  - `required`: `["frequency"]`（不再要求 task_type）
- `_aiseo_schedule_task`：
  - `forbidden_fields` 删 `prompt`，保留其余
  - 分支：
    - 有 `prompt` → 走新路径 `_build_freeform_schedule_prompt`
    - 没 `prompt` 但有合法 `task_type` → 走旧路径（向后兼容，已注册不破坏）
    - 都没有 → 报错"either prompt or task_type required"
- 新函数 `_build_freeform_schedule_prompt(prompt, frequency, time, timezone,
  language)`：
  - 包装用户 prompt
  - 追加硬约束段（即 SOUL §6 的硬化版本，防长 context 衰减）
  - 引导调用 `aiseo_skills_read` 自动加载 skill
  - 仍然过 `_scan_cron_prompt`
- create_job 时固定 `enabled_toolsets=["web","search","browser","aiseo_skills_read"]`
  （自由 prompt 不该让用户选 toolset；`aiseo_skills_read` 是暴露
  `aiseo_skills_list` + `aiseo_skill_view` 的 toolset，cron runtime 必须有它
  才能在运行时按 prompt 指引加载 SKILL.md）；不指定 skills 字段（不预 pin，让
  cron agent 运行时自己选）

### 2. `seeds/aiseo-profile/SOUL.md` §2.1

改写"对话式 SEO 定时任务"段：
- 去掉"只允许 7 个白名单"的硬约束描述
- 改为"用户自由描述 SEO 任务 + schedule 三要素（频率 / 时间 / 时区）"
- 保留"非 SEO prompt / 非 SEO 自动化拒绝"、"script、workdir、投递、模型 / provider /
  base_url、任意 toolsets / enabled_toolsets / skills 仍然不接受"
- 保留 7 个 task_type 在 SOP 中作为"快捷词"（用户说"技术审计"→提示 LLM 用
  `task_type=technical_audit`），但不强制

### 3. 测试

新文件 `tests/aiseo/test_aiseo_schedule_task_freeform.py`：

1. 自由 prompt 注册成功（"每天 9 点抓 cfmate.com 标题"）
2. 自由 prompt 路径生成的 prompt 包含硬约束段（DATA only / aiseo_skills_read）
3. 自由 prompt 路径 enabled_toolsets = ["web","search","browser","aiseo_skills_read"]
   （多一个 aiseo_skills_read 让 cron agent 运行时能加载 SKILL.md）
4. 缺 prompt 和 task_type 都缺时报错
5. 自由 prompt 走 `_scan_cron_prompt`（注入 payload 被拦）
6. 自由 prompt 不能传 script/workdir/model/provider（forbidden 保留）
7. 旧 task_type 路径仍能跑（向后兼容）
8. 自由 prompt + frequency floor（不允许 every_5min 这种过密频率—— 已在
   `_ALLOWED_FREQUENCIES` 中天然限制）

### 4. 不动的

- `tools/cronjob_tools.py` 原生 cronjob 工具，保持禁用
- `seeds/aiseo-profile/config.yaml`，保持现状
- `aiseo_manage_scheduled_tasks`（list/pause/resume 不受影响）
- `cron/scheduler.py` 的 `_scan_assembled_cron_prompt`（已是 second-order 防线）

## 安全边界总结

| 攻击面 | 防御层 |
|---|---|
| 自由 prompt 注入 | `_scan_cron_prompt` regex 8 + 5 patterns + invisible unicode |
| 业务范围越权 | SOUL.md §3 软规则 + InputGate 黑名单 |
| 字段越权（script/workdir） | `forbidden_fields` 集合（保留） |
| skill 内容被污染 | `_scan_assembled_cron_prompt`（已有，cron/scheduler.py:1153） |
| 网页内容回流污染 | SOUL.md §6 软规则 + wrapper 注入硬约束（新增） |
| token 失控 / 频率失控 | `_ALLOWED_FREQUENCIES` 集合（最小 hourly） |

## 工作量

- 代码：~80 行新增 + ~20 行修改
- 测试：8 个新测试
- 1 个 PR
- 不需要破坏性数据迁移

# Profile Sync → profile_distribution.py — Spike

**Status**: COMPLETE  
**Date**: 2026-05-19  
**Author**: Code Explorer Agent (P0-C task)  
**Decision**: (c) 保留 AISEO 私有 + 文档化为永久资产

---

## 1. 历史归因

### Commit 时间线

| 文件 | 首次 commit | UTC 时间 |
|---|---|---|
| `hermes_cli/profile_distribution.py` | `f209a3585` — 2026-05-08T10:04-07:00 | 2026-05-08 **17:04 UTC** |
| `aiseo_cli.py` (首次出现) | `15956f9fd` — 2026-05-14T15:53+08:00 | 2026-05-14 **07:53 UTC** |

**时间差**: `profile_distribution.py` 比 `aiseo_cli.py` 早 **约 6 天**。

### 结论: 可能性 (c) — 开发顺序问题

`distribution.py` 在 AISEO sync 写作时已经存在于 repo。但 commit message 
`15956f9fd` ("aiseo_cli.py — Python entry point that bootstraps the aiseo profile 
and delegates to hermes chat") 没有任何关于评估 distribution.py 的记录。

**最可能的原因**: 当时 owner 专注于"seed → user profile"的 first-run bootstrap 语义,
而 `distribution.py` 的设计哲学是"打包好的独立 profile 从 git URL 安装",两者 surface
不重叠,owner 未识别到语义关联。没有历史证据显示 distribution.py 被评估过后主动放弃;
属于开发顺序/认知盲区问题,而非主动的技术决策。

---

## 2. Gap Matrix(13 行为点)

读取依据: `hermes_cli/profile_distribution.py` 全文 (702 行); `aiseo_cli.py:60-870`。

| # | AISEO 行为 | AISEO 位置 | 上游能力 | 判定 | 证据 |
|---|---|---|---|---|---|
| 1 | `NEVER_OVERWRITE_FILES` 保护(`MEMORY.md`, `config.yaml`, `.env`, `auth.json`, `auth.lock`) | `aiseo_cli.py:71-77` | `USER_OWNED_EXCLUDE` 保护 `.env`, `auth.json`, `state.db`, `memories/` 等,**但不保护 `MEMORY.md`**(它在 `memories/` 下间接受保护); `config.yaml` 在 update 时 `preserve_config=True` 跳过 | **部分** | `profile_distribution.py:98-117` (`USER_OWNED_EXCLUDE`); `l.549` (`config.yaml` 条件跳过); `MEMORY.md` 在 `memories/` 目录下通过目录保护,但 AISEO 的 `MEMORY.md` 在 `skills/` 内的用法需逐案验证 |
| 2 | `SEED_TRACKED_LIST_FIELDS` additive list migration — 读 seed config,将缺失的 list item 追加到用户 config.yaml,保留注释/缩进/顺序,text-level 编辑 | `aiseo_cli.py:87-91`, `_migrate_profile_config` (l.400-545) | **完全不存在**。distribution.py 在 update 时对 `config.yaml` 只做两种选择:整体保留(preserve_config=True)或整体替换(preserve_config=False / --force-config)。无任何 additive merge 逻辑 | **✗** | `profile_distribution.py:549`, `l.627-674` `update_distribution()`;代码全文未见 "merge", "additive", "append" 相关逻辑 |
| 3 | `config.yaml.bak.*` 滚动备份(5 槽,文件名排序剪枝,兼容旧 legacy `.bak`) | `aiseo_cli.py:363-397` `_rolling_backup` | **完全不存在**。distribution.py 不对任何文件做 backup,直接 `shutil.copy2` 或 `shutil.copytree` 覆盖 | **✗** | `profile_distribution.py` 全文无 "backup", "bak", "rolling", "snapshot" 字样 |
| 4 | Env warning block — 扫 enabled plugin 的 `requires_env`,对比 `.env` 文件 + `os.environ`,缺失时打印警告 | `aiseo_cli.py:757-809` `_check_plugin_env_requirements` | **部分**。distribution.py 有 `env_requires` manifest 字段(l.37-44, `EnvRequirement` dataclass l.134-163),并生成 `.env.template` / `.env.EXAMPLE`(l.333-349, l.566)。**但它不检查变量是否真的在运行时存在**;没有 `os.environ` 对比,没有 stderr 警告;只是生成模板文件 | **部分** | `profile_distribution.py:333-349` `_env_template_from_manifest`; `l.566`; 无 `os.environ` 引用(grep 确认) |
| 5 | `--refresh-soul` SOUL.md backup + 覆盖,显示行数 diff,交互式确认 | `aiseo_cli.py:657-729` `_refresh_soul_from_seed` | **✗ 不存在**。distribution.py 的 update 会整体替换 SOUL.md(`DEFAULT_DIST_OWNED` l.85 包含 SOUL.md);但没有单独的"仅刷新 SOUL"子命令,也没有交互式确认 + 行数 diff | **✗** | `profile_distribution.py:85-92` `DEFAULT_DIST_OWNED`; `l.625-674` `update_distribution` |
| 6 | `skills/` 目录粒度 missing-only — skill 目录已存在则跳过整个 skill,不覆盖用户修改 | `aiseo_cli.py:558-573` `_sync_skills_dir` | **✗ 完全相反**。`_copy_dist_payload` 在 l.555-563 对目录先 `shutil.rmtree(dest)` 再 `shutil.copytree(entry, dest)` — 完全替换。update 时 skills/ 全量覆盖用户修改 | **✗** | `profile_distribution.py:554-563` `_copy_dist_payload`;这是最大语义差异 |
| 7 | YAML 注释 / anchor / 缩进保留 — text-level 编辑,不 re-dump,`_find_list_block` 检测 anchor 并跳过 | `aiseo_cli.py:173-361`, `_has_yaml_anchor` l.351 | **✗ 不存在**。distribution.py 用 `yaml.safe_dump`(l.254)重新序列化,会丢失所有注释、anchor 声明、自定义缩进 | **✗** | `profile_distribution.py:251-255` `_dump_yaml`; l.271 `write_manifest` |
| 8 | git URL 安装(`hermes profile install github:...`) | AISEO 无此功能(`aiseo sync` 只读本地 seed) | 上游完整支持 git clone、depth-1、ssh/https/git@ 格式、`#ref` pin | **✓ (上游独有)** | `profile_distribution.py:357-430` `_looks_like_git_url`, `_git_clone`, `_stage_source` |
| 9 | distribution-owned vs user-owned 路径划分 | AISEO 用 `NEVER_OVERWRITE_FILES` basename 匹配 | 上游用 `USER_OWNED_EXCLUDE` frozenset + `DEFAULT_DIST_OWNED` tuple,语义更清晰但覆盖范围不同(AISEO 的 `NEVER_OVERWRITE_FILES` 含 `MEMORY.md` 而上游不含) | **部分** | `profile_distribution.py:85-117`; `aiseo_cli.py:71-77` |
| 10 | `requires_env` 在 plugin.yaml 中声明 | `plugins/aiseo-guard/plugin.yaml`, `plugins/dataforseo/plugin.yaml` | 上游有 `env_requires` 在 `distribution.yaml` manifest 中声明(独立于 plugin.yaml);两套声明系统语义不同(per-plugin vs distribution-level) | **部分(不兼容)** | `profile_distribution.py:37-44`, `134-163`; AISEO 的 `_check_plugin_env_requirements` 读 `plugin.yaml` 而非 manifest |
| 11 | 跨平台路径处理 | `aiseo_cli.py` 全程用 `pathlib.Path`(l.13 import) | 上游同样全程 `pathlib.Path`(l.70 import) | **✓** | 两文件均用 `pathlib`,无 `os.sep` / `os.path.join` |
| 12 | 失败模式(corrupt YAML / inline scalar / anchor)报错而非崩溃 | `aiseo_cli.py:_migrate_profile_config` diff["skipped"] 细粒度错误码(l.440,l.476,l.481) | **部分**。distribution.py 用 `try/except DistributionError` 在调用层处理(l.263-266 `read_manifest`),但内部 `_copy_dist_payload` 无细粒度 skipped 报告;出错即 raise,无 diff 跟踪 | **部分** | `profile_distribution.py:257-266`, `l.526-570`; aiseo 的 skipped[] audit trail 无对应 |
| 13 | Atomic write + fsync — config.yaml 写入用 `mkstemp` 到同目录临时文件、`fsync` 强制落盘、`os.replace` 原子替换,保证写入中途崩溃不会留下损坏文件 | `aiseo_cli.py:516-526` `_migrate_profile_config` 写入路径 | **✗ 完全不存在**。distribution.py 直接 `shutil.copy2`(l.555)和 `path.write_text`(无 fsync,无临时文件,无 atomic replace);写入中途崩溃 = 文件损坏,且无 backup(见 #3)所以无法恢复 | **✗** | `profile_distribution.py:554-563` `_copy_dist_payload`(裸 `shutil.copy2` / `shutil.copytree`);全文 grep 无 `fsync` / `mkstemp` / `os.replace` |

### Gap 汇总

- **✓ (对等)**: #11 跨平台路径
- **✓ (上游独有)**: #8 git URL 安装(AISEO 当前不需要)
- **部分**: #1 文件保护, #4 env warning, #9 路径划分, #10 requires_env 声明, #12 失败模式
- **✗ (上游完全不支持)**: #2 additive list migration, #3 rolling backup, #5 refresh-soul 子命令, #6 skills missing-only, #7 YAML 注释保留, #13 atomic write/fsync

**6 个核心 AISEO 特有能力(#2/#3/#5/#6/#7/#13)上游完全没有**,不是"小差距可打补丁",而是根本设计哲学不同:

- distribution.py 哲学: **distribution-owned = 完全替换**,用户 owned = 完全隔离,两域泾渭分明;写入用裸 `shutil.copy2`,无 durability/safety 保证
- aiseo sync 哲学: **seed → profile 是 additive/missing-only,且 config 可 additive merge**,用户改动永远安全;写入走 atomic write + fsync,中途崩溃不损坏文件

---

## 3. 3 选 1 决策

**选择**: **(c) 保留 AISEO 私有 + 文档化为永久资产**

### 理由

#### 核心哲学冲突,不是能力缺失

`profile_distribution.py` 的设计前提是"distribution-owned 内容全权由发行者控制,update
等于从 git 重新拉取并全量替换"。这对"可复现部署"场景(工程团队分发标准化 profile)是正确的。

AISEO 的 sync 哲学恰恰相反:SEO 用户会在本地 profile 里修改 skill prompt、tune 参数、
积累 MEMORY,这些是用户资产,不能被 upstream update 覆盖。`_sync_skills_dir` 的
missing-only 语义(#6)正是这一哲学的体现。如果换用 distribution.py 的 rmtree+copytree,
用户修改过的 skill 文件会在每次 `aiseo sync` 时被静默清除,这是数据丢失风险。

#### 不可桥接的 5 个 gap

gap #2(additive list migration)是 AISEO 的核心运维能力:当 AISEO 发布新 plugin、
新 toolset 时,旧用户 profile 的 config.yaml 会被自动补齐而不会丢失用户的手改项。
这需要 text-level YAML 编辑 + 注释保留(#7)+ rolling backup(#3)作为安全网。
这三个能力在 distribution.py 里一个都没有,且实现它们需要改变 distribution.py
的核心 update 流程,不是小补丁。

gap #5(`--refresh-soul`)是 AISEO 特有的"软规则漂移修复"工具,上游不需要这种概念。

#### "推上游"路径代价过高

如果走 (b) 推上游 PR:需要在 distribution.py 里加:
1. 目录粒度 missing-only 模式(破坏现有 update 语义)
2. YAML text-level additive merge(~200 行,含 anchor 检测、缩进镜像、atomic write)
3. rolling backup(~50 行)
4. 运行时 env 变量检查 + stderr 警告(~60 行)
5. `--refresh-soul` 子命令(~80 行)

总计 ~400 行上游变更,且会引入"两种 update 模式"(全替换 vs missing-only),破坏
distribution.py 当前简洁的哲学。上游 Hermes maintainer 不太可能接受这么大的哲学分叉。
按照三问决策树:"AISEO 用户群外是否有人会用这个 patch?" — additive merge 和 missing-only
skills 是 SEO 场景特有的;一般 profile distribution 场景不需要它。

### 排除其他选项

**排除 (a) 直接复用**: gap #6(skills 全量覆盖)是数据丢失风险,gap #2(additive merge)
是核心运维能力,两者都不是"可接受 acceptable loss"。换用 distribution.py 会破坏
"用户在本地 tune skill 后 sync 不覆盖"这个隐式合同,且会静默丢失数据。

**排除 (b) 推上游**: 需要 ~400 行改动,引入哲学分叉,且上游使用场景(可复现部署)
不需要这些能力。6 周超时后大概率升格为永久资产,走弯路。

---

## 4. 危险检查

选 (c) 不涉及替换操作,因此**无新增替换风险**。但有两个现有风险需文档化:

### 4.1 现有 `_migrate_profile_config` 的备份覆盖窗口

`_rolling_backup` 在写入前备份,但 backup 失败时(磁盘满 / 权限问题)直接放弃写入
并报告 `diff["skipped"]`。这是安全的设计。

风险点:如果用户手工修改 `config.yaml` 后立即运行 `aiseo sync`,rolling backup
会把用户版本备份到 `.bak.YYYYMMDD_HHMMSS`,然后 additive append 到正确位置。
用户改动**不会丢失**,因为 text-level 编辑是纯追加。**风险评级: 低**。

**但有一个 silent-skip 子风险需要 P1-B 处理**:`aiseo_cli.py:202-208` 的 anchor 检测
(`_has_yaml_anchor`)只要发现 `&` 或 `*` 字符就广泛跳过整段 list migration;另外
`block-not-found`、`non-list-shape`、嵌套 ≥3 层 list 等失败模式也都只把详情写入
`diff["skipped"]` dict,**不打 stderr WARN**。用户在终端只看到 `aiseo sync` 退出 0,
完全不知道某个 plugin 的新 toolset 因为 anchor 被静默漏掉,直到下次某个功能不工作
才会回溯排查。

**P1-B 建议**:照搬 `_check_plugin_env_requirements` 的 stderr 警告样式(see
`aiseo_cli.py:757-809`),让 `_migrate_profile_config` 在返回前若 `diff["skipped"]`
非空则打印一个清晰的 WARN block,列出每个被跳过的 field 路径 + 跳过原因(anchor /
block-not-found / non-list-shape / nesting-too-deep)+ 修复建议(例如"请手工把
`X` 追加到 `config.yaml` 的 `toolsets:` 列表")。这把 silent failure 升级为
visible warning,符合 "fail-loud" 原则。

### 4.2 Backwards-compat(现有用户 profile)

AISEO 当前无 `distribution.yaml` manifest,因此现有用户的
`~/.hermes/profiles/aiseo/` 不满足 `update_distribution()` 的前置条件(l.648-658 会
raise)。选 (c) 下不使用 distribution.py 的任何路径,**无 backwards-compat 问题**。

如果将来有人手动尝试 `hermes profile update aiseo`,会得到清晰的
`DistributionError: Profile 'aiseo' is not a distribution (no distribution.yaml)`
错误,不会静默破坏 profile。**风险评级: 低(有明确错误信息)**。

### 4.3 Seeds/aiseo-profile 与 distribution.yaml 共存风险

如果将来有人在 `seeds/aiseo-profile/` 添加 `distribution.yaml`(例如为了支持
`hermes profile install github:...` 安装 AISEO),distribution.py 的 `update_distribution`
会绕过所有 AISEO 的保护逻辑,全量覆盖 skills/。这是未来的风险点,需在
`seeds/aiseo-profile/` 目录的 README 或 CLAUDE.md 中明确标注:

> "不要在此目录添加 distribution.yaml。AISEO profile sync 由 aiseo_cli.py 的专用
> 路径处理,不走 hermes profile distribution 机制。"

**风险评级: 中(仅在未来有人误操作时触发)**。

---

## 5. 后续工作量估算

### P1-B 实施内容(选 (c) 路径下)

选 (c) 的 P1-B 定义为:**文档化 + 稳固化**,而非重构替换。

| 任务 | 估算 | 说明 |
|---|---|---|
| 在 `CLAUDE.md` "Profile bootstrap pattern" 段补充明确声明:sync 是 AISEO 永久私有实现,不走 distribution.py | 0.25d | 防止未来 owner 误判为技术债 |
| 在 `ARCHITECTURE.md` 新增 ADR:Profile Sync vs distribution.py 决策记录 | 0.5d | 包含本 spike 的 gap matrix 精华 |
| **ADR 编号查 + 写入** `docs/aiseo-agent/ARCHITECTURE.md` 已有 ADR 序列位置(需先 grep 现有 ADR-NNN 编号、确认下一个可用号、按现有 ADR 模板格式插入) | 0.25d | 新增项 — 之前漏算 ADR 编号管理成本 |
| 在 `seeds/aiseo-profile/` 补 README 说明"禁止添加 distribution.yaml"的原因 | 0.25d | 防止 #4.3 风险 |
| **验证** `seeds/aiseo-profile/README.md` **是否已存在**;若无需新建 + 加 CODEOWNERS-style 标注(owner 标识 + "do-not-add-distribution.yaml" 警告) | 0.25d | 新增项 — 之前默认假设 README 存在,需先 ls 确认 |
| `aiseo_cli.py` 添加 `# NOTE: distribution.py not used — see .plans/profile-sync-upstream-spike.md` 注释 | 0.1d | 代码内指引 |
| 验证测试:确认 `_sync_skills_dir` missing-only 行为有 unittest 覆盖 | 0.25d | 防止未来重构意外改变语义 |
| **为 atomic write / rolling backup / yaml-comment-preservation 各加 unit test**(三个独立 test,覆盖 fsync 路径、备份槽位剪枝、注释/anchor 保留断言) | 0.5d | 新增项 — 之前只列 missing-only 一项测试,漏了 #3/#7/#13 的保护测试 |
| `docs/aiseo-agent/NEXT_STEPS.md` 加"重评估 trigger"段落(指向本 spike 第 6 节,提醒季度 review owner) | 0.25d | 新增项 — 与 must-fix 2(第 6 节)联动,确保 trigger 条件不孤立 |

**P1-B 总工时**: **~2.5 天**(约为 spike 估算 1.25d 的 2x,新增 4 项:ADR 编号管理
+ NEXT_STEPS 重评估段 + 三个保护 unit test + seeds README 创建/验证)

### 如果未来需要支持"从 git URL 安装 AISEO"(#8 能力)

则需要在 `aiseo_cli.py` 单独实现 git clone + 种子安装路径,或在
`seeds/aiseo-profile/` 添加带 `distribution_owned: []`(空列表,禁用全替换)的特殊
distribution.yaml。但**当前不需要**,遵循 YAGNI。

---

## 6. 重评估触发条件 (Trigger conditions for re-spike)

选 (c) 是基于"2026-05 这一时间点的上游 distribution.py 设计哲学"作出的永久资产
判定。但上游 Hermes 在演进,某些上游能力的引入会让本 spike 的核心论据失效,届时
owner 应重新跑一遍 Gap matrix 决策。**默认评估周期: 每季度一次**(对齐 P0-B 的
季度僵尸 pattern 清理节奏)。

### 6.1 立即触发重评估的上游变更

以下任一上游变更出现时,**不必等到下一季度**,owner 应在 1 周内重新评估本 spike:

| 上游变更 | 影响的 gap | 重评估理由 |
|---|---|---|
| `distribution.py` 引入 `distribution_owned` 的 **per-path policy**(允许某路径标 `replace`、某路径标 `missing_only`) | 可能填上 **#6 skills missing-only** | 这是 spike 当前判定 (c) 的最大 BLOCKING 理由之一。若上游允许 per-path 模式标注,AISEO 就可以声明 `skills/: missing_only` 而复用 distribution.py 框架 |
| 上游加入 `config.yaml` 的 **text-level merge hook**(类似 `pre_config_write` / `transform_config` callback) | 可能填上 **#2 additive list migration** + **#7 YAML 注释保留** | spike 当前的另外两个 BLOCKING/SIGNIFICANT gap。若上游开放 hook 让 plugin 注入 text-level 编辑逻辑,AISEO 的 `_migrate_profile_config` 就可以注册成 hook 而不必维护私有 sync |
| 上游引入 **backup 机制**(任何形式:rolling backup、snapshot、.bak 文件)在 update 路径里 | **#3 rolling backup** 从 SIGNIFICANT 退化为 ACCEPTABLE LOSS | 若上游有 backup,AISEO 即使丢失自己的 rolling backup 实现,用户也不会面对"config 损坏无法恢复"的风险。这时可单独考虑混合实现(用上游 update + AISEO 的 additive merge) |
| 上游引入 **atomic write / fsync** 写入路径 | **#13 atomic write/fsync** 从 ✗ 退化为 ✓ | 同上,降低混合实现的安全风险 |

### 6.2 季度 review checklist

每季度(对齐 P0-B 节奏)按以下步骤跑一遍:

1. `git -C <hermes-upstream-checkout> log --since="3 months ago" -- hermes_cli/profile_distribution.py` — 列出过去一季度所有变更
2. 对每个 commit 检查是否引入 6.1 表格中四类 API/概念之一(关键词:`missing_only`、`merge`、`backup`、`fsync`、`atomic`、`per_path`、`hook`、`callback`、`transform_config`)
3. 检查 `hermes_cli/` 下是否新增了与 profile distribution 相关的新文件(例如 `profile_merge.py` / `profile_backup.py`)
4. 若任一变更命中,在 `.plans/` 下新增 `profile-sync-upstream-spike-rev{N}.md`,重跑 Gap matrix,更新本 spike 的"Status"字段为 `SUPERSEDED by rev{N}`
5. 若一季度内无变更,在 `docs/aiseo-agent/NEXT_STEPS.md` 留一行 `YYYY-Q{n}: profile-sync spike re-review — no upstream changes, decision (c) still holds.`

### 6.3 不触发重评估的上游变更

以下变更**不影响**本 spike 决策,无需重评估:

- 上游对 `distribution.yaml` manifest 字段的纯增量扩展(新增 `env_requires` 子字段、metadata 字段等)
- 上游对 git URL 解析、ssh/https 支持的增强(#8 是上游独有,AISEO 不消费)
- 上游 `USER_OWNED_EXCLUDE` 列表的扩展(只要 distribution-owned 仍是"全替换"语义)

---

## 附录: Gap 严重性分类

```
BLOCKING (不可替换的理由):
  #2 additive list migration  — 运维核心,无上游等价
  #6 skills missing-only      — 数据安全,上游行为相反
  #13 atomic write/fsync      — durability/safety,上游裸 shutil.copy2 写入中途崩溃即损坏

SIGNIFICANT (替换后用户体验明显退化):
  #3 rolling backup           — config 修改安全网
  #7 YAML 注释保留            — 用户手改 config 可读性
  #5 refresh-soul 子命令      — SEO 特有运维工具

ACCEPTABLE LOSS (如果替换):
  #4 env warning (部分,上游有模板文件)
  #12 细粒度 skipped 报告

上游独有 (当前 AISEO 不需要):
  #8 git URL 安装
```

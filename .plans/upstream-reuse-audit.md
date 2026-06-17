# AISEO Fork 复用上游 Hermes 原生能力 — 审计与执行方案

## Metadata

- **Owner**: yujian(后续可在 ledger 中按项指派)
  - **Fallback**: 无人可指派时,默认 owner = 上次改该文件的 committer(`git log -1 --format='%ae' <file>`)
- **PR 命名**: `chore(aiseo-reuse): <topic>`(例: `chore(aiseo-reuse): replace _is_private_ipv4 with stdlib`)
- **分支命名**: `aiseo/reuse-<pri>-<topic>`(例: `aiseo/reuse-p0a-ipv4`)
- **关联文档**:
  - `.plans/cron-free-form-task.md` 是 P1-A 的设计前置,本方案 supersede 其中关于
    `create-from-memory` 去留的判断
  - P0-C 完成后会产出 `.plans/profile-sync-upstream-spike.md`
  - P2-C 完成后会产出 `.plans/upstream-push-ledger.md`(ledger = upstream push 跟踪表,
    本文档 P2-C 章定义其结构)
- **CI 集成路径**: P0-B / P2-B / P2-C 的检查脚本统一加入 `scripts/run_tests.sh` 入口
  调用链(具体 workflow 在 P2-C 实施时定义)
- **Lifecycle**(本方案文档的归宿):
  - P0-P1 完成 → 精华合并到 `ARCHITECTURE.md` 新增 ADR(profile sync 决策)+ `CLAUDE.md` fork delta 表
  - P2-C ledger 投产 → 本方案 P2-C 段移到 `CONTRIBUTING.md`
  - 全部完成 → 归档到 `.plans/archive/`(不删,保留 post-mortem 价值)
- **Docs synchronization checklist**(每个 P-X 完成时必勾):
  - P0-* / P1-A 改 plugin 行为 → 同步 `CLAUDE.md` "The aiseo-guard plugin" 段
  - P1-B 改 sync 行为 → 同步 `CLAUDE.md` "Profile bootstrap pattern" + `ARCHITECTURE.md` 相关章节
  - P2-A 改入口 → 同步 `CLAUDE.md` "Entry points" 表 + `ARCHITECTURE.md` §3 图 + §10 表
  - 任何项升格永久资产 → 同步 `CLAUDE.md` "fork delta" 表 + ledger
  - **`NEXT_STEPS.md` 不强制更新**:除非该变更直接影响用户操作步骤,否则只用 ledger 跟踪

## 目标

系统性识别 AISEO fork 中"自己写了一套、但 Hermes 上游已有原生能力"的代码点,
分清**必要 wrapper**(保留 + 最小化)、**真冗余**(直接复用)、**需上推上游的能力**
(独立 PR + 退出条件),给出可执行的 sprint 计划。

不是一次性大重构,而是建立一个**可持续的 fork delta 治理机制**。

## 核心判断原则(三问决策树)

对任何"AISEO 自己写了一套"的代码,依次问:

1. **删了 wrapper 后,上游是否仍能维持 safe by default?** — 否(删了就不 safe)→ **必留 wrapper**
2. **替代方案是否只需 ≤30 行 upstream patch?** — 是 → **推上游**
3. **AISEO 用户群外是否有人会用这个 patch?** — 是 → **推上游优先**

只有 (1)=否(删了不 safe)→ 永久保留 wrapper;三个都是 → 推上游。

**所有"推上游"项默认 6 周/2 release 超时,超时后升格为永久 AISEO 资产并固化维护策略。**

不能用的判断标准(显式禁用):

- "wrapper 一定是产品/安全边界" — 太宽泛,会变成豁免牌
- "推上游 = 长期"无截止 — 等同于无限延期
- "删了丢失语义"单条反证 — 会把"推上游"和"必留"混在一起

## 优先级总表

| Pri | 项目 | 工时 | 触发条件 |
|---|---|---|---|
| **P0-A** ✅ DONE | `_is_private_ipv4` → `_is_private_host` 安全修复(6 RED → 15/15 GREEN,423/423 全套通过) | 实际 0.5d | 已完成(2026-05-19) |
| **P0-B** ✅ DONE | OutputGate `_PREFIX_PATTERNS` drift gate(35 baseline + 2 测试 + 425/425 全套通过) | 实际 1d | 已完成(2026-05-19) |
| **P0-C** ✅ DONE | Profile sync spike → 决策 (c) 永久 AISEO 资产(`.plans/profile-sync-upstream-spike.md` 256 行,13 行为点 gap matrix,设计哲学冲突论据 strong) | 实际 1.5d | 已完成(2026-05-19) |
| **P1-A** ✅ DONE | Cron equivalence + 老 job migration helper(`_is_aiseo_created_job` 多维识别 + 6 个新测试 + deprecation 文案对齐 2026-08-15 + ledger 9 列契约 + `_KNOWN_AISEO_SKILLS` drift gate) | 实际 2d | 已完成(2026-05-19) |
| **P1-B** ✅ DONE | Profile sync 永久资产化(ADR-001 + CLAUDE.md fork delta 更新 + seeds README + 3 个 BLOCKING gap protection tests + NEXT_STEPS 季度 review reminder) | 实际 2.5d | 已完成(2026-05-19) |
| **P2-A** ✅ DONE | `bin/aiseo` 收敛到 Python 入口(92→9 行,21 个 parity 测试 + PYTHON override 文档化) | 实际 0.5d | 已完成(2026-05-19) |
| **P2-B** ✅ DONE | `disabled_toolsets` ↔ `TOOL_BLOCKLIST` parity test(8 toolsets × 14 tools 全覆盖,双层防御无漏洞) | 实际 0.5d | 已完成(2026-05-19) |
| **P2-C** ✅ DONE | 6 周 ledger + CI deadline grep(进程替换 + 格式校验 + 3 分支测试 + lint.yml blocking job + PR template + GOVERNANCE gate 提示) | 实际 1d | 已完成(2026-05-19) |
| **P3** | `_parse_env_file` / `aiseo_cost_report.py` / DataForSEO retry verify-only | — | 进入 P2-C ledger(已上线),deadline = P2 完成 + 4 周 |

---

## P0-A: `_is_private_ipv4` 安全修复

### 关键反转 — 先写边界回归测试

前几轮分析直接判定"IPv6 私有地址(`::1`、`fc00::/7`)会绕过 `_is_private_ipv4`",
列为安全 bug。但实际链路上:

- `plugins/aiseo-guard/__init__.py:517` 的 `_SAFE_HOST_RE = ^[A-Za-z0-9.-]+$` **不接受 `:`**
- IPv6 host(原始格式)在调用 `_is_private_ipv4` 之前就已被拦
- `_is_private_ipv4` 在 `plugins/aiseo-guard/__init__.py:554-571`,唯一 caller 是
  `_normalize_public_url` (line 583-592)

需要验证的真实威胁面:

- `urlparse("http://[::1]/").hostname` 返回 `"::1"` → 会被 `_SAFE_HOST_RE` 拦吗?
- `fe80::1%eth0` zone identifier → `ipaddress.ip_address()` 会 `ValueError`
- `internal.corp` 未解析 hostname → 不被 `_SAFE_HOST_RE` 拦,也不被 `_is_private_ipv4` 拦
  (改前就存在的盲区,但和本 P0 无关)

### Prerequisite(必须先做)

1. 在 `tests/aiseo/test_input_gate_*.py` 先写边界回归测试覆盖 ≥6 个 IPv6 case
   (`::1`、`fc00::/7`、`fe80::/10`、`::ffff:127.0.0.1`、`[::1]:80`、`0:0:0:0:0:0:0:1`)
   - **若当前 pytest 已 RED** → 真有绕过,按 (b)(c) 修复路径执行
   - **若当前 pytest 已通过** → 已被上游链路其他环节拦住,本项**降级为 regression guard
     + 重构**;不要求"必须 RED"
2. `grep -rn _is_private_ipv4` 确认唯一 caller 是 `_normalize_public_url:589`
3. 若降级为重构,**触发显式 checklist**:
   - 在 PR 描述里写"降级原因:回归测试已通过,绕过被 X 拦住"
   - **新开 `refactor:` PR**(不复用 P0-A 的 PR / 分支)
   - 仍然保留"stdlib 替换 + 关闭未来回归面"的重构目标
   - 在 ledger 加一行 status=`degraded-to-refactor`

### 实现要点

```python
# 当前 (plugins/aiseo-guard/__init__.py:554-571)
def _is_private_ipv4(host: str) -> bool:
    # 手写 4 段 + CIDR 判断,18 行,无 IPv6

# 改后
import ipaddress
def _is_private_host(host: str) -> bool:
    """判定 host 是不是已知私有/loopback/link-local/reserved IP。
    
    若 host 不是 IP(普通域名),本函数不在此判定,return False,
    交给 caller 链路上的 .local / .internal / _SAFE_HOST_RE 等后续规则。
    """
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False  # 不是 IP → 不归本函数管,让后续规则决定
    return addr.is_private or addr.is_loopback or addr.is_link_local \
           or addr.is_unspecified or addr.is_reserved
```

**关键陷阱与边界**:
- `except ValueError: return True` 会把所有普通域名(`example.com`)误判为私有 → 全拒
- `except ValueError: return False` 是正确选择,**前提**是 caller 链路有其他规则
  接管 hostname(已确认: `_SAFE_HOST_RE` + `.endswith(".local")` + `.endswith(".internal")`)
- fail-closed 语义只适用于"看起来像 IP 但解析失败"的极端情况(如 zone identifier
  `fe80::1%eth0`);本函数因 caller 链路已过滤,不需要扛这种边界

**caller 链路盲区(必须同步在 `_normalize_public_url` 补丁)**:
现有 caller 只兜 `.local` / `.internal` / `localhost`,以下 hostname 因 `_is_private_host`
不再 fail-closed,而 caller 也没拦,会被**放行**:
- `*.corp` / `*.lan` / `*.intranet` / `*.home` / `*.localhost`(常见企业内网 TLD + RFC 6761)
- 无 dot 的纯主机名 `db01` / `intranet` / `redis`(本地 DNS 解析)
- 完全数字 hostname `12345`(部分内部命名约定)
- **十六进制 / 八进制 IP 表示**:`0x7f000001` / `0177.0.0.1`(`ipaddress.ip_address`
  在 Python 3.11 不接受非标准格式,会 `ValueError` → `return False` → 放行)

P0-A DoD 必须**同步给 `_normalize_public_url` 补一段拦截**:

```python
# 在 _normalize_public_url 中,_is_private_host(host) 调用之前/后加。
# 注:现有 _normalize_public_url(line 574)全部用 raise ValueError 风格,
#    line 592 已有同语义现成模板,新增拦截必须沿用,不能改成 return None。
PRIVATE_HOSTNAME_SUFFIXES = (
    ".corp", ".lan", ".intranet", ".home",
    ".local", ".internal", ".localhost",  # 后三者: RFC 6761 + 已有兜底加固
)
_PRIVATE_REJECT_MSG = (
    f"{field} must target a public website, not localhost/private/internal hosts."
)
if any(host.endswith(s) for s in PRIVATE_HOSTNAME_SUFFIXES):
    raise ValueError(_PRIVATE_REJECT_MSG)
if "." not in host:  # 无 TLD 的纯主机名一律视为内网
    raise ValueError(_PRIVATE_REJECT_MSG)
# 拒绝十六进制 / 八进制 IP 表示(stdlib ipaddress 不识别 → ValueError → 漏判)
import re
HEX_OCT_NUM_RE = re.compile(r"^(0x[0-9a-fA-F]+|0[0-7]+)$")
if all(HEX_OCT_NUM_RE.match(tok) or tok.isdigit() for tok in host.split(".")):
    if any(tok.startswith(("0x", "0X")) or (tok.startswith("0") and len(tok) > 1 and tok.isdigit())
           for tok in host.split(".")):
        raise ValueError(_PRIVATE_REJECT_MSG)
```

否则 P0-A 的"修 bug"变成"扩大盲区"(改前过严但 safe,改后过松但漏 SSRF)。

**已知局限(必须文档化、不在本 P0 修)**:
- **DNS rebinding**: `attacker.com` 解析到 `127.0.0.1`。字符串层防御无法阻止,
  需要在 HTTP 客户端层加 IP 绑定(`httpx` 的 `transport=httpx.HTTPTransport(local_address=...)`
  或 socket-level 校验)。**P0-A 不修**,作为已知 SSRF 局限记录,未来另开 P-X 处理
- **IDN Punycode**: `xn--p1ai` 解码后可能指向私有资源,字符串层无法防御 → 同上策略

### DoD

- (a) 边界回归测试存档(无论 RED 或已通过,都保留作为 regression guard)
- (b) 函数改名 `_is_private_host` + 改用 stdlib + `except ValueError: return False`
  (语义见"实现要点"段)
- (c) `tests/aiseo/test_input_gate_*.py` 含 IPv6 边界用例
  - **实施差异**: 阶段 1 测试发现 `_SAFE_HOST_RE` 统一拒绝 `:`,所有 IPv6 bracket 格式
    (`[::1]` / `[fe80::1]` / `[::ffff:127.0.0.1]` 等)在 character set 层就被拦,
    无需逐个枚举。**1 个代表 case** (`http://[::1]/`) 足以覆盖整条防御链路;
    额外在 `_SAFE_HOST_RE` 定义处加注释 `# SECURITY BOUNDARY: must not accept colon`
    作为防御纵深(防未来有人为支持 port 扩展 RE 而打破 IPv6 拦截)
- (d) 同步给 `_normalize_public_url` 补 `PRIVATE_HOSTNAME_SUFFIXES` + 无 dot 兜底
  (见"caller 链路盲区"段),修复 `*.corp` / `*.lan` / `db01` 的 SSRF 漏洞
- (e) 新增具体 hostname 测试 case:
  - `example.com` → `_is_private_host()` 返回 `False`,`_normalize_public_url()` 不拦
    (fail-open 防御性测试)
  - `db01` → `_normalize_public_url()` 拦截(无 dot 兜底)
  - `app.corp` / `intranet.lan` → `_normalize_public_url()` 拦截
  - `service.local` → `_normalize_public_url()` 拦截(已有兜底)
  - `x.localhost` → `_normalize_public_url()` 拦截(`.localhost` RFC 6761)
  - `169.254.169.254` → `_normalize_public_url()` 拦截(AWS metadata, link-local)
  - `http://0177.0.0.1/` → `_normalize_public_url()` 拦截(八进制 IP)
  - `http://0x7f000001/` → `_normalize_public_url()` 拦截(十六进制 IP)
  - `http://[::1]/` → `_normalize_public_url()` 拦截(IPv6 loopback,虽然被 `_SAFE_HOST_RE` 先拦,但验证完整链路)
  - `http://user@evil.com/` → `_normalize_public_url()` 拦截(已有 `parsed.username` 检查兜底回归)

**Rollback**: `git revert <commit>`;回归测试保留(降级为 regression guard)。

---

## P0-B: OutputGate `_PREFIX_PATTERNS` drift gate

### 问题

`plugins/aiseo-guard/__init__.py:1491-1570` 的 `OUTPUT_REDACT_PATTERNS` 复制了
`agent/redact.py:70-106` 的 vendor prefix 列表(注释 line 1502 自承"copied (not imported)
to keep plugin self-contained")。

上游 `agent/redact.py` 加新 prefix(最近的 `brv_` / `mem0_` 等)时,plugin 不会自动跟上。

### 错误的解法(已排除)

- ❌ **数量相等**: 上游加 1 个 + AISEO 加 1 个 → 计数不变,假阳性
- ❌ **AISEO 是上游超集**: 上游 `sk-{10,}` vs AISEO `sk-{20,}` 字符串不等 → CI 长期红 → 被 disable
- ❌ **正则语义等价自动判定**: 不可能

### 正确解法

维护 `AISEO_REDACT_PINNED_COPY: list[str]`(纯字符串列表,人工 pin 的上游 baseline):

```python
# tests/aiseo/test_outputgate_drift.py
# 注: agent.redact._PREFIX_PATTERNS 是 list[str](pattern 字符串,非编译后 Pattern)
# 注: plugins/aiseo-guard/ 目录含连字符,实际可 import 路径需通过 plugin loader
#     注册的模块名,以 plugin.yaml 中声明为准(常见为 aiseo_guard 下划线形式)
from agent.redact import _PREFIX_PATTERNS

def test_no_upstream_prefix_missing_from_pinned():
    from aiseo_guard import AISEO_REDACT_PINNED_COPY  # 实际 import 路径以 plugin loader 为准
    missing = set(_PREFIX_PATTERNS) - set(AISEO_REDACT_PINNED_COPY)
    assert not missing, (
        f"上游新增 {missing},需手动决策是否同步到 OutputGate"
    )
```

上游加 → CI 红 → 开发者**手动决策**是否同步到 pinned copy + OutputGate。
测的是 **gate**,不是语义等价。

触发后行为分两层:
- **CI 层 fail-closed**: 测试红 → 阻塞 merge,强制开发者手动决策同步 pinned copy
- **Runtime 层 WARN-only**: plugin 加载时若 pinned copy 与上游不一致,仅 stderr WARN,
  不 raise/不 fail-closed — fail-closed 会让上游一次合法更新就 break 所有 AISEO 用户运行时

### Prerequisite

1. **开工当天重新核查 baseline**(覆盖文档硬编码值):
   - 跑 `python -c "from agent.redact import _PREFIX_PATTERNS; print(len(_PREFIX_PATTERNS))"`
   - 2026-05-19 核查值为 35 条,延后开工时上游可能已增减
2. 验证 `from agent.redact import _PREFIX_PATTERNS` 在 plugin import 时不会循环依赖
3. 如果会循环,改为 lazy 触发(第一次 `transform_llm_output` 调用时检查)
4. 确认 plugin loader 注册的模块名(连字符 `aiseo-guard` 在 Python import 路径中需替换)
5. 同步更新 `scripts/run_tests.sh`,把 `test_outputgate_drift.py` 挂入调用链;
   本地跑 `bash scripts/run_tests.sh tests/aiseo/test_outputgate_drift.py` 确认不被 skip

### DoD

- `AISEO_REDACT_PINNED_COPY` 常量定义,初始值含 35 条 baseline(开工当天重核)
- `tests/aiseo/test_outputgate_drift.py` 新增 + CI 必跑
- **反向 drift 不报警**(设计决定,需写注释): 如果上游**删除**某 prefix 而 AISEO 仍保留,
  测试不会红。理由: 拦多不拦少 = 安全侧;但 pinned copy 会出现僵尸 pattern,需要在
  季度 review 时人工清理。测试文件头注释说明此设计决定。
- **行为测试(补 1 个)**: 把上游某近期新增 prefix(如 `brv_abc123` / `mem0_xyz`)送入
  `_output_gate`,断言实际被 `[REDACTED_API_KEY]` 替换 —— 验证 pinned copy 更新后
  OutputGate 真的同步了拦截,而不只是 CI 报警
- 基础版工时 **1-2 天**(pinned copy + missing check + 反向 drift 注释 + 行为测试)
- 仅当需要验证"OutputGate 不与 `agent/redact.py` 二次替换破坏 token"时,扩到 30+ 整合
  测试,此时工时 **3-5 天**;要不要扩看 P0-B 实施时的实际风险面,**不强制**

**Rollback**: 移除测试文件 + 移除 `AISEO_REDACT_PINNED_COPY` 常量。无运行时影响。

---

## P0-C: Profile sync upstream spike

### 为什么是 P0(不是 P1 spike)

`aiseo_cli.py` 中的 sync 实现是 fork 中最大重叠点:

| AISEO 位置 | 上游对应 |
|---|---|
| `aiseo_cli.py:108` `_sync_profile` | `hermes_cli/profile_distribution.py:582` `install_distribution()` |
| `aiseo_cli.py:173` `_find_list_block`(YAML 文本编辑器,~200 行) | (上游无 additive list migration) |
| `aiseo_cli.py:363` `_rolling_backup` | (上游无 backup 机制) |
| `aiseo_cli.py:400` `_migrate_profile_config` | `hermes_cli/profile_distribution.py:625` `update_distribution()` |
| `aiseo_cli.py:87` `SEED_TRACKED_LIST_FIELDS` | (上游无对应概念) |
| `aiseo_cli.py:71` `NEVER_OVERWRITE_FILES` | `hermes_cli/profile_distribution.py:98` `USER_OWNED_EXCLUDE` |
| `aiseo_cli.py:757` `_check_plugin_env_requirements` | (上游 plugin loader 不在 startup 扫 `requires_env`) |

约 **624 行** AISEO sync 代码(`aiseo_cli.py:108-731`),其中 ~200 行手写 YAML 文本编辑器
是因为不愿用 `yaml.dump` 重写文件而发明的脆弱实现。

Spike 失败成本(~1.5 天读上游 + 写 gap matrix)远低于推迟成本(每次 seed 改动都要双写)。
**spike 本身是 P0**,refactor 留 P1。

### Spike 输出(必须)

新文件 `.plans/profile-sync-upstream-spike.md`,包含:

1. **Gap matrix**: 上游 `profile_distribution.py` 当前能力 vs `aiseo_cli.py::sync`
   12 个行为点逐项 ✓/✗/部分
   - NEVER_OVERWRITE_FILES 保护
   - SEED_TRACKED_LIST_FIELDS additive list migration
   - `config.yaml.bak.*` 滚动备份(5 槽)
   - env warning block
   - `--refresh-soul` SOUL backup 覆盖
   - skills 目录粒度 missing-only
   - YAML 注释/anchor/缩进保留
   - 其他...
2. **3 选 1 决策**:
   - (a) 直接复用上游 → 删 AISEO sync
   - (b) 推上游 PR 补能力(列出 surface 变更)→ 6 周 ledger
   - (c) 保留 AISEO 私有 + 文档化为永久资产
3. **危险检查**: 替换是否会绕过 `_rolling_backup`?用户手改的
   `~/.hermes/profiles/aiseo/config.yaml` 是否会被新机制无警告覆盖?

### Prerequisite

1. 读 `hermes_cli/profile_distribution.py` 全文(line 1-700),理解 `install/update` 完整调用链
2. spike 期间**禁止改** `aiseo_cli.py::_sync_profile` 及相关函数,**禁止写** `cron/` 目录
   (读 cron/ 目录确认 seed 语义是允许的;并保证 P1-A 可并行)
3. 拉一份现有用户 `~/.hermes/profiles/aiseo/config.yaml` 样例(redacted),作为 spike 时的对照
4. **历史归因调查**(必做,避免重蹈覆辙): 跑
   `git log --follow hermes_cli/profile_distribution.py` 和
   `git log --follow aiseo_cli.py` 对照 commit 时间线,定位"AISEO 当初为何没用上游"——
   可能性: (a) sync 写于 distribution.py 之前;(b) distribution.py 不支持单向 seed→profile;
   (c) 当时 owner 未发现。结论写入 spike doc 的开头

### DoD

- `.plans/profile-sync-upstream-spike.md` 文件存在
- 文件内含**历史归因结论**(Prerequisite #4)在文档开头
- 文件内含**完整 gap matrix**(12 个行为点逐项 ✓/✗/部分,不允许"暂未评估")
- 文件内含**明确 3 选 1 决策**,(a)/(b)/(c) 必选其一并附理由
- 至少 1 名 reviewer 在 spike PR 上 sign-off(`Approved`);因本 repo 无 CODEOWNERS,
  必须在 PR description 里 `@tag` 具体 GitHub username 并等待显式 review,
  不允许 self-merge
- 不需要写任何代码原型

**Rollback**: spike 是纯文档产出,无 rollback 需要;若决策事后被证伪,重开新 spike。

---

## P1-A: Cron equivalence 测试 + 老 job migration

### 背景

`aiseo cron create-from-memory` (`aiseo_cli.py:1098` `_run_cron_create_from_memory`)
和 `aiseo_schedule_task` 的 freeform path 是两条解决同一问题的路径,
prompt 模板维护两份必然漂移。计划:补对照测试 → deprecate → 删除。

### 关键陷阱:老 job 孤儿问题

`_run_cron_create_from_memory` 创建的老 job 的 `enabled_toolsets` 字段
**根本不存在**(`hermes cron create` 命令行不传该字段)。

`plugins/aiseo-guard/__init__.py:1088` `_is_aiseo_created_job` 检测:

```python
toolsets in (_AISEO_LEGACY_TOOLSETS, _AISEO_FREEFORM_TOOLSETS)
# job.get("enabled_toolsets") = None → 不匹配任何一个 → False
```

后果: 删 subcommand 后,**老 job 变成孤儿 — `aiseo_manage_scheduled_tasks` 看不到、
用户无法 list/cancel,但 cron 系统继续运行它们**。

### Migration helper(开删前必做)

```python
# 以下为伪代码,list_all_aiseo_jobs / patch_job 需对照 cron/jobs.py 实际 API 调整

# 选项 A:扫所有现存 job,给老 job 回填 enabled_toolsets
def migrate_legacy_jobs():
    for job in list_all_aiseo_jobs():
        if job.get("enabled_toolsets") is None:
            patch_job(job.id, enabled_toolsets=_AISEO_LEGACY_TOOLSETS)

# 选项 B:扩展 _is_aiseo_created_job,多维度识别老 create-from-memory job
# 注:_SCHEDULE_LABEL_RE 实际是 "^Schedule label: (daily|weekly|...)",
#    所有 cron job 都会带 schedule label,不能用作判别条件
_LEGACY_FROM_MEMORY_PREFIXES = (
    "Run seo-weekly-report on ",
    "Run technical-seo-audit on ",
    "Run keyword-opportunity for ",
    "Run competitor-analysis with ",
)
_KNOWN_AISEO_SKILLS = frozenset({"seo-weekly-report", "technical-seo-audit",
    "keyword-opportunity", "competitor-analysis", "content-brief",
    "growflare-seo"})

def _is_aiseo_created_job(job):
    if job.get("enabled_toolsets") in (_AISEO_LEGACY_TOOLSETS, _AISEO_FREEFORM_TOOLSETS):
        return True
    # 老 create-from-memory job 多维度识别(全部满足才算)
    if job.get("enabled_toolsets") is not None:
        return False  # 老 job 此字段必为 None
    if any(job.get(k) for k in ("script", "no_agent", "workdir", "context_from")):
        return False  # 老 job 这些字段都是空
    skills = job.get("skills") or []
    if skills and not all(s in _KNOWN_AISEO_SKILLS for s in skills):
        return False  # 含未知 skill 不算 AISEO 创建
    prompt = job.get("prompt", "")
    # 条件 1: prompt 命中旧 create-from-memory 四个 prefix
    if any(prompt.startswith(p) for p in _LEGACY_FROM_MEMORY_PREFIXES):
        return True
    # 条件 2: name 以 aiseo- 开头 AND skills 是已知 AISEO skill 子集(非空)
    # 单看 name 太宽,用户自建 "aiseo-test" 会被误收编;必须复合判定
    name = (job.get("name") or "").lower()
    skills = job.get("skills") or []
    if name.startswith("aiseo-") and skills and all(s in _KNOWN_AISEO_SKILLS for s in skills):
        return True
    return False
```

**推荐 B**(纯读、零迁移、向后兼容)。

**`_KNOWN_AISEO_SKILLS` 同步保护**(drift gate,与 `AISEO_REDACT_PINNED_COPY` 对称):

```python
# tests/aiseo/test_known_skills_drift.py
# 防止 seeds/aiseo-profile/skills/ 增删 skill 时常量偷偷漂移导致老 job 孤儿
from pathlib import Path

SKILLS_DIR = Path("seeds/aiseo-profile/skills")

def test_known_aiseo_skills_matches_seed_directory():
    seed_skills = {d.name for d in SKILLS_DIR.iterdir() if d.is_dir()}
    # 引入实际常量(通过 aiseo_guard fixture 或直接读 plugin 文件)
    assert seed_skills == _KNOWN_AISEO_SKILLS, (
        f"_KNOWN_AISEO_SKILLS 与 seed 目录不一致: "
        f"多余={_KNOWN_AISEO_SKILLS - seed_skills}, "
        f"缺失={seed_skills - _KNOWN_AISEO_SKILLS}"
    )
```

上游 / seed 新增 skill 时 → CI 红 → 强制开发者手动同步常量。

**为什么不用 `_SCHEDULE_LABEL_RE`**: 它只是频率/时间标签(`^Schedule label: weekly at ...`),
**所有 cron job** 都会被自动加上,根本无法区分 AISEO 创建 vs 用户自建。误用会让用户自建的
普通 cron job 被 `aiseo_manage_scheduled_tasks` 收编,未来批量 cancel 误删非 AISEO 用户 job。

**4 个 prefix 来源**: `aiseo_cli.py:994/1009/1040/1066` 中 `_build_*` 实际生成的模板,
对照 `seeds/aiseo-profile/cron/*.json` 的 `prompt_template` 字段已验证。

### 等价测试金字塔

| 层 | 断言 | 成本 | CI |
|---|---|---|---|
| **L1 静态** | freeform 经 `aiseo_skills_read` mock 后注入的 MEMORY sha256 == `_build_*` MEMORY sha256;schedule/skill_name/deliver 严格相等 | 0 | 每次 |
| **L2 录制回放** | `respx`/`vcr` 录制一次 LLM 调用,两路径工具调用序列集合相等 | 0 | 每次 |
| **L3 LLM smoke** | 真调 1 次/skill,断言最终 deliverable schema 字段集相等 | ¥4-12 | 手动 + release sign-off |

**最小可落地**: L1 必须(≤4h),L2 在 deprecate 前必须,L3 仅 delete 当日跑一次。

**关键 CI 隔离**: L3 LLM smoke **永不进 `scripts/run_tests.sh`**,只能放在 `tests/aiseo_llm/`
(已有 `AISEO_SMOKE_CONFIRMED=1` guard 保护)。L1/L2 进 `tests/aiseo/` 走 CI。
**禁止**把 L3 文件放到 `tests/aiseo/` 子目录下(`tests/aiseo/__init__.py` 会自动收集 = ¥)。

### Prerequisite

1. 把测试金字塔设计写进 `.plans/cron-free-form-task.md`(已存在),reviewer 先 challenge 测试设计
2. 扫现有 `~/.hermes/profiles/aiseo/cron/` 里 legacy job 数量,确认 migration helper 覆盖面

### DoD

- (a) `_is_aiseo_created_job` 加回溯识别(选项 B)
- (b) `tests/aiseo/test_cron_freeform_equiv.py` 4 个对照测试(每个 `_build_*` 一个)L1 全过
  - 文件头加注释 `# TODO: delete this file when create-from-memory subcommand is removed`
- (c) `aiseo_cli.py` subcommand 入口打印 deprecation warning(`stderr` 输出
  `[DEPRECATION] aiseo cron create-from-memory will be removed in <release tag>;
  use aiseo_schedule_task with freeform prompt instead`,无 `--no-warn` 退路)
- (d) 文件头注释 `# AISEO_DEPRECATION_DEADLINE: YYYY-MM-DD`(配合 P2-C CI grep)
- (e) ledger 加一行(`Delete-by` 字段填代码删除日期 / `Deadline` 字段填上游 PR 截止日;
  两者**不同概念,不复用同一列**;**不**重复写入 `docs/aiseo-agent/NEXT_STEPS.md`)
  - **本地验证**: P1-A 落地时 P2-C 的 CI 集成可能还未就绪。开发者必须立即在本地跑
    `bash scripts/check_deprecation_deadlines.sh`(若脚本未就绪则在 PR 中显式声明
    "P2-C 就绪前 deadline 监控为人工"),并把脚本输出截图贴到 PR 描述
- (f) **端到端可见性测试**(防止 helper 返回值绿但实际 list 失败): 构造一个老 job
  (无 `enabled_toolsets`,prompt 以 `Run seo-weekly-report on ` 开头)写入 cron store,
  调用 `aiseo_manage_scheduled_tasks(action="list")`,断言该 job 出现在返回结果
- (g) **migration helper false-positive 测试**(防止误判用户自建 job): 构造一个用户
  自建 cron job(prompt 含 `use the keyword-opportunity tool to ...` 自然语言),
  断言 `_is_aiseo_created_job(job) is False`
- (h) **`_isolate_cron` 抽 fixture**: 移到 `tests/aiseo/conftest.py` 作 `@pytest.fixture`,
  消除 `test_aiseo_schedule_task.py:14` + `test_aiseo_schedule_task_freeform.py:18` 重复

**Rollback**: `git revert` 三处改动;老 cron job 在选项 B 下不受影响(纯读 wrapper)。

---

## P1-B: Profile sync refactor

视 P0-C spike 的 3 选 1 决策定,每条分支有独立 DoD:

**分支 (a) 复用上游**
- DoD: `aiseo_cli.py::_sync_profile` 及其 11 个 helper 函数删除 → 改 call 上游
  `hermes_cli.profile_distribution.install_distribution()` / `update_distribution()`
- 净减 ~350 行,新增 ≤20 行 adapter 代码
- 现有 `tests/aiseo/test_sync_*.py` 全过(零回归)
- 至少 1 个 manual e2e: 在干净 `~/.hermes/` 跑 `aiseo sync` + `aiseo sync --refresh-soul`
- 粗估工时: **3-5d**
- **Rollback**: `git revert` + 恢复 sync helper 函数(测试套件可作为完整性参考)

**分支 (b) 推上游 PR 补能力**
- DoD: 上游 PR opened + ledger 行新增 + 6 周 deadline 标定 + ledger 的 `upstream_health` 字段填写
- AISEO 本地实现保持现状,等上游 merge 后再切
- 粗估工时: PR 起草 1d + 跟进 ledger 持续运作
- **"上游拒绝"定义**(机械可判定): PR 状态变为 `closed` 且未被 merge,
  **或** 30 天无 maintainer 任何响应(comment/review/label)
- **Rollback**: 上游拒绝 → owner 必须在 ledger 把 Status 改为 `rejected`,
  并在 **1 周内** 开 (c) 分支 PR;月度 review 时若发现 `rejected` 超过 1 周未开 (c) PR,
  默认升格为 (c) 由 maintainer 强制推进

**分支 (c) 保留永久 AISEO 资产**
- DoD: `aiseo_cli.py` 中 sync 模块抽出独立 `aiseo_cli/sync.py` 文件
- `docs/aiseo-agent/ARCHITECTURE.md` 新增 ADR 段说明"为何不复用上游"
- `CLAUDE.md` "fork delta" 表更新
- 粗估工时: **1.5d**
- **Rollback**: 这就是 rollback 终态,无需进一步 rollback

---

## P2-A: `bin/aiseo` 收敛到 Python 入口

当前 `bin/aiseo` 93 行,`aiseo_cli.py` 中 Python 入口同样实现 brand switch + bootstrap。
parity 靠人记得,容易漂移(CLAUDE.md "两 CLI 入口必须 stay in parity"段)。

### Prerequisite

1. 验证 `python -m aiseo_cli` 可直接运行(确认 `aiseo_cli.py` 模块结构支持 `-m` 调用)
2. 列举 `bin/aiseo` 当前承担但 `aiseo_cli.py` 未覆盖的行为(如 PATH 探测、虚拟环境激活),
   迁移到 Python 入口或确认可下沉到环境变量
3. 在 fresh clone(无 `.venv`)上跑一次 `./bin/aiseo --help` 留 baseline

### 实现

`bin/aiseo` 减到 ≤10 行,仅 PATH/env + `exec python -m aiseo_cli "$@"`:

```bash
#!/usr/bin/env bash
# 见 CLAUDE.md "Entry points" 段
export AISEO_BRAND_ACTIVE=1
exec python3 -m aiseo_cli "$@"
```

### DoD

- `bin/aiseo` ≤10 行
- `tests/aiseo/test_dual_entry_parity.py` 新增,覆盖所有 subcommand 的 stdout/exit-code 一致性
- CLAUDE.md "Entry points" 段更新

**Rollback**: `git revert` `bin/aiseo` 改动 + 移除 parity 测试。

---

## P2-B: `disabled_toolsets` ↔ `TOOL_BLOCKLIST` parity test

`seeds/aiseo-profile/config.yaml:42-53` 的 `disabled_toolsets` (8 项: terminal /
code_execution / delegation / messaging / file / skills / cronjob / image_gen)
和 `plugins/aiseo-guard/__init__.py:166` 的 `TOOL_BLOCKLIST` 是**双层防御**
(boot 时不加载 vs dispatch 时拦截),不是重复。

但 `cronjob` 同时在两边出现,没有任何机制保证未来加新 toolset 时两边都改。

### DoD

- (a) 测试文件 `tests/aiseo/test_toolset_blocklist_parity.py` 存在且实现以下断言
- (b) 同步更新 `scripts/run_tests.sh`,把该测试挂入 CI 调用链
- (c) 本地跑 `bash scripts/run_tests.sh tests/aiseo/test_toolset_blocklist_parity.py` 确认通过

```python
# tests/aiseo/test_toolset_blocklist_parity.py
# 关键:
# - config.disabled_toolsets 是 toolset 名(整体),TOOL_BLOCKLIST 是 tool 名(单工具)
# - 用 toolsets.resolve_toolset(name) -> List[str](toolsets.py:579)展开稳定 API
# - plugins/aiseo-guard/ 含连字符,Python import 不可用,通过现有 aiseo_guard fixture /
#   plugin loader 导入(见 tests/aiseo/conftest.py)
from toolsets import resolve_toolset

def test_disabled_toolsets_all_tools_actually_blocked(aiseo_guard):  # fixture
    _is_blocked_tool_name = aiseo_guard._is_blocked_tool_name
    config_disabled = load_seed_config()["agent"]["disabled_toolsets"]
    for toolset_name in config_disabled:
        for tool_name in resolve_toolset(toolset_name):  # 返回 List[str]
            assert _is_blocked_tool_name(tool_name), (
                f"toolset '{toolset_name}' 在 config 禁用,但其 tool '{tool_name}' "
                f"未被 _is_blocked_tool_name 拦截,双层防御失效"
            )
```

**Rollback**: 删除测试文件 + 还原 `scripts/run_tests.sh` 调用。

---

## P2-C: 6 周 ledger + CI deadline grep

### 双层 self-policing 机制

**Layer 1 — Ledger 文件**: `.plans/upstream-push-ledger.md`,markdown 表格:

```
| Topic | Started | PR URL | Deadline | Delete-by | Owner | Status | Upstream Health | Decision-if-expired |
|---|---|---|---|---|---|---|---|---|
| profile-sync → profile_distribution | 2026-05-20 | (none yet) | 2026-07-01 | n/a | yujian | spike | active | 永久 AISEO 资产 |
| outputgate-prefix-upstream | (TBD) | (TBD) | (TBD) | n/a | yujian | not-started | active | 保留 pinned copy gate |
| cron-create-from-memory deprecation | 2026-06-01 | n/a | n/a | 2026-08-15 | yujian | deprecating | n/a | 即删 |
```

**字段语义区分**:
- `Deadline` = 上游 PR 接受/拒绝的截止日(6 周/2 release);**仅"推上游"项填**
- `Delete-by` = 本地代码计划删除日(deprecation 期结束);**仅"删本地"项填**
- 两个字段**默认互斥**(`n/a` 填空);唯一例外:本地 deprecate 期内同时尝试推上游
  (rare),需在 `Decision-if-expired` 列说明原因(联动规则 R4)

**Upstream Health 字段**(开 PR 前必填):
- `active` — 上游近 90 天有 maintainer 活动且接受外部 PR
- `stale` — 90 天无 maintainer 响应,跳过 (b) 分支直接走 (c)
- `closed-to-external` — 上游明确拒绝外部 PR(README/CONTRIBUTING 写明),不开 PR

**Status 字段允许值** (8 个): `not-started` / `spike` / `pr-open` / `pr-merged` /
`rejected`(closed 未 merge 或 30 天无响应)/ `graduated`(已升格永久资产)
/ `degraded-to-refactor`(P0-A 等降级路径)/ `deprecating`(本地 deprecation 期内,
即将删除)

**Status 状态机转换表**(允许的转换弧,其他转换非法):

```
not-started ──→ spike | pr-open | deprecating | degraded-to-refactor
spike       ──→ pr-open | rejected | degraded-to-refactor
pr-open     ──→ pr-merged | rejected
pr-merged   ──→ graduated
rejected    ──→ deprecating | graduated   (拒绝后:要么本地删,要么升格永久资产)
deprecating ──→ [terminal: 代码删除完成 → ledger 行归档]
graduated   ──→ [terminal]
degraded-to-refactor ──→ spike   (重新评估时可回到 spike)
```

**字段联动规则**(P2-C ledger 内不变式):
- R1: `Upstream Health = closed-to-external` → `Deadline = n/a`
- R2: `Status = rejected` → 下次 monthly review 前必须 transition 到 `deprecating` 或 `graduated`
- R3: `Status = pr-open` AND `Upstream Health = closed-to-external` → 非法组合,
  必须在 1 周内更新 `Status` 为 `rejected`
- R4: `Deadline` 和 `Delete-by` **默认互斥**;若同时填(例如本地 deprecate 期内同时
  推上游),必须在 `Decision-if-expired` 列说明原因

每月第一个周一 maintainer review。**写入责任**: 每开"推上游"PR 必须同步改 ledger
(PR template checkbox)。

**Layer 2 — 代码内 deadline 注释 + CI grep**:

在临时 wrapper 文件头插一行:

```bash
# AISEO_DEPRECATION_DEADLINE: 2026-07-01
```

CI 加 `scripts/check_deprecation_deadlines.sh` 每次 PR 跑:

```bash
#!/usr/bin/env bash
# 关键 bash 陷阱:`grep | while ... exit 1; done` 中 while 在子 shell,exit 只退子 shell。
# 必须用进程替换 `while ... done < <(grep ...)` 让 while 运行在父 shell 才能正常 exit。
set -euo pipefail
TODAY=$(date +%Y-%m-%d)
DATE_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
FAILURES=0

while IFS= read -r line; do
    # 提取 deadline 值(去掉前缀文本和末尾注释)
    raw=$(echo "$line" | sed -E 's/.*AISEO_DEPRECATION_DEADLINE:[[:space:]]*//' | awk '{print $1}')
    if ! [[ "$raw" =~ $DATE_RE ]]; then
        echo "[FORMAT-ERROR] $line  (deadline='$raw' 不匹配 YYYY-MM-DD)" >&2
        FAILURES=$((FAILURES+1))
        continue
    fi
    if [[ "$raw" < "$TODAY" ]]; then
        echo "[EXPIRED] $line" >&2
        FAILURES=$((FAILURES+1))
    fi
done < <(grep -rn "AISEO_DEPRECATION_DEADLINE:" --include="*.py" --include="*.sh" .)

# 区分退出码:格式错优先(实现 bug)> 过期(治理违约)
if [[ "$FAILURES" -gt 0 ]]; then
    # 简化:任一失败都 exit 1;若需区分 exit 2,在循环中改用临时文件标记
    exit 1
fi
```

**脚本规则**:
- deadline 值必须严格匹配 `YYYY-MM-DD`,不允许 `TBD` / 空 / 中文
- 用 `< <(grep ...)` 进程替换避免 bash subshell `exit` 陷阱
- `set -euo pipefail` 防 silent failure
- 收集所有违规(不在循环中立即 exit),输出完整诊断后再 exit
- `AISEO_DEPRECATION_DEADLINE` 必须只用于注释,不允许出现在 Python 赋值语句中

### 升格仪式(超时后 owner 1 周内必做)

1. PR `chore(aiseo): graduate <topic> to permanent fork asset`
2. 更新 `CLAUDE.md` "fork delta" 表
3. ledger Status 改为 `graduated`
4. 删除 NEXT_STEPS.md / ARCHITECTURE.md 中"长期推上游"措辞
5. 删除文件头 `AISEO_DEPRECATION_DEADLINE` 注释

### 为什么必须自动化

上游 4 个独立 PR 联合 merge 概率 ≈ 0.3⁴ ≈ **0.81%**。
默认假设是"现状即永久形态",不能让"长期推上游"变成永远的 TODO。

### Prerequisite

1. 先做一次 audit 把所有现有"长期推上游"承诺(散落于 `docs/aiseo-agent/NEXT_STEPS.md` /
   `ARCHITECTURE.md` / 本方案)迁入初始 ledger,确保不漏项
2. 与 maintainer 对齐每月 review 节奏(写入 `CONTRIBUTING.md` 或 team 日历)
3. 确认 repo CI 平台(GitHub Actions / 其他),用于 P2-C2 集成

### DoD

- (a) `.plans/upstream-push-ledger.md` 文件存在,初始至少包含本方案识别的所有
  "推上游"项(profile-sync / outputgate-prefix-upstream / pre_user_message 上游确认 /
  external content wrapping / additive list migration)
- (b) `scripts/check_deprecation_deadlines.sh` 存在 + 可执行 + **CI 中至少一个测试
  构造三分支**(format-error / expired / clean)各跑一次,断言对应 exit code 正确;
  不能只靠"本地手跑"
- (c) PR template(`.github/pull_request_template.md` 或等效位置)加 checkbox:
  "若本 PR 涉及推上游能力,我已同步更新 `.plans/upstream-push-ledger.md`"
- (d) 至少 1 个 CI workflow 调用 `scripts/check_deprecation_deadlines.sh`,
  pipeline 红时阻塞 merge
- (e) ledger 作为推上游/deprecation 追踪的**单一信息源**;
  **不**在 `docs/aiseo-agent/NEXT_STEPS.md` 加重复指针(避免双写漂移)

**Rollback**: 删除 4 个产出物(ledger / 脚本 / template checkbox / workflow 步骤)。

---

## P3: 小重复(有空再处理)

| 项 | 位置 | 评估 |
|---|---|---|
| `_parse_env_file` | `aiseo_cli.py:732-754` | 23 行,语义和 `hermes_cli/config.py:4315` `load_env` 略有不同(诊断 vs 注入),收益小 |
| `aiseo_cost_report.py` 硬编码 pricing | `scripts/aiseo_cost_report.py:30` | 独立 devops 脚本,有 `--pricing-file` 覆盖,不在主路径 |
| DataForSEO retry 逻辑 | `plugins/dataforseo/` | 上游无 HTTP client toolset,大概率不冗余 — **verify-only**,不动 |

---

## 应该上推 Hermes 的三个能力

(独立 PR,纳入 P2-C ledger,6 周超时升格;不新开 P-X 章节,因为当前无代码变更)

1. **`pre_user_message` hook** — 本 fork/core 中已存在(`hermes_cli/plugins.py:151`
   的 `VALID_HOOKS` 已注册),但**是否已进入 NousResearch upstream 尚未确认**。
   - **TODO(开任何相关 PR 前必做)**: 跑
     `git log --oneline upstream/main -- hermes_cli/plugins.py | grep pre_user_message`
     (或对应 remote 名)验证 merge 状态;未确认前**不得**在 PR description 里声称"已上游"
2. **`<untrusted_external_content>` 包装** — `plugins/aiseo-guard/__init__.py`
   `transform_tool_result` 实现的 indirect prompt injection 防御,任何用 web/browser
   的 profile 都需要
3. **Additive list migration** — `aiseo_cli.py::_migrate_profile_config`,
   distribution-update 通用需求

---

## 不动的范围(明确写入)

- **4-hook guard 架构骨架**(pre_user_message / pre_tool_call / transform_tool_result / transform_llm_output)
- **`aiseo_schedule_task` wrapper 本身**(`plugins/aiseo-guard/__init__.py:820` 起,合理薄壳)
- **`TOOL_BLOCKLIST`**(`plugins/aiseo-guard/__init__.py:166`,防御纵深)
- **SOUL.md 软规则**
- **`tests/aiseo_runtime_audit/` 4-axis harness**(真 multi-home isolation,上游做不到)
- **`OUTPUT_REDACT_PATTERNS` 中 SEO 特定的工具名改写 / 路径 / traceback patterns**
  (是 AISEO 独有产品语义,vendor prefix 部分才需 drift gate)

---

## 测试套件本身的盲点(顺手修)

`tests/aiseo/test_aiseo_schedule_task_freeform.py`:

- `test_freeform_prompt_scanned_for_injection` 断言过弱(`success is False` + 字符串包含
  `block`/`threat`,scan 函数被注释掉、其他校验失败也能让测试绿)
- `test_freeform_prompt_includes_hardening_directives` 用 `or` 让一半模板缺失也通过
- `_isolate_cron` 未抽 fixture(grep `cron/jobs.py` 未发现 `_jobs_cache`,
  无显式 cache 污染风险,但抽成 fixture 可减少重复并保证隔离一致)

P1-A 开工前顺手修,否则金字塔搭在沙地上。

---

## 推荐 Sprint 顺序

| Sprint | 内容 | 平行/串行 |
|---|---|---|
| **S1** | P0-A(先写边界回归测试,据是否 RED 决定修 bug 还是降级重构) + P0-C(profile sync spike) | 并行 |
| **S2** | P0-B(drift gate)+ P1-A(cron L1 测试 + migration helper) | 并行;P1-A 与 P0-C 并行的前提是 spike 不触碰 `cron/` 目录(spike 仅读 + 写文档) |
| **S3** | P1-B(profile sync refactor,视 spike 决策) + P2-A(`bin/aiseo` 收敛) | 并行 |
| **S4** | P2-B(parity test)+ P2-C(ledger + CI deadline grep) + 文档清理 | 并行 |

每 Sprint = 1-2 工作日单元,非日历周。

## 工作量估算

| 阶段 | 代码净减 | 新增测试 | 工时 |
|---|---|---|---|
| P0 三项 | -20(IPv4) | +6 用例(IPv4) +1 文件(drift gate) +0(spike doc) | 5-7d(P0-B 3-5d 是主要不确定性) |
| P1-A | -250(create-from-memory subcommand,deprecation 生效后) | +4 用例(cron equiv) +老 job 兼容 | 2d |
| P1-B | spike-dependent(分支 a: -350 行;分支 b: 0;分支 c: -0 重排) | 视分支 | 1.5-5d(分支 a 最大) |
| P2 三项 | -80(bin/aiseo) | +1 文件(parity) +1 ledger + 1 脚本 + 1 workflow | 2d |
| **合计** | **确定 -350 行 + 视 P1-B 决策追加** | **~12 测试用例 + 2 ledger 机制** | **确定 9-11 工作日 + P1-B refactor TBD** |

## 总原则一句话

**保留有 AISEO 独有语义的薄 wrapper、修真实安全 bug(先 RED 验证)、用 pinned-copy gate 防漂移、
用 ledger 防"长期推上游"成空话、所有清理动作都先有边界回归测试 + 老数据迁移路径,再动手。**

## Success Metrics(完成后可观测的变化)

| 指标 | Baseline | 目标 | 测量方法 |
|---|---|---|---|
| Fork delta 行数 | `wc -l aiseo_cli.py plugins/aiseo-guard/__init__.py` 当前合计 | 净减 ≥ 350 行 | 同命令对比 |
| 上游 rebase 摩擦 | 下次 rebase 上游 Hermes 时手工 resolve conflict 数 | ≤ baseline 的 60% | 记录在 ledger |
| Drift gate / parity / deadline CI 红率 | 上线后第 1 个月红次数 | 1-3 次/月(>10 次说明 gate 设计错) | CI dashboard |
| 6 周超时项升格率 | 进入 ledger 的"推上游"项 | 升格永久资产比例 ≥ 70%(否则"推上游"是空话) | ledger 季度汇总 |

## 下一步行动(立即执行)

1. **今天**: 拷贝 P0-A Prerequisite 第 1 条,在 `tests/aiseo/test_input_gate_*.py`
   写边界回归测试,跑 pytest 确认是 RED 还是已被现有链路拦截
   (决定 P0-A 是修 bug 还是降级为 regression guard + 重构)
2. **本周**: 创建 `.plans/upstream-push-ledger.md` 空文件占位(P2-C 前置),
   把本方案已识别的"推上游"项(profile-sync / outputgate-prefix / pre_user_message 确认 /
   external content wrapping / additive list migration / DataForSEO verify)迁入初始行
3. **本周**: 优先级总表迁入 GitHub Project/Issues,每个 P-X 一个 issue,
   Owner 字段按 Metadata fallback 规则指派

## 决策历程

完整迭代记录(team 评议、反转、修正过程)见 git log + PR/会话历史。本节略。

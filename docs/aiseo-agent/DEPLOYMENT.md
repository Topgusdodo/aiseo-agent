# AISEO Agent 服务器部署 / 升级 SOP

服务器侧从 git push 到新插件 / 新 cron 生效的标准运维流程。

## 适用场景

- 服务器升级到 main / feat 分支新提交
- 接入新插件（如 `dataforseo`），需要服务器 env 配置才能让工具可调用
- 调整 cron 任务、seed profile 资产（skills / memories / references）

服务器默认部署路径：`/usr/local/lib/hermes-agent/`，venv 在 `./.venv/`，wrapper 入口 `./.venv/bin/aiseo`。

## 标准升级流程

```bash
# 1. 进入部署目录
cd /usr/local/lib/hermes-agent/

# 2. 确认工作区干净（不能有未提交本地改动）
git status

# 3. 拉取远端
git fetch
git checkout <branch>          # 例：feat/aiseo-phase2 或 main
git pull

# 4. 同步 seed → 用户 profile
#    - 文件级 missing-only：MEMORY.md / .env / auth.json 等用户状态永不覆盖
#    - 目录级 missing-only：已存在的 skill 目录不会被动到
#    - 列表追加：toolsets / agent.disabled_toolsets / plugins.enabled
#      三个字段按 seed 差量 append，自动追上新 toolset / 新插件启用
#    - sync 完会自动打印 ⚠️ 警告块：列出启用插件 requires_env 但缺失的变量
./.venv/bin/aiseo sync

# 5. 如果升级带来了 SOUL.md 行为指令更新（不在自动追加范围内），显式刷新：
./.venv/bin/aiseo sync --refresh-soul    # 备份当前 → 从 seed 复制（交互确认）
./.venv/bin/aiseo sync --refresh-soul -y # 同上但跳过确认

# 6. 配置上一步警告里报缺的 env（务必单引号，避免 $ / ! 被 shell 展开）
#    aiseo profile 的 env 文件路径是 ~/.hermes/profiles/aiseo/.env
#    （不是 ~/.hermes/.env —— 那是 default profile 的，aiseo 不读）
echo 'DATAFORSEO_BASE64=<paste-base64-here>' >> ~/.hermes/profiles/aiseo/.env

# 7. 重启 gateway 让新 env / 新插件 / 新追加的 toolset 生效
./.venv/bin/aiseo gateway restart

# 8. 验证
grep DATAFORSEO_BASE64 ~/.hermes/profiles/aiseo/.env       # env 已写入
grep -A4 "^toolsets:" ~/.hermes/profiles/aiseo/config.yaml # 新 toolset 应有 # auto-added by ... 注释
./.venv/bin/aiseo                                          # 进 chat，让 LLM 列工具，确认新工具可见
```

`aiseo sync` 永不覆盖的文件清单：`MEMORY.md`、`config.yaml`（**仅例外**：列表
追加，见下）、`.env`、`auth.json`、`auth.lock`。新加的 seed 文件 / 新 skill 目
录会按 missing-only 拷贝过去；已存在的 skill 目录不会被动到。

**列表追加例外**：从 v0.2 起，`aiseo sync` 会读 seed 的 `config.yaml`，对三个
列表字段做差量 append：
- `toolsets:`（顶层）
- `agent.disabled_toolsets:`
- `plugins.enabled:`

只加 seed 有 profile 没的，**永不删、永不替换标量**（model / api_key / max_turns
全保留）。每次写入前自动 rolling backup 到 `config.yaml.bak.<YYYYMMDD_HHMMSS>`
（保留最近 5 份）。追加的项末尾带 `# auto-added by aiseo sync <date>` 注释，
方便审计。

如果你给 seed 加了**新字段类型**（不是上述三个），现有 profile 不会自动跟上——
要么扩 `SEED_TRACKED_LIST_FIELDS` 白名单 + 跑 sync，要么手动改 profile 的
config.yaml。SOUL.md 走 `--refresh-soul` 显式刷新；skills/ 内部文件目前没有
传播机制（按目录粒度 missing-only，要更新需手动改用户 profile 的目录）。

## 已知插件凭证清单

| Plugin       | 必需 env             | 可选 env                | 来源                                                                            |
| ------------ | -------------------- | ----------------------- | ------------------------------------------------------------------------------- |
| `dataforseo` | `DATAFORSEO_BASE64`  | `DATAFORSEO_SANDBOX=1`  | https://app.dataforseo.com/api-access（API password ≠ dashboard 登录密码） |

`DATAFORSEO_BASE64` 是 **预先算好的** `base64(login:password)` 字符串。本地生成：

```bash
printf '%s' 'your-login:your-api-password' | base64
```

`DATAFORSEO_SANDBOX=1` 切到免费 dummy-data 沙盒主机，用于联调 / 不消耗配额。生产留空。

写入服务器：

```bash
echo 'DATAFORSEO_BASE64=bG9naW46cGFzc3dvcmQ=' >> ~/.hermes/profiles/aiseo/.env
# 沙盒（可选）：
echo 'DATAFORSEO_SANDBOX=1' >> ~/.hermes/profiles/aiseo/.env
```

## 常见踩坑

1. **env 写错位置** —— 写到 `~/.hermes/.env` 是 default profile 的文件，`aiseo` wrapper 切了独立 `HERMES_HOME`，根本不会读它。aiseo profile 的 env 文件路径只有一个：`~/.hermes/profiles/aiseo/.env`。
2. **凭证用错** —— DataForSEO 的 dashboard 登录密码不是 API password。必须去 https://app.dataforseo.com/api-access 拿专用 API password 再 base64。
3. **echo 用双引号** —— `echo "DATAFORSEO_BASE64=..."` 里如果 base64 字符串含 `$` / `!` / 反引号，会被 shell 提前展开吃字符，写进文件的值就是错的。**一律用单引号** `'...'`。
4. **忘记 restart gateway** —— gateway 在启动时加载 env，热写文件不会自动生效。改完 env 必须 `aiseo gateway restart`。
5. **使用了废弃变量名** —— 当前只认 `DATAFORSEO_BASE64`，不要写成 login/password 拆分变量。
6. **git 工作区脏** —— 服务器上若有人手改过 `.venv/` 外的文件，`git pull` 会拒绝或冲突。先 `git status` 看清楚，必要时把改动 stash 走。

## 回滚

发现升级后出问题，回到上一个已知好版本：

```bash
cd /usr/local/lib/hermes-agent/
git log --oneline -10                       # 找到上一个稳定 commit
git checkout <prev-commit-sha>
./.venv/bin/aiseo gateway restart
```

`aiseo sync` 不需要重跑 —— 用户 profile 状态本身没被覆盖过，回滚代码即可。如果回滚后某个新加的 env 不再需要，可以从 `~/.hermes/profiles/aiseo/.env` 里删掉对应行（删之前先备份）。

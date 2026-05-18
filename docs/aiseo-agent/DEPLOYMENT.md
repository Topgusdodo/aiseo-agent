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

# 4. 同步 seed → 用户 profile（missing-only，幂等，绝不覆盖现有 skill / MEMORY.md / config.yaml / .env）
./.venv/bin/aiseo sync

# 5. 检查本次升级是否引入新插件、是否需要 env
#    每个插件的 plugin.yaml 都声明 requires_env / 可选 env：
ls plugins/
cat plugins/<name>/plugin.yaml

# 6. 配置必需 env（务必单引号，避免 $ / ! 被 shell 展开）
#    aiseo profile 的 env 文件路径是 ~/.hermes/profiles/aiseo/.env
#    （不是 ~/.hermes/.env —— 那是 default profile 的，aiseo 不读）
echo 'DATAFORSEO_BASE64=<paste-base64-here>' >> ~/.hermes/profiles/aiseo/.env

# 7. 重启 gateway 让新 env / 新插件生效
./.venv/bin/aiseo gateway restart

# 8. 验证
grep DATAFORSEO_BASE64 ~/.hermes/profiles/aiseo/.env       # env 已写入
./.venv/bin/aiseo                                          # 进 chat，让 LLM 列工具，确认新工具可见
```

`aiseo sync` 永不覆盖的文件清单：`MEMORY.md`、`config.yaml`、`.env`、`auth.json`、`auth.lock`。新加的 seed 文件 / 新 skill 目录会按 missing-only 拷贝过去；已存在的 skill 目录不会被动到。

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

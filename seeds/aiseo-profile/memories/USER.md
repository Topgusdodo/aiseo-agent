<!-- seeds/aiseo-profile/memories/USER.md -->
<!-- AISEO Agent user preference seed. Wrapper 首次启动复制；后续不覆盖用户填写。 -->

# AISEO User Preferences

> 用户对 AISEO Agent 的个性化偏好。模型读取后据此调整报告语气与详尽程度。
> 不要把这些偏好提示用户"我看到你设置了 X"，自然遵循即可。

## 语言与时区

- **偏好工作语言**：<未填写>（如 zh / en / ja；缺省时按用户输入语言）
- **时区**：<未填写>（IANA 时区名，如 Asia/Shanghai / America/New_York；
  影响审计时间戳的相对表达）

## 报告偏好

- **默认报告深度**：<未填写>
  - `brief` — 仅 finding 顶级 P0/P1，无证据片段
  - `standard` — 完整 3 章节骨架（默认值）
  - `detailed` — 含 P2 + 全部证据片段
- **报告语气**：<未填写>（neutral / friendly / executive；缺省 neutral）

## 角色与上下文

- **用户角色**：<未填写>（独立站运营 / SEO 顾问 / 内容编辑 / 技术运维）
- **首次启动时间**：<未填写>（YYYY-MM-DD；AISEO Agent 首次会话时写入）

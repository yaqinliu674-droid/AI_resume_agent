# Streamlit Community Cloud 测试部署

本文件用于将私有 GitHub 仓库部署成测试者无需安装软件、无需登录即可打开的公开测试网页。

## 1. 提交前安全检查

仓库根目录应至少包含：

- `app.py`
- `career_core.py`
- `requirements.txt`
- `.streamlit/config.toml`
- `.gitignore`
- `README.md`

不得提交：

- `.env`
- `.streamlit/secrets.toml`
- `.venv/` 或 `.venv_codex/`
- 本地备份、缓存和完整简历样本

建议在推送前执行：

```powershell
git status --short
git check-ignore -v AI_resume_agent/.env
git grep -n -I -E "sk-[A-Za-z0-9]|DASHSCOPE_API_KEY\\s*=\\s*['\"][^'\"]+" -- AI_resume_agent
```

## 2. GitHub 仓库

1. 在 GitHub 新建私有仓库，例如 `ai-resume-agent-mvp`。
2. 默认分支使用 `main`。
3. 将本项目文件作为仓库根目录内容推送。
4. 确认 GitHub 网页中看不到 `.env` 和 `.streamlit/secrets.toml`。

如果 Streamlit 无法列出私有仓库，需要允许 Streamlit 访问私有仓库。部署者必须对该仓库有管理员权限。

## 3. 创建 Streamlit 应用

1. 打开 `https://share.streamlit.io/` 并使用 GitHub 登录。
2. 切换到与 GitHub 仓库所有者一致的 workspace。
3. 点击右上角 **Create app**。
4. 选择 **Yup, I have an app**。
5. 填写：
   - Repository：刚创建的私有仓库
   - Branch：`main`
   - Main file path：`app.py`
6. 可选：填写 6 至 63 个字符的 App URL 子域名。
7. 点击 **Advanced settings**：
   - Python version：`3.12`
   - Secrets：粘贴下一节的 TOML

## 4. Secrets 字段

只在 Streamlit Secrets 中填写真实值：

```toml
DASHSCOPE_API_KEY = "你的百炼 API Key"
DASHSCOPE_WORKSPACE_ID = "你的百炼业务空间 ID"
DASHSCOPE_MODEL = "qwen3.7-plus"
```

不要添加 `AI_RESUME_OFFLINE = "1"`，否则线上应用会始终使用保守离线模式。

## 5. 设置测试者无需登录

私有仓库部署的应用默认可能是私有应用。部署完成后：

1. 在 Streamlit workspace 中点击应用右侧的三点菜单。
2. 点击 **Settings**。
3. 打开 **Sharing**。
4. 在 **Who can view this app** 选择 **This app is public and searchable**。
5. 保存。

设置后仓库仍保持私有，但应用链接可以公开访问。

## 6. 上线后必须验证

只有完成以下检查后才发送链接：

1. 在未登录 Streamlit 的无痕窗口打开真实 `.streamlit.app` 链接。
2. 确认首页只有三个入口。
3. 使用手机宽度（建议 390×844）完成一次“目标岗位”主流程。
4. 确认输入 JD 和经历后先出现初步诊断。
5. 确认最多 3 题，并可以全部跳过。
6. 确认结果包含“投递判断”“可复制简历结果”和真实性复核；当前版本不再提供 Word 下载按钮。
7. 确认微信内置浏览器能打开首页、输入文字并点击全宽按钮。
8. 在应用日志中确认没有完整简历正文和 API Key。

## 7. 常见错误

- **仓库不可见**：重新授权 Streamlit 访问私有 GitHub 仓库，并确认自己有仓库管理员权限。
- **ModuleNotFoundError**：检查 `requirements.txt` 是否位于 `app.py` 同一目录。
- **AI 服务配置无效**：检查 Secrets 的字段名和引号，不要把 `.env` 整段作为单个值。
- **额度用尽**：应用会保留输入并生成保守版本；补充额度后可重试。
- **链接要求登录**：在 Settings → Sharing 中把应用改为公开。
- **部署后仍是旧代码**：确认推送到了 Streamlit 配置的分支，并在应用菜单中 Reboot。

## 8. 当前部署状态记录

- GitHub 仓库：尚未确认
- Streamlit 应用：尚未确认
- 公开测试链接：只有实际部署和打开验证后填写
- 手机主流程：只有实际运行后填写

# AI 求职助手 MVP

一个面向真实求职者测试的 Streamlit 应用。首页只有三个入口：

- 我有目标岗位，准备投递
- 我还没确定投什么岗位
- 我想先整理一份基础简历

## 已实现的核心流程

### 岗位定制

上传 PDF、Word、TXT、Markdown 简历或粘贴真实经历，输入真实 JD 后依次完成：

1. JD 要求拆解
2. 真实经历证据提取
3. 初步诊断
4. 最多 3 个关键追问（可全部跳过）
5. 基于已确认事实的 STAR 定向重构
6. 独立真实性复核
7. 定制简历与面试追问

模型不可用、额度用尽或返回异常时，系统保留输入并生成不增加事实的保守版本。

### 方向探索

只判断是否继续原方向、岗位/城市优先级和明确排除内容，输出：

- 直接可投
- 相邻方向
- 探索方向
- 多城市第一梯队参考
- 经历证据不足时的 3 至 7 天微型项目

城市建议不是实时招聘数据，也不代表录取概率。

### 基础简历

允许填写课程、个人项目、实习、兼职、社团、比赛、作品、技能和证书。完成后可以将已有信息直接带入岗位定制或方向探索，不需要重复填写。

## 真实性边界

- 不根据模型猜测补写职责、数据、公司、客户、商业结果或证书。
- AI 重构条目必须带有原始事实片段；未被原始输入或用户补充支持的数字会被拦截。
- “主导、独立负责”等责任升级只有原始事实支持时才能保留。
- 课程、个人和练习项目不会被改写成企业或客户项目。
- 日志不记录 API Key 或完整简历正文。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

在 `.env` 中填写：

```text
DASHSCOPE_API_KEY=
DASHSCOPE_WORKSPACE_ID=
DASHSCOPE_MODEL=qwen3.7-plus
```

不要提交 `.env` 或 `.streamlit/secrets.toml`。

## 测试

```powershell
$env:AI_RESUME_OFFLINE="1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试覆盖八条业务路径、文件解析、真实性拦截和 Streamlit 页面状态机。

## 部署

请查看 [README_TEST_DEPLOY.md](README_TEST_DEPLOY.md)。部署入口文件为 `app.py`，推荐 Python 3.12。


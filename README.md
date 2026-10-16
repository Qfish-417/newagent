# newagent · 每日 AI 新闻助手

KUAFUAI Agent 开发实习题，选项 A。当前为 **V0.1 本地单用户原型**。

模型通过 function calling 自主选择工具、追加检索并决定停止，页面可查看偏好、历史任务及工具调用记录。当前支持手动生成；定时任务、邮件推送、多用户和结构化来源校验尚未实现，详见 [实施方案](docs/PLAN.md)。

## 5 分钟启动（Python 3.11+）

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env：填写 OPENAI_API_KEY、SEARCH_API_KEY（Tavily），按需调整模型及 BASE_URL
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 ，保存偏好后点击立即生成。接口文档：http://127.0.0.1:8000/docs 。首次启动自动执行 `migrations/001_initial.sql`。所有数据保存在 `data/`，不提交 Git。

未配置密钥时服务和页面仍可启动，生成任务会明确失败，不会伪造新闻。模型与搜索服务可能产生费用。

## 工具与边界

- `list_dir` / `read_file` / `search_content` / `write_file`：限定当前任务工作目录。
- `bash`：受限命令解释器，仅支持 `pwd`、`ls`、`cat FILE`、`wc FILE`，不执行通用 shell。
- `search_news`：Tavily 新闻搜索，时间范围过去一天。

默认最大 12 轮模型请求；错误反馈给模型，超限后任务失败。网页内容作为不可信资料处理。首版无账户鉴权，仅用于本机演示；勿直接开放公网。工具记录可能包含偏好和检索内容。

## 验证

```powershell
python -m pytest -q
```

自动测试不调用付费模型；真实新闻生成需要有效的模型及搜索服务密钥。

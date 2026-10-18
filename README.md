# newagent · 每日 AI 新闻助手

KUAFUAI Agent 开发实习题，选项 A。当前为 **V0.2 本地单用户原型**。

模型通过 function calling 自主选择工具、追加检索并决定停止，页面可查看偏好、历史任务及工具调用记录。当前支持手动生成；定时任务、邮件推送、多用户和结构化来源校验尚未实现，详见 [实施方案](docs/PLAN.md)。

## 5 分钟启动（Python 3.11+）

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env：沿用本地 DEEPSEEK_API_KEY，填写 SEARCH_API_KEY（Tavily）
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

## DeepSeek 配置

默认使用 `deepseek-chat` 和 `https://api.deepseek.com`，直接读取本地环境变量 `DEEPSEEK_API_KEY`，无需复制密钥。
可通过 `DEEPSEEK_MODEL`、`DEEPSEEK_BASE_URL` 覆盖。兼容 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL`，DeepSeek 变量优先。
`.env` 不提交 Git。新闻检索仍需单独配置 `SEARCH_API_KEY`（Tavily）。

## V0.2 本地 RAG 降级

页面“本地 RAG 知识库”可以导入你自己的文本、标题、来源和可选发布日期。
模型可调用 `search_knowledge(query)` 检索相关片段，在新闻来源失败或背景不足时补充资料。
检索采用中文双字与英文词项加权匹配，不依赖额外 embedding API；同义词召回能力有限。
资料分块保存在 SQLite（`data/news.db`），无需额外服务。

使用知识库或检索过程出现降级时，任务标记 `partial`。程序附加知识库引用及日期；只有知识库命中时明确提示“非今日新闻”。两种来源均无证据则失败。
当前只检查检索是否有命中，尚未完整验证模型每条陈述与引用的一致性，不能保证新闻真实性。

资料只供本地单用户使用。被检索命中的片段会发给所配置的 DeepSeek 服务用于生成内容，请只导入适合发送给该服务的资料。
新闻搜索仍可选配 Tavily；没有搜索密钥时，Agent 可以尝试知识库降级，不会自动创建虚假新闻或示例资料。

## 新闻搜索自动归档（2026-10-18）
- search_news 成功返回的标题、正文摘要、来源 URL、服务提供的发布时间自动入 RAG；保存首次和最近检索时间。
- URL 去除 fragment、utm_*、fbclid、gclid，唯一约束及事务避免重复归档；重复命中更新最近检索时间，保留原始资料。
- 不保存模型生成的摘要作为新闻证据；缺少正文/有效来源的结果跳过，发布时间缺失保留未知。
- 知识库页面区分手动导入和搜索归档；RAG 返回 archived_news 类型及检索日期，始终作为历史背景使用。
- 归档失败不会抹掉可用搜索结果；跳过或失败会写入降级说明。仍受 200 文档上限约束，达到上限不自动删除旧资料。
- 8 项自动测试通过，包含重复链接、日期保留、历史资料召回、无效资料跳过。未进行真实搜索 API 调用。

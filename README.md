# newagent · 每日 AI 新闻助手

KUAFUAI Agent 开发实习题，选项 A。当前支持本地多浏览器身份与每日站内定时推送。

模型通过 function calling 自主选择工具、追加检索并决定停止，页面可查看偏好、历史任务及工具调用记录。当前支持手动生成和每日站内定时推送；邮件、跨设备账户和结构化来源校验尚未实现，详见 [实施方案](docs/PLAN.md)。

## 5 分钟启动（Python 3.11+）

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env：沿用本地 DEEPSEEK_API_KEY，可选填写 SEARCH_API_KEY（Tavily 备用搜索）
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
`.env` 不提交 Git。新闻检索默认可直接使用现有 DeepSeek 密钥；`SEARCH_API_KEY` 仅用于可选 Tavily 搜索。

## V0.2 本地 RAG 降级

知识库仅通过本机后台命令管理，不在用户页面展示或导入。
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
- 后台记录区分手动导入和搜索归档；RAG 返回 archived_news 类型及检索日期，始终作为历史背景使用。
- 归档失败不会抹掉可用搜索结果；跳过或失败会写入降级说明。仍受 200 文档上限约束，达到上限不自动删除旧资料。
- 8 项自动测试通过，包含重复链接、日期保留、历史资料召回、无效资料跳过。未进行真实搜索 API 调用。

## 官方新闻示例资料
运行 python -m scripts.seed_knowledge 导入 examples/knowledge_seed.json 中的三篇官方公告摘要（DeepSeek V3.2、Claude 4、MCP）。重复运行跳过已存在的同标题同来源资料。保留原始发布日期，仅用于历史背景检索，并非今日新闻。

## 后台知识库管理

用户页面不提供知识库列表、正文浏览及导入入口，原 `/api/knowledge` 路由已移除。
任务详情只显示工具名称，原始检索资料仍保留在本地数据库用于后台排查。

```powershell
python -m scripts.manage_knowledge list
python -m scripts.manage_knowledge import examples/knowledge_seed.json
python -m scripts.manage_knowledge show 1
python -m scripts.manage_knowledge search Agent
```

导入文件为 JSON 数组，字段参考 examples/knowledge_seed.json。已有知识库与自动搜索归档继续工作，简报保留来源引用。

## 扩充工具与搜索切换

框架为 FastAPI + OpenAI Python SDK，Agent Loop 为手写 function calling，不依赖 LangChain/LangGraph。
扩充工具时，在 app/tools.py 的 SCHEMAS 添加名称、参数和说明，并在 Tools.execute 实现对应处理；循环自动把工具暴露给模型。
`search_deepseek(query)` 已注册，使用本机 DEEPSEEK_API_KEY 请求官方 Search API。
未配置 Tavily 时不向模型提供 search_news；已配置的搜索服务调用异常后在当前任务停用，错误与切换建议回传模型，由模型重新选择其他搜索或知识库工具。空结果允许调整查询，不直接停用。
两个搜索工具的结果都自动归档 RAG。搜索服务提供的日期可能是索引时间，模型仍需核实新闻日期。

## 用户隔离与每日调度

同一个 SQLite 数据库存储多个用户：users、user_subscriptions、run_owners 以 user_id 关联。用户由长期 HttpOnly Cookie 标识；同一浏览器保留身份，不同浏览器隔离订阅与简报。没有账号密码和跨设备登录，清除 Cookie 会失去原身份的入口。升级后第一个本地访问者一次性继承旧单用户资料。

页面设置每日 HH:MM、IANA 时区（默认 Asia/Shanghai）并启用定时。后端用 UTC 存储下一执行时刻，启动读取数据库与当前时间计算等待时间；修改后即时唤醒重算。保存时间已过则安排明天；保存时间恰好等于当前分钟亦按下一天计算。关闭定时取消未来计划，已执行中的任务仍完成。

到时自动检索生成，站内显示未读，点击该简报标记已读。页面每 3 秒检查，未开页面时结果仍保留，下次打开可查看；不发送桌面系统通知。时间表示开始生成的时间，完成后才投递，生成耗时会使收到时间稍晚。

服务必须运行才能按时执行。停机错过的计划启动后最多补执行一次，然后安排下一天。数据库事务与 (user_id, scheduled_for) 唯一约束防止重复调度；执行中重启的任务标记失败，不盲目重发。每日时间修改为新时刻允许当天再次调度。

当前部署使用一个 Uvicorn worker；尚无跨进程任务恢复/租约，不以多 worker 方式启动。RAG 为后台维护的共享公开新闻资料，不将用户订阅作为共享知识入库。

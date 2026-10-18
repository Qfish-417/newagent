# newagent · 每日 AI 新闻助手

KUAFUAI Agent 开发实习题，选项 A。Python + FastAPI + SQLite，使用 OpenAI Python SDK 实现手写 Function Calling 循环。LLM 自主选择工具、查询内容、调用次数及结束时机。

支持注册登录、按用户保存订阅与自定义提示词、每日站内定时推送、未读提醒、新闻卡片详情、后台 RAG 管理与搜索自动归档。方案与实施记录见 [docs/PLAN.md](docs/PLAN.md)。

## Windows 一键启动

环境：Windows 10/11，Windows PowerShell 5.1 或 PowerShell 7，**64 位 Python 3.11+**（本项目在 Python 3.13 验证），首次安装依赖需要联网。项目路径支持空格与中文。

**只需要 DeepSeek API Key**，模型对话和官方搜索共用本机环境变量 `DEEPSEEK_API_KEY`。不需要 Tavily、Redis、MySQL 或 Docker。

已配置该环境变量的用户，在仓库目录执行：

```powershell
.\start.cmd
```

也可双击 `start.cmd`。首次没有密钥会自动打开交互配置向导。脚本创建 `.venv`、安装依赖、生成本地 `.env`（不覆盖已有文件）、校验密钥并自动建表，随后启动单 worker 服务。
打开 http://127.0.0.1:8000 ，注册账号，设置偏好、自定义提示词和每日时间。Ctrl+C 停止；每日调度需要服务保持运行。

如果尚未配置密钥，可在 Windows“环境变量”中添加用户变量 `DEEPSEEK_API_KEY`，值填自己的密钥，然后重新打开终端。脚本也会尝试读取已持久化的用户/系统变量。**不要将密钥填写到示例文件或提交 Git。**

可选启动参数：

```powershell
.\start.cmd -Port 8001
.\start.cmd -CheckOnly
# 已安装依赖时，仅检查配置和建表，不启动服务：
.\start.cmd -SkipInstall -CheckOnly
```

首次拉取或修改 requirements.txt 后脚本安装依赖；其余启动复用环境。CheckOnly 会创建环境/本地配置并执行 migration，但不调用付费模型或搜索。

## 交互配置并一键启动

双击 `configure.cmd`，或执行：

```powershell
.\configure.cmd
# 等价：
.\start.cmd -Configure
```

同一个脚本先安装依赖，再进入配置向导：

1. 提示 **只需要 DeepSeek API Key**，输入时隐藏；已有环境变量时可回车沿用。
2. 询问是否填写可选项；选 N 直接使用默认值，选 Y 可设置模型、接口地址、数据目录、轮数及 Tavily Key。
3. 保存为本地 UTF-8 `.env`，由应用加载为配置，自动建表并启动服务。

不会修改 Windows 系统环境变量，也不会显示密钥。若已有同名系统环境变量，其优先级高于 `.env`，向导会明确提示；更新系统密钥需要在系统环境变量设置中处理。
`start.cmd` 用于之后直接启动，`configure.cmd` 可随时重新配置并启动。可选值回车保留现有设置。

## 配置格式

推荐通过系统环境变量保存密钥。也支持仓库根目录的本地 `.env`：复制 `.env.example` 后按需填写。文件采用 **UTF-8，逐行 NAME=value**，不写 `export`、`$env:`、JSON 或中文引号。操作系统环境变量优先于 `.env`。

| 变量 | 必填 | 默认/用途 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 是 | 本机密钥，模型与 DeepSeek 官方搜索共用 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-chat`，可按账号可用模型调整 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com`，模型接口地址 |
| `SEARCH_API_KEY` | 否 | Tavily 密钥；留空直接使用 DeepSeek 搜索 |
| `DATA_DIR` | 否 | `data`，数据库、任务文件及本地备份目录 |
| `MAX_ROUNDS` | 否 | `12`，单任务模型轮数上限 |

DeepSeek 搜索请求固定发送至官方 `https://api.deepseek.com/v1/tools/search`；修改模型 BASE_URL 不会修改搜索地址。兼容 OPENAI_API_KEY/OPENAI_BASE_URL/MODEL，但默认推荐 DeepSeek 变量。
模型与搜索可能计费，是否可用取决于密钥权限、余额及网络。

## 其他系统手动启动

Linux/macOS 使用 Python 3.11+，无需 PowerShell：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 通过系统环境或本地 .env 配置 DEEPSEEK_API_KEY
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

requirements.txt 是跨环境依赖范围；requirements.lock.txt 记录 Windows/Python 3.13 的验证版本，不保证适用于所有系统。

## 数据库与账号

SQLite 自动创建，SQL 在 migrations/001_initial.sql 至 005_accounts.sql；启动执行幂等 migration，保留已有数据。无需手动建库。
同一数据库通过 user_id 隔离用户订阅、提示词、任务和简报，无需每用户建库。

用户名密码注册登录，随机盐 scrypt 密码哈希、30天服务端会话（数据库只存令牌摘要），Cookie 使用 HttpOnly、SameSite=Strict，HTTPS 下启用 Secure。连续8次登录失败限制该用户名15分钟。尚无邮箱验证、找回密码或双因素认证。
注册迁移当前访客资料；登录已有账号合并访客历史并优先保留账号设置。提示词每次手动/定时生成读取，不进入共享 RAG。

## 每日调度与阅读

按用户设置的 HH:MM 和 IANA 时区每日执行（默认 Asia/Shanghai），UTC 存储下次执行时刻。修改后立即重算，页面显示下次时间和差值。已过当天时刻则排到明天。
到点开始搜索生成，完成后站内标记未读；点击简报标记已读，页面3秒轮询。没有邮件或系统桌面通知。
停机错过的计划启动后补执行一次，再恢复每日计划；执行中重启的任务标记失败。事务和唯一约束避免重复认领。只部署一个 worker。

## 工具与降级

- list_dir、read_file、search_content、write_file：限任务工作目录。
- bash：目前是受限命令解释器，仅支持 pwd/ls/cat/wc，**尚未实现通用 shell 执行**。
- search_news：可选 Tavily 新闻搜索。
- search_deepseek：DeepSeek 官方联网搜索，复用现有密钥。
- search_knowledge：本地分块词项检索（中文双字/英文词项加权），不依赖 embedding 服务。

工具定义与执行位于 app/tools.py。Tavily 未配置不向模型提供该工具；搜索异常本任务停用该服务，由模型选择剩余工具。
只有两个搜索服务都不可用或无结果才允许 RAG；任一搜索取得结果就不进行知识库降级。仅实际使用知识库时显示补充提示和历史资料引用。
搜索证据自动入库，按规范化 URL 去重，保存来源与日期；搜索日期可能是索引日期，完整新闻时效和逐句引用校验尚未完成。

## 后台知识库管理

用户页面及公共 API 不提供知识库浏览和导入。后台命令：

```powershell
.venv\Scripts\python -m scripts.manage_knowledge list
.venv\Scripts\python -m scripts.manage_knowledge import examples/knowledge_seed.json
.venv\Scripts\python -m scripts.manage_knowledge show 1
.venv\Scripts\python -m scripts.manage_knowledge search Agent
```

示例文件为三篇带官方来源和发布日期的历史摘要，不会启动时自动导入。共享 RAG 仅存后台资料与公开新闻，检索命中片段会发送给 DeepSeek 用于生成。

## 验证与提交

```powershell
.venv\Scripts\python -m pytest -q
```

自动测试不调用付费服务。覆盖工具隔离、模型工具循环、双搜索/RAG门槛、新闻归档、账号隔离与迁移、定时与未读。
Git 保留各阶段提交历史。`.env`、`.env.*`（除示例）、data/、数据库、日志和虚拟环境均被忽略。提交代码与 SQL，不提交 API Key、账号数据、Cookie、任务资料或备份。

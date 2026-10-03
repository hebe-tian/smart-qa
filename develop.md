# 开发文档

> 本文档包含 smart-qa 项目的技术实现细节：技术能力、项目架构、通用 AI 接入指南、快速开始、版本变更历史与日志说明。项目介绍与功能列表见 [README.md](README.md)，环境搭建与生产部署见 [deploy.md](deploy.md)。

## 一、技术能力

- **异步任务系统**：后台线程执行 AI 生成任务，线程安全的 TaskStore 存储任务状态，前端轮询进度
- **Flask 应用上下文穿透**：后台线程自动注入 `app.app_context()`，避免 `Working outside of application context`
- **JSON 响应鲁棒解析**：支持 markdown 围栏提取、正则匹配、`json_repair` 三级回退，容错 AI 返回非标准 JSON
- **API Key 加密**：Fernet 对称加密存储 AI API Key，密钥不落库明文
- **SQLite 并发优化**：启用 WAL 模式 + `busy_timeout=5000ms`，支持并发读写
- **RAG 检索增强**：numpy 向量余弦相似度检索 + scikit-learn 欧氏距离排序，历史用例注入 AI prompt 提升 few-shot 效果
- **全局异常处理**：Flask errorhandler 捕获 500/未处理异常，完整 traceback 写入 `error.log`，前端返回 JSON 错误响应
- **结构化日志**：多 Logger 分模块记录（app/api/ai/generation/auth/middleware/call_log/analytics/error），`LOG_LEVEL` 环境变量控制级别，日志文件自动轮转

## 二、项目架构

### 2.1 目录结构

```
smart-qa/
├── backend/
│   ├── app/
│   │   ├── __init__.py              # Flask 应用工厂 + 路由注册 + 建表 + 默认管理员
│   │   ├── config.py                # 应用配置（密钥/数据库/日志/超时）
│   │   ├── extensions.py            # SQLAlchemy 实例
│   │   ├── core/
│   │   │   ├── decorators.py        # @token_required / @track_event 装饰器
│   │   │   ├── security.py          # JWT 生成/验证 + API Key 加密/解密
│   │   │   └── middleware.py        # HTTP 请求/响应日志中间件
│   │   │   └── guest_guard.py       # 游客只读守卫（写操作拦截）
│   │   ├── models/                  # 数据模型 (9 张表)
│   │   │   ├── user.py              # 用户表
│   │   │   ├── requirement.py       # 需求表
│   │   │   ├── qa_session.py        # 问答消息表
│   │   │   ├── module.py            # 功能模块表
│   │   │   ├── test_case.py        # 测试用例表
│   │   │   ├── ai_config.py        # AI 配置表
│   │   │   ├── ai_call_log.py      # AI 调用记录表
│   │   │   ├── regeneration.py     # 重新生成记录表
│   │   │   ├── analytics_event.py   # 用户行为事件表
│   │   │   └── embedding.py         # 向量嵌入表（RAG 知识库）
│   │   ├── api/                     # API 蓝图 (13 个 Blueprint)
│   │   │   ├── auth.py             # /api/auth — 登录/注册/游客/me
│   │   │   ├── requirements.py     # /api/requirements — 需求 CRUD
│   │   │   ├── qa.py               # /api/qa — 需求分析/问答/历史
│   │   │   ├── modules.py          # /api/modules — 模块 CRUD
│   │   │   ├── cases.py            # /api/cases — 用例 CRUD
│   │   │   ├── generate.py          # /api/generate — 异步生成模块/用例
│   │   │   ├── regenerate.py       # /api/regenerate — 异步重新生成
│   │   │   ├── tasks.py            # /api/tasks — 任务状态轮询
│   │   │   ├── ai_config.py        # /api/ai-config — AI 配置 CRUD + 测试
│   │   │   ├── call_logs.py        # /api/call-logs — 调用记录列表/详情/摘要
│   │   │   ├── analytics.py        # /api/analytics — 事件追踪/摘要/事件流
│   │   │   ├── export.py           # /api/export — 用例导出 (HTML/MD/XMind)
│   │   │   └── rag.py              # /api/rag — 知识库状态/查询/重建
│   │   └── services/                # 服务层
│   │       ├── ai_service.py       # AI 调用封装（自动记录调用日志）
│   │       ├── prompt_service.py   # Prompt 模板（分析/QA/模块/用例/重新生成）
│   │       ├── case_service.py     # 生成编排（分析→QA→模块→用例→重新生成）
│   │       ├── task_store.py       # 线程安全的异步任务存储
│   │       ├── call_log_service.py # AI 调用记录服务
│   │       ├── analytics_service.py # 埋点统计服务
│   │       ├── export_service.py   # 用例导出服务 (HTML/MD/XMind)
│   │       ├── logging_service.py  # 多 Logger 日志服务
│   │       ├── embedding_service.py # Embedding 向量服务（分块/向量检索）
│   │       └── rag_service.py      # RAG 检索增强生成服务
│   ├── requirements.txt
│   ├── wsgi.py                      # WSGI 入口（PythonAnywhere）
│   ├── run_dev.py                   # 本地开发服务器
│   ├── init_db.py                   # 数据库初始化脚本
│   └── build_kb.py                  # 知识库索引构建脚本
├── frontend/
│   ├── index.html                   # 登录页
│   ├── dashboard.html               # 需求列表页
│   ├── requirement.html             # 需求详情页（核心）
│   ├── ai-config.html               # AI 配置页
│   ├── call-logs.html               # 调用记录页
│   ├── analytics.html               # 数据概览页
│   ├── knowledge-base.html          # 知识库管理页
│   ├── css/                         # 样式文件
│   └── js/
│       ├── api.js                   # API 请求封装
│       ├── auth.js                  # 认证逻辑
│       ├── router.js                # 前端路由
│       ├── config.js                # 前端配置
│       ├── analytics.js             # 前端埋点
│       ├── components/              # 通用组件
│       │   ├── navbar.js           # 顶栏
│       │   ├── sidebar.js          # 侧边栏
│       │   ├── modal.js            # 模态框
│       │   ├── toast.js             # 消息提示
│       │   ├── tree.js             # 模块-用例树
│       │   └── progress.js         # 进度条
│       └── pages/                   # 页面逻辑
│           ├── login.js            # 登录页
│           ├── dashboard.js        # 需求列表页
│           ├── requirement.js      # 需求详情页
│           ├── ai-config.js       # AI 配置页
│           ├── call-logs.js        # 调用记录页
│           ├── analytics-page.js   # 数据概览页
│           └── knowledge-base.js   # 知识库管理页
├── deploy.md                        # 部署指南
├── develop.md                       # 开发文档（本文档）
└── README.md                        # 项目说明
```

### 2.2 数据流

```
用户输入需求
    │
    ▼
┌──────────┐     ┌───────────────┐     ┌──────────────┐
│ 需求分析  │ ──▶ │ 多轮问答补全  │ ──▶ │  模块拆分    │
│ (AI)     │     │ (AI ⇄ User)  │     │  (AI)       │
└──────────┘     └───────────────┘     └──────┬───────┘
                                              │
                    ┌─────────────────────────┘
                    ▼
              ┌──────────────┐
              │ 逐模块生成用例 │
              │ (AI, 异步)   │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ 结构化测试用例 │
              │ (存入数据库)  │
              └──────┬───────┘
                     │
                     ▼ 用户可选择性重新生成
              ┌──────────────┐
              │  重新生成记录  │
              │ (新旧快照)    │
              └──────────────┘
```

### 2.3 API 路由总览

| Blueprint | 前缀 | 主要端点 |
|-----------|------|----------|
| auth | `/api/auth` | `POST /login`, `POST /register`, `POST /guest`, `GET /me` |
| requirements | `/api/requirements` | `GET /`, `POST /`, `GET/PUT/DELETE /<id>` |
| qa | `/api/qa` | `POST /analyze/<id>`, `POST /answer/<id>`, `GET /<id>/history` |
| modules | `/api/modules` | `GET /requirement/<id>`, `GET/PUT/DELETE /<id>` |
| cases | `/api/cases` | `GET /module/<id>`, `GET/PUT/DELETE /<id>` |
| generate | `/api/generate` | `POST /modules`, `POST /cases` |
| regenerate | `/api/regenerate` | `POST /` (批量) |
| tasks | `/api/tasks` | `GET /<id>/status`, `GET /<id>/result` |
| ai_config | `/api/ai-config` | `GET/POST /`, `GET/PUT/DELETE /<id>`, `POST /<id>/test` |
| call_logs | `/api/call-logs` | `GET /`, `GET /<id>`, `GET /summary` |
| analytics | `/api/analytics` | `POST /track`, `GET /summary`, `GET /events` |
| export | `/api/export` | `GET /<req_id>?format=html\|md\|xmind` |
| rag | `/api/rag` | `GET /status`, `POST /query`, `POST /rebuild` |

## 三、通用 AI 接入指南

本平台兼容所有提供 **OpenAI Chat Completions API** 的模型服务商。接入步骤如下：

### 3.1 接入流程

1. 登录系统 → 左侧导航 → **AI 配置**
2. 点击 **添加模型**
3. 填写模型信息（名称、Base URL、API Key、Model 名称）
4. 可选设置 Temperature 和 Max Tokens
5. 设为默认模型（`is_default`）
6. 点击 **测试连接** 确认可用

### 3.2 常见服务商配置

| 服务商 | Base URL | 模型示例 |
|--------|----------|----------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat`, `deepseek-reasoner` |
| 智谱 AI | `https://open.bigmodel.cn/api/paas/v4` | `glm-4`, `glm-4-flash` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus`, `qwen-turbo` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k`, `moonshot-v1-32k` |

### 3.3 接入原理

平台通过 OpenAI Python SDK 发起调用，核心代码位于 `backend/app/services/ai_service.py`：

```python
from openai import OpenAI

client = OpenAI(
    base_url=ai_config.base_url,   # 服务商 API 地址
    api_key=decrypt_api_key(ai_config.api_key_encrypted),  # 解密后的 API Key
)

response = client.chat.completions.create(
    model=ai_config.model,
    messages=messages,
    temperature=ai_config.temperature,
    max_tokens=ai_config.max_tokens,
    response_format={"type": "json_object"},  # JSON 模式
)
```

**自定义服务商接入要求**：

- 提供 `POST /v1/chat/completions` 端点，兼容 OpenAI API 格式
- 支持 `messages` 数组（system/user/assistant 角色）
- 返回 `choices[0].message.content` 字段
- 支持 `response_format: {"type": "json_object"}`（JSON 模式，可选）

满足以上条件的任何 API 均可直接接入，无需修改代码。

### 3.4 API Key 安全

- API Key 通过 Fernet 对称加密后存储于数据库（`api_key_encrypted` 字段）
- 加密密钥由 `ENCRYPTION_KEY` 环境变量控制，生产环境必须修改
- 前端展示时以 `***` 掩位，仅在编辑时按需返回明文

## 四、快速开始

```bash
# 1. 创建虚拟环境
python -m venv .smart-qa

# 2. 激活虚拟环境
.smart-qa\Scripts\Activate.ps1   # Windows PowerShell
# source .smart-qa/bin/activate  # macOS/Linux

# 3. 安装依赖
cd backend
pip install -r requirements.txt

# 4. 初始化数据库
python init_db.py

# 5. 启动开发服务器
python run_dev.py
```

> **国内网络环境提示**：从 PyPI 官方源（`pypi.org`）安装依赖时常因网络超时报错 `Read timed out` 或 `No module named 'xxx'`（包未装进虚拟环境）。建议为虚拟环境 `.smart-qa` 配置国内镜像源，一次性写入虚拟环境配置后，后续所有 `pip install` 均自动走镜像源，无需每次手动加 `-i` 参数：
>
> ```bash
> # 配置阿里云镜像源（写入 .smart-qa/pip.ini，仅影响本虚拟环境）
> .smart-qa\Scripts\python.exe -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ --site
> .smart-qa\Scripts\python.exe -m pip config set global.trusted-host mirrors.aliyun.com --site
>
> # 之后安装依赖即可正常使用
> pip install -r requirements.txt
> ```
>
> 验证配置：`.smart-qa\Scripts\python.exe -m pip config list`，应显示 `global.index-url='https://mirrors.aliyun.com/pypi/simple/'`。

浏览器打开 `http://127.0.0.1:5000`，默认账号 `admin` / `admin123`（可通过 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 环境变量自定义）。

## 五、版本变更历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0.0 | 2026-09-21（2026-10-03 全量合版） | **平台全功能版本**：需求管理、AI 需求分析、多轮问答、模块与用例生成、选择性重新生成、AI/Embedding 模型配置、调用记录、数据概览、用户埋点、用户认证、游客模式、用例导出、RAG 知识库、多轮问答知识库、文档与代码导入、项目类型区分、SOP、日志治理 |

### v1.0.0 详细变更

> 本版本为平台全功能版本，涵盖需求管理、AI 生成、知识库问答、SOP、导入导出、游客模式等当前全部已交付功能。

**一、功能交付**

| 功能模块 | 说明 |
|----------|------|
| **需求管理** | 创建/编辑/删除需求，分页查询与搜索过滤，按状态（draft/analyzing/qa/generating/completed）流转 |
| **AI 需求分析** | AI 自动分析需求稿，识别歧义与缺失细节，生成追问问题列表 |
| **多轮问答补全** | 聊天式交互界面（打字机效果），AI 每轮最多追问 2 个问题，上下文充分后自动进入生成阶段 |
| **模块拆分生成** | AI 基于需求 + QA 上下文拆分 3-8 个功能模块（名称/描述/关键测试点） |
| **测试用例生成** | 逐模块生成 3-8 条结构化用例（前置条件/步骤/预期结果/优先级），覆盖功能/边界/异常/性能四类 |
| **选择性重新生成** | 勾选用例/模块，填写原因与补充描述，AI 基于原内容重新生成，保存新旧快照 |
| **AI 模型配置** | 多模型管理，支持 OpenAI 兼容 API，API Key 加密存储，一键连接测试 |
| **Embedding 模型配置** | AI 配置支持 chat / embedding / both 三种类型，可独立配置 Embedding 模型与 API |
| **全链路调用记录** | 每次 AI 调用记录 prompt/response/token 用量/耗时/状态，可展开查看详情 |
| **数据概览** | 统计卡片（用例总数/生成次数/AI 调用次数/token 消耗/成功率）、token 趋势图表、事件流 |
| **用户行为埋点** | 前后端双端埋点，追踪 page_view/click/generate_start/generate_complete/regenerate/qa_round/config_test/login/logout/guest_login 等事件 |
| **用户认证** | JWT Token 认证，用户注册/登录，密码 bcrypt 哈希存储；初始管理员账密支持 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 环境变量自定义 |
| **游客模式** | 登录页一键"游客访问"，免登录只读浏览业务页面；敏感页面对游客隐藏，后端统一拦截写操作（403），前后端双重防护 |
| **用例导出** | 需求详情页一键导出全部模块与用例，支持 HTML / Markdown / XMind 三种格式，浏览器自动下载 |
| **RAG 知识库** | 向量嵌入检索历史用例，AI 生成时注入相似案例作为 few-shot 参考；支持知识库状态查看、问答查询、索引重建 |
| **多轮问答知识库** | 会话式问答、引用来源展示、准确度反馈（反馈入索引）、历史会话管理、代码源管理 |
| **文档上传与代码导入** | 文档上传解析（PDF/Word/Markdown）提取需求，ZIP 代码包上传与代码文档管理 |
| **项目类型区分** | 需求区分线上项目（production）与测试项目（test），仅线上项目数据纳入知识库索引 |
| **SOP 标准操作程序** | 问答结束后生成 SOP、SOP 模板配置、查看与编辑、SOP 入知识库索引 |
| **日志治理** | `LOG_LEVEL` 环境变量控制落盘级别，`error.log` 错误专用日志，HTTP 日志降噪，多模块分文件结构化日志自动轮转 |

**二、技术实现**

- Flask 应用工厂模式，13 个 API Blueprint 注册
- 后台线程异步执行 AI 生成，TaskStore 线程安全存储任务状态，前端轮询进度
- Flask 应用上下文穿透到后台线程，避免 `Working outside of application context`
- JSON 响应三级回退解析（直接解析 → 正则提取 → json_repair），容错 AI 非标准返回
- Fernet 对称加密存储 API Key
- SQLite WAL 模式 + busy_timeout 并发优化；启动时幂等 `ALTER TABLE` 迁移新列
- JWT payload 携带 `role`（`user` / `guest`）：游客 token 由 `POST /api/auth/guest` 签发，不落库；`app/core/guest_guard.py` 在 app 级 `before_request` 统一拦截游客写请求与敏感接口（返回 403，避免触发前端 401 登出）
- 前端只读采用 CSS 方案：`body.guest-mode .user-only { display: none !important }`，静态按钮加类即可隐藏，不侵入业务逻辑
- 向量检索：numpy 余弦相似度计算，Embedding API 生成向量，知识库索引可增量重建
- 多 Logger 分模块结构化日志，日志文件自动轮转
- 前端原生 JS 模块化，无构建工具依赖

**三、数据模型**

13 张数据表：`users`、`requirements`、`modules`、`test_cases`、`qa_sessions`、`ai_configs`、`ai_call_logs`、`analytics_events`、`regenerations`、`embeddings`、`code_documents`、`sops`、`kb_sessions`

**四、主要依赖**

Flask 3.0+ / Flask-SQLAlchemy 3.1+ / SQLAlchemy 2.0+ / PyJWT 2.8+ / openai 1.10+ / cryptography 42+ / json-repair 0.3+ / numpy 1.26+ / scikit-learn 1.5+ / flask-cors 4.0+；数据库 SQLite（WAL 模式）

---

## 六、日志文件说明

日志文件位于 `backend/logs/` 目录（可通过 `LOG_DIR` 环境变量自定义），使用 `RotatingFileHandler` 自动轮转（单文件 512KB，保留 3 个备份）。

### 日志级别配置

通过 `LOG_LEVEL` 环境变量控制最低记录级别，默认 `INFO`：

| LOG_LEVEL | 落盘内容 | 适用场景 |
|-----------|----------|----------|
| `DEBUG` | DEBUG 及以上（全部日志） | 排查问题、开发调试 |
| `INFO`（默认） | INFO / WARNING / ERROR（不含 DEBUG） | 日常运行 |
| `WARNING` | WARNING / ERROR | 减少噪音、仅关注异常 |
| `ERROR` | 仅 ERROR | 生产环境精简模式 |

> 非法值自动回退为 INFO，不会导致启动失败。

### 日志文件内容

| 文件 | 记录内容 | 典型级别 |
|------|----------|----------|
| `app.log` | **汇总日志**：所有模块的日志合并写入，是全局视角的首选查看文件 | INFO+ |
| `error.log` | **错误专用日志**：所有模块的 ERROR 及以上级别记录，含完整 traceback；全局异常处理器（500/Exception）自动写入 | ERROR+ |
| `api.log` | **API 层日志**：认证（登录/注册）、需求 CRUD、QA 分析、模块/用例操作、生成任务、导出、RAG 等 API 端点日志 | INFO（关键操作）/ WARNING（4xx）/ ERROR（5xx） |
| `ai.log` | **AI 服务日志**：AI API 调用起止、Embedding 向量生成、RAG 查询与重建；调用详情由 `AICallLog` 表记录，日志仅记录关键里程碑 | INFO（起止/完成）/ DEBUG（参数/结果）/ ERROR（失败） |
| `generation.log` | **生成编排日志**：用例生成全流程里程碑——需求分析开始、QA 轮次、模块拆分完成、逐模块用例生成完成、重新生成完成 | INFO（里程碑）/ DEBUG（逐条进度）/ ERROR（失败） |
| `auth.log` | **认证日志**：用户登录成功/失败、注册 | INFO（成功）/ WARNING（失败） |
| `middleware.log` | **HTTP 请求日志**：仅记录后端 API 响应（非静态资源）；2xx 为 DEBUG（默认不落盘），4xx 为 WARNING，5xx 为 ERROR，含请求方法、路径、状态码、耗时 | DEBUG/WARNING/ERROR |
| `call_log.log` | **AI 调用记录服务日志**：AICallLog 表写入操作的辅助日志 | DEBUG（默认不落盘）/ WARNING（异常） |
| `analytics.log` | **埋点统计日志**：用户行为事件追踪（page_view/click/generate 等）写入异常 | DEBUG（默认不落盘）/ ERROR（失败） |

### 日志级别分布

- **始终记录（任何 LOG_LEVEL）**：ERROR、WARNING
- **默认记录（LOG_LEVEL=INFO）**：业务关键 INFO（需求创建、生成里程碑、迁移日志等）
- **默认不记录（LOG_LEVEL=INFO 时）**：DEBUG 级别（HTTP 200 响应、AI 调用参数/结果、逐条生成进度、埋点细节等）
- **排查时恢复**：设 `LOG_LEVEL=DEBUG` 重启即可查看全部 DEBUG 日志

> **清理日志**：停服后删除 `backend/logs/` 目录下的文件，重启后自动重建为空文件。运行中清理在 Windows 下会因文件锁定失败。

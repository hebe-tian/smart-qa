# 部署指南

本文档介绍 AI 测试用例生成平台 的本地开发环境搭建与 PythonAnywhere 生产部署。

---

## 一、本地开发环境

### 1.1 环境要求

| 项目 | 要求 |
|------|------|
| Python | >= 3.9 |
| 操作系统 | Windows / macOS / Linux |
| 浏览器 | Chrome / Edge / Firefox（最新版） |

### 1.2 安装步骤

```bash
# 1. 克隆或下载项目
cd smart-qa

# 2. 创建虚拟环境（推荐，可在项目根目录或任意位置创建）
python -m venv .smart-qa

# 3. 激活虚拟环境
#    Windows PowerShell:
.smart-qa\Scripts\Activate.ps1
#    macOS / Linux:
source .smart-qa/bin/activate

# 4. 进入后端目录，安装依赖
cd backend
pip install -r requirements.txt

# 5. 初始化数据库（自动建表 + 创建默认管理员）
python init_db.py

# 6. 启动开发服务器
python run_dev.py
```

### 1.3 访问应用

浏览器打开 `http://127.0.0.1:5000`，使用默认账号登录：

```
用户名: admin
密码:   admin123
```

### 1.4 常用开发命令

| 命令 | 说明 |
|------|------|
| `python run_dev.py` | 启动开发服务器（debug 模式，端口 5000） |
| `python init_db.py` | 初始化/重置数据库 |
| `python -c "from app import create_app; app=create_app(); app.app_context().push(); from app.extensions import db; db.create_all(); print('done')"` | 仅建表不重置数据 |

### 1.5 配置说明

通过环境变量或 `app/config.py` 调整配置：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SECRET_KEY` | `dev-secret-key-change-in-production` | Flask 会话密钥，生产环境必须修改 |
| `ENCRYPTION_KEY` | `dev-encryption-key-change-in-prod-32b` | AI API Key 加密密钥，生产环境必须修改 |
| `ADMIN_USERNAME` | `admin` | 初始管理员登录名（仅首次初始化数据库无用户时创建） |
| `ADMIN_PASSWORD` | `admin123` | 初始管理员密码（仅首次初始化数据库无用户时创建） |
| `DB_DIR` | `backend/instance` | 数据库目录 |
| `LOG_DIR` | `backend/logs` | 日志目录 |
| `PORT` | `5000` | 服务端口 |

### 1.6 项目结构

```
smart-qa/
├── backend/
│   ├── app/
│   │   ├── __init__.py              # Flask 应用工厂
│   │   ├── config.py                # 配置
│   │   ├── extensions.py             # SQLAlchemy 实例
│   │   ├── models/                  # 数据模型 (9 张表)
│   │   ├── api/                     # API 蓝图 (10 个 Blueprint)
│   │   ├── services/                # 服务层 (AI/Prompt/Case/TaskStore/Logging/CallLog/Analytics)
│   │   └── core/                    # 中间件/装饰器/安全
│   ├── requirements.txt
│   ├── wsgi.py                      # PythonAnywhere WSGI 入口
│   ├── run_dev.py                   # 本地开发服务器
│   └── init_db.py                   # 数据库初始化
├── frontend/
│   ├── index.html                   # 登录页
│   ├── dashboard.html               # 需求列表页
│   ├── requirement.html             # 需求详情页（核心）
│   ├── ai-config.html               # AI 配置页
│   ├── call-logs.html               # 调用记录页
│   ├── analytics.html               # 数据概览页
│   ├── css/                         # 样式文件
│   └── js/                          # JS 模块
├── deploy.md                        # 本文档
└── README.md                        # 项目说明
```

---

## 二、PythonAnywhere 部署

### 2.1 前置准备

1. 注册 PythonAnywhere 账号（https://www.pythonanywhere.com/）
2. 准备好项目代码（本地测试通过）

### 2.2 上传项目

通过 PythonAnywhere Dashboard 的 **Files** 标签页，或使用 Git/Bash console 上传：

```bash
# 方式一：通过 Git 克隆
cd ~
git clone https://github.com/{your-repo}/smart-qa.git

# 方式二：通过 Zip 上传后解压
cd ~
unzip smart-qa.zip
```

确保项目路径为 `/home/{username}/smart-qa/`。

### 2.3 创建 Web App

1. 进入 Dashboard → **Web** 标签页
2. 点击 **Add a new web app**
3. 选择 **Manual configuration**（不要选 Flask 预置模板）
4. 选择 **Python 3.x**（与本地版本一致）
5. 设置以下路径：

| 配置项 | 值 |
|--------|-----|
| Source code | `/home/{username}/smart-qa/backend` |
| Working directory | `/home/{username}/smart-qa/backend` |

### 2.4 配置 WSGI 文件

在 Web 标签页找到 **WSGI configuration file** 链接，点击编辑，将内容替换为：

```python
import os
import sys

# 设置项目路径
project_home = '/home/{username}/smart-qa'
os.environ['PROJECT_HOME'] = project_home

path = os.path.join(project_home, 'backend')
if path not in sys.path:
    sys.path.insert(0, path)

from app import create_app
application = create_app()
```

> 也可以直接使用项目自带的 `wsgi.py` 文件，在 WSGI 配置中设置环境变量 `PROJECT_HOME=/home/{username}/smart-qa`。

### 2.5 安装依赖

打开 Bash console，执行：

```bash
pip install --user -r /home/{username}/smart-qa/backend/requirements.txt
```

### 2.6 配置静态文件

在 Web 标签页的 **Static files** 部分添加以下映射：

| URL | Directory |
|-----|-----------|
| `/css/` | `/home/{username}/smart-qa/frontend/css/` |
| `/js/` | `/home/{username}/smart-qa/frontend/js/` |
| `/assets/` | `/home/{username}/smart-qa/frontend/assets/` |

### 2.7 设置环境变量

在 Web 标签页的 **Environment variables** 部分添加：

| 变量 | 值 |
|------|-----|
| `SECRET_KEY` | （随机强密码字符串） |
| `ENCRYPTION_KEY` | （32 位随机字符串） |
| `ADMIN_USERNAME` | （自定义初始管理员登录名，如 `myadmin`） |
| `ADMIN_PASSWORD` | （自定义初始管理员密码，建议强密码） |

> `ADMIN_USERNAME` / `ADMIN_PASSWORD` 仅在数据库无用户（首次初始化）时用于创建初始管理员，已有数据库不受影响。

生成随机密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2.8 初始化数据库

打开 Bash console，执行：

```bash
cd /home/{username}/smart-qa/backend
python init_db.py
```

### 2.9 重启 Web App

回到 Web 标签页，点击绿色的 **Reload** 按钮。

### 2.10 验证

浏览器访问 `https://{username}.pythonanywhere.com/`，应看到登录页面。

使用 `admin` / `admin123` 登录后，前往 **AI 配置** 页面添加 AI 模型。

---

## 三、部署后配置

### 3.1 添加 AI 模型

1. 登录系统 → 左侧导航 → **AI 配置**
2. 点击 **添加模型**
3. 填写模型信息：

| 字段 | 示例值 |
|------|--------|
| 名称 | `DeepSeek Chat` |
| Provider | `deepseek` |
| API Base URL | `https://api.deepseek.com/v1` |
| API Key | `sk-xxxxxxxxxxxxx` |
| Model | `deepseek-chat` |

4. 点击 **测试连接** 确认可用

### 3.2 修改管理员密码

登录后在系统中修改默认密码，或在 console 中执行：

```bash
cd /home/{username}/smart-qa/backend
python -c "
from app import create_app
from app.extensions import db
from app.models.user import User
app = create_app()
with app.app_context():
    u = User.query.filter_by(username='admin').first()
    u.set_password('你的新密码')
    db.session.commit()
    print('Password updated')
"
```

### 3.3 日志查看

日志文件位于 `backend/logs/` 目录：

| 文件 | 说明 |
|------|------|
| `app.log` | 全模块合并日志 |
| `middleware.log` | HTTP 请求/响应日志（仅 API 请求） |
| `api.log` | API 业务日志 |
| `ai.log` | AI 调用日志 |
| `generation.log` | 用例生成日志 |
| `auth.log` | 认证日志 |
| `call_log.log` | AI 调用记录服务日志 |
| `analytics.log` | 埋点统计日志 |

日志策略：
- 前端资源请求（CSS/JS/图片/HTML）**不记录**日志
- 后端 API 请求正常记录
- ERROR 和 WARNING **必须记录**

---

## 四、常见问题

### 4.1 静态文件 404

检查 PythonAnywhere Web 标签页的 Static files 映射是否正确，URL 路径和 Directory 路径都要匹配。

### 4.2 数据库锁定 (database is locked)

SQLite 并发写入可能锁定。项目已启用 WAL 模式和 `busy_timeout=5000ms`。如仍出现问题，检查是否有多个进程同时写入。

### 4.3 AI 调用超时

PythonAnywhere 免费账号限制 5 分钟请求超时。生成大量测试用例可能超时，建议：
- 将需求拆分为多个小需求分别生成
- 升级到付费账号

### 4.4 模块导入失败

确认 `sys.path` 已正确添加 backend 目录，依赖已通过 `pip install --user` 安装。

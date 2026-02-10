# 个人博客项目（Vue + Element UI + Flask + SQLAlchemy + MySQL）

## 功能
- 博客首页文章列表、关键字搜索。
- 分类筛选、标签筛选。
- 文章详情与评论。
- 管理员登录。
- 管理员文章新增、编辑、删除、发布/下线。
- 一键初始化（创建管理员、默认分类/标签、示例文章）。

## 技术栈
- 前端：Vue2 + Element UI + Axios（静态页，Nginx 托管）
- 后端：Flask + Flask-SQLAlchemy + PyMySQL
- 数据库：远程 MySQL（使用你提供的连接）
- 部署：Docker Compose

## 目录结构
```text
personal-blog/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── models.py
│   │   └── routes.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── Dockerfile
│   └── index.html
├── nginx/
│   └── default.conf
├── .env.example
└── docker-compose.yml
```

## 启动
```bash
docker compose up -d --build
```

访问：
- 前端：http://localhost:8080
- 后端健康检查：http://localhost:5000/health

## 初始化与登录
1. 打开前端后点击“管理登录”。
2. 点击“首次初始化”。
3. 使用默认账号登录：
   - 用户名：admin
   - 密码：admin123

## 使用远程 MySQL（你提供的连接方式）
项目已在 `backend/app/config.py` 与 `.env.example` 中内置：

```text
mysql+pymysql://pay:9J7pWfK2zEDqR@47.115.225.64:3306/personal_blog?charset=utf8mb4
```

`docker-compose.yml` 已默认使用该远程连接，不再创建本地 MySQL 容器。请确保远端已创建 `personal_blog` 库并放行当前部署机器访问。

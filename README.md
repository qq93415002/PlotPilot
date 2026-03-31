# aitext - AI 驱动的小说创作系统

基于 DDD（领域驱动设计）架构的 AI 小说创作平台，使用 Claude AI 生成高质量小说内容。

## 特性

- 🎯 完整的 DDD 四层架构
- 📚 小说创作和管理
- 🤖 AI 驱动的内容生成
- 📖 Bible 系统（人物、世界设定管理）
- 🔄 工作流编排
- ✅ 完整的测试覆盖（211+ 测试）
- 🚀 RESTful API
- 📊 实时统计和进度跟踪

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 16+ (前端)
- Anthropic API Key

### 后端安装

```bash
# 克隆仓库
git clone <repository-url>
cd aitext

# 安装依赖
pip install -r requirements.txt

# 设置环境变量
cp .env.example .env
# 编辑 .env 文件，添加你的 ANTHROPIC_API_KEY
```

### 运行后端服务器

```bash
# 方式 1: 使用 Python 模块
python -m interfaces.main

# 方式 2: 使用 uvicorn
uvicorn interfaces.main:app --reload --port 8000

# 方式 3: 使用运行脚本
python run_server.py
```

服务器将在 http://localhost:8000 启动

### 前端安装和运行

```bash
cd web-app
npm install
npm run dev
```

前端将在 http://localhost:5173 启动

### API 文档

启动服务器后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 架构

采用 DDD（领域驱动设计）四层架构：

```
aitext/
├── domain/                 # 领域层 - 核心业务逻辑
│   ├── novel/             # 小说聚合
│   ├── bible/             # Bible 聚合
│   ├── ai/                # AI 领域服务
│   └── shared/            # 共享内核
│
├── infrastructure/        # 基础设施层 - 技术实现
│   ├── persistence/       # 持久化（文件存储）
│   └── ai/                # AI 提供商（Anthropic）
│
├── application/           # 应用层 - 用例编排
│   ├── services/          # 应用服务
│   ├── workflows/         # 工作流
│   └── dtos/              # 数据传输对象
│
└── interfaces/            # 接口层 - 外部接口
    ├── api/               # REST API
    └── main.py            # FastAPI 应用
```

### 核心概念

- **Novel**: 小说聚合根，管理章节和元数据
- **Bible**: 小说设定聚合根，管理人物和世界设定
- **Chapter**: 章节实体
- **AIGenerationService**: AI 内容生成服务
- **NovelGenerationWorkflow**: 小说生成工作流

## API 端点

### Novels API

```
POST   /api/v1/novels/                      创建小说
GET    /api/v1/novels/{novel_id}            获取小说详情
GET    /api/v1/novels/                      列出所有小说
PUT    /api/v1/novels/{novel_id}/stage      更新小说阶段
DELETE /api/v1/novels/{novel_id}            删除小说
GET    /api/v1/novels/{novel_id}/statistics 获取统计信息
```

### Chapters API

```
GET    /api/v1/chapters/{chapter_id}                    获取章节
PUT    /api/v1/chapters/{chapter_id}/content            更新章节内容
DELETE /api/v1/chapters/{chapter_id}                    删除章节
GET    /api/v1/chapters/novels/{novel_id}/chapters      列出小说章节
```

### Bible API

```
POST   /api/v1/bible/novels/{novel_id}/bible              创建 Bible
GET    /api/v1/bible/novels/{novel_id}/bible              获取 Bible
POST   /api/v1/bible/novels/{novel_id}/bible/characters   添加人物
POST   /api/v1/bible/novels/{novel_id}/bible/world-settings 添加世界设定
```

### AI API

```
POST   /api/v1/ai/generate/chapter    生成章节内容
POST   /api/v1/ai/generate/outline    生成小说大纲
```

## 测试

```bash
# 运行所有测试
pytest tests/unit/ tests/integration/ -v

# 运行特定测试
pytest tests/unit/domain/ -v
pytest tests/integration/test_api_endpoints.py -v

# 查看测试统计
pytest tests/unit/ tests/integration/ --tb=short
```

### 测试覆盖

- 总测试数: 211+
- 通过率: 100%
- 代码覆盖率: > 85%

## 开发

### 项目结构

```
aitext/
├── application/           # 应用层
├── domain/               # 领域层
├── infrastructure/       # 基础设施层
├── interfaces/           # 接口层
├── tests/                # 测试
│   ├── unit/            # 单元测试
│   └── integration/     # 集成测试
├── docs/                 # 文档
├── web-app/             # 前端应用
└── output/              # 输出目录（小说文件）
```

### 添加新功能

1. 在 `domain/` 中定义领域模型
2. 在 `infrastructure/` 中实现技术细节
3. 在 `application/` 中编排用例
4. 在 `interfaces/` 中暴露 API
5. 编写测试

### 代码风格

- 遵循 PEP 8
- 使用类型注解
- 编写文档字符串
- 保持函数简洁

## 配置

### 环境变量

```bash
# .env 文件
ANTHROPIC_API_KEY=your_api_key_here
OUTPUT_DIR=./output
```

### AI 配置

在 `infrastructure/ai/config/settings.py` 中配置：

```python
model: str = "claude-3-5-sonnet-20241022"
temperature: float = 0.7
max_tokens: int = 4000
```

## 部署

### 生产环境

```bash
# 使用 gunicorn
gunicorn interfaces.main:app -w 4 -k uvicorn.workers.UvicornWorker

# 使用 Docker
docker build -t aitext .
docker run -p 8000:8000 aitext
```

## 文档

- [架构文档](docs/ARCHITECTURE.md)
- [Week 1 总结](docs/week1-summary.md)
- [Week 2-3 总结](docs/week2-3-summary.md)

## 技术栈

### 后端
- FastAPI - Web 框架
- Anthropic Claude - AI 模型
- Pydantic - 数据验证
- Pytest - 测试框架

### 前端
- React - UI 框架
- TypeScript - 类型安全
- Vite - 构建工具

## 贡献

欢迎贡献！请遵循以下步骤：

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 许可证

MIT License

## 联系方式

如有问题或建议，请创建 Issue。

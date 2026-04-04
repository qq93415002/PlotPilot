"""FastAPI 主应用

提供 RESTful API 接口。
"""
from pathlib import Path
import sys
import time
from datetime import datetime

# 必须在其他 aitext 模块导入前执行：将仓库根目录 `.env` 写入 os.environ
_AITEXT_ROOT = Path(__file__).resolve().parents[1]
if str(_AITEXT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AITEXT_ROOT))
try:
    from load_env import load_env

    load_env()
except Exception:
    # 无 .env 或非标准启动方式时忽略
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interfaces.api.v1 import novels, chapters, bible, cast, knowledge, generation, story_structure
from interfaces.api.v1 import chapter_element_routes, knowledge_graph_routes, continuous_planning_routes
from interfaces.api.v1 import worldbuilding_routes, context_intelligence, narrative_state, foreshadow_ledger
from web.routers.stats import create_stats_router
from web.services.stats_service import StatsService
from web.repositories.sqlite_stats_repository_adapter import SqliteStatsRepositoryAdapter
from infrastructure.persistence.database.connection import get_database
from application.paths import DATA_DIR

# 后端版本号（每次重启递增）
BACKEND_VERSION = datetime.now().strftime("%Y%m%d-%H%M%S")
STARTUP_TIME = time.time()

print("=" * 80)
print(f"🚀 BACKEND STARTING - Version: {BACKEND_VERSION}")
print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)

# 创建 FastAPI 应用
app = FastAPI(
    title="aitext API",
    version="2.0.0",
    description="AI 小说创作平台 API"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（开发环境）
    allow_credentials=False,  # 使用 * 时必须设为 False
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册新架构路由
app.include_router(novels.router, prefix="/api/v1")
app.include_router(chapters.router, prefix="/api/v1/novels")
app.include_router(bible.router, prefix="/api/v1")
app.include_router(cast.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(generation.router, prefix="/api/v1")
app.include_router(story_structure.router, prefix="/api/v1")
app.include_router(context_intelligence.router, prefix="/api/v1")
app.include_router(narrative_state.router, prefix="/api/v1")
app.include_router(foreshadow_ledger.router, prefix="/api/v1")

# 注册统一的持续规划路由
app.include_router(continuous_planning_routes.router)
app.include_router(chapter_element_routes.router)
app.include_router(knowledge_graph_routes.router)
app.include_router(worldbuilding_routes.router)

# 注册统计路由（使用 SQLite 适配器）
stats_repository = SqliteStatsRepositoryAdapter(get_database())
stats_service = StatsService(stats_repository)
stats_router = create_stats_router(stats_service)
app.include_router(stats_router, prefix="/api/stats", tags=["statistics"])


@app.get("/")
async def root():
    """根路径

    Returns:
        欢迎消息
    """
    return {"message": "aitext API v2.0"}


@app.get("/health")
async def health_check():
    """健康检查

    Returns:
        健康状态
    """
    uptime = time.time() - STARTUP_TIME
    return {
        "status": "healthy",
        "version": BACKEND_VERSION,
        "uptime_seconds": round(uptime, 2)
    }

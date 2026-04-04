# tests/integration/interfaces/api/v1/test_foreshadow_ledger_api.py
import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from interfaces.main import app
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from infrastructure.persistence.repositories.file_foreshadowing_repository import FileForeshadowingRepository
from interfaces.api.dependencies import get_foreshadowing_repository


class TestForeshadowLedgerAPI:
    """测试潜台词账本 API"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    @pytest.fixture
    def novel_id(self):
        """测试小说 ID"""
        return "test-novel-123"

    @pytest.fixture
    def setup_registry(self, novel_id):
        """设置测试注册表"""
        # 获取仓储
        repo = get_foreshadowing_repository()

        # 创建或获取注册表
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            registry = ForeshadowingRegistry(
                id=f"registry-{novel_id}",
                novel_id=NovelId(novel_id)
            )
            repo.save(registry)

        # 清理：删除所有 subtext entries（测试前清理）
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if registry:
            entries_to_remove = [e.id for e in registry.subtext_entries]
            for entry_id in entries_to_remove:
                try:
                    registry.remove_subtext_entry(entry_id)
                except:
                    pass
            repo.save(registry)

        yield registry

        # 清理：删除所有 subtext entries（测试后清理）
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if registry:
            entries_to_remove = [e.id for e in registry.subtext_entries]
            for entry_id in entries_to_remove:
                try:
                    registry.remove_subtext_entry(entry_id)
                except:
                    pass
            repo.save(registry)

    def test_create_subtext_entry(self, client, novel_id, setup_registry):
        """测试创建潜台词账本条目"""
        response = client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-001",
                "chapter": 5,
                "character_id": "char-001",
                "hidden_clue": "主角的秘密身份",
                "sensory_anchors": {
                    "visual": "红色围巾",
                    "auditory": "轻微的咳嗽声"
                }
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "entry-001"
        assert data["chapter"] == 5
        assert data["character_id"] == "char-001"
        assert data["hidden_clue"] == "主角的秘密身份"
        assert data["sensory_anchors"]["visual"] == "红色围巾"
        assert data["status"] == "pending"
        assert data["consumed_at_chapter"] is None

    def test_create_duplicate_entry(self, client, novel_id, setup_registry):
        """测试创建重复条目"""
        # 创建第一个条目
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-002",
                "chapter": 5,
                "character_id": "char-001",
                "hidden_clue": "线索",
                "sensory_anchors": {"visual": "红色"}
            }
        )

        # 尝试创建重复条目
        response = client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-002",
                "chapter": 6,
                "character_id": "char-002",
                "hidden_clue": "另一个线索",
                "sensory_anchors": {"visual": "蓝色"}
            }
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_list_subtext_entries(self, client, novel_id, setup_registry):
        """测试列出所有条目"""
        # 创建多个条目
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-003",
                "chapter": 5,
                "character_id": "char-001",
                "hidden_clue": "线索1",
                "sensory_anchors": {"visual": "红色"}
            }
        )
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-004",
                "chapter": 6,
                "character_id": "char-002",
                "hidden_clue": "线索2",
                "sensory_anchors": {"visual": "蓝色"}
            }
        )

        # 列出所有条目
        response = client.get(f"/api/v1/novels/{novel_id}/foreshadow-ledger")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        assert any(e["id"] == "entry-003" for e in data)
        assert any(e["id"] == "entry-004" for e in data)

    def test_list_subtext_entries_by_status(self, client, novel_id, setup_registry):
        """测试按状态过滤条目"""
        # 创建 pending 条目
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-005",
                "chapter": 5,
                "character_id": "char-001",
                "hidden_clue": "线索",
                "sensory_anchors": {"visual": "红色"}
            }
        )

        # 列出 pending 条目
        response = client.get(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            params={"status": "pending"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["status"] == "pending" for e in data)

    def test_get_subtext_entry(self, client, novel_id, setup_registry):
        """测试获取单个条目"""
        # 创建条目
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-006",
                "chapter": 5,
                "character_id": "char-001",
                "hidden_clue": "线索",
                "sensory_anchors": {"visual": "红色"}
            }
        )

        # 获取条目
        response = client.get(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/entry-006"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "entry-006"
        assert data["hidden_clue"] == "线索"

    def test_get_nonexistent_entry(self, client, novel_id, setup_registry):
        """测试获取不存在的条目"""
        response = client.get(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/nonexistent"
        )

        assert response.status_code == 404

    def test_update_subtext_entry(self, client, novel_id, setup_registry):
        """测试更新条目"""
        # 创建条目
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-007",
                "chapter": 5,
                "character_id": "char-001",
                "hidden_clue": "原始线索",
                "sensory_anchors": {"visual": "红色"}
            }
        )

        # 更新条目
        response = client.put(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/entry-007",
            json={
                "hidden_clue": "更新后的线索",
                "status": "consumed",
                "consumed_at_chapter": 10
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["hidden_clue"] == "更新后的线索"
        assert data["status"] == "consumed"
        assert data["consumed_at_chapter"] == 10

    def test_delete_subtext_entry(self, client, novel_id, setup_registry):
        """测试删除条目"""
        # 创建条目
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-008",
                "chapter": 5,
                "character_id": "char-001",
                "hidden_clue": "线索",
                "sensory_anchors": {"visual": "红色"}
            }
        )

        # 删除条目
        response = client.delete(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/entry-008"
        )

        assert response.status_code == 204

        # 验证已删除
        response = client.get(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/entry-008"
        )
        assert response.status_code == 404

    def test_match_subtext_entry(self, client, novel_id, setup_registry):
        """测试匹配查询"""
        # 创建条目
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-009",
                "chapter": 5,
                "character_id": "char-001",
                "hidden_clue": "线索",
                "sensory_anchors": {
                    "visual": "红色围巾",
                    "auditory": "脚步声"
                }
            }
        )

        # 匹配查询
        response = client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/match",
            json={
                "current_anchors": {
                    "visual": "她戴着红色围巾走进房间",
                    "auditory": "远处传来脚步声"
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["matched"] is True
        assert data["entry"]["id"] == "entry-009"

    def test_match_no_result(self, client, novel_id, setup_registry):
        """测试无匹配结果"""
        # 创建条目
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-010",
                "chapter": 5,
                "character_id": "char-001",
                "hidden_clue": "线索",
                "sensory_anchors": {"visual": "红色围巾"}
            }
        )

        # 匹配查询（不匹配）
        response = client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/match",
            json={
                "current_anchors": {"visual": "蓝色帽子"}
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["matched"] is False
        assert data["entry"] is None

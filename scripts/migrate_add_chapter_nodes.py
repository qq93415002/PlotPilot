#!/usr/bin/env python3
"""
数据库迁移：将章节纳入 story_nodes 树形结构

修改：
1. story_nodes.node_type 增加 'chapter' 类型
2. 将现有 chapters 表数据迁移到 story_nodes
3. chapters 表保留，但通过 story_node_id 关联

运行方式：
    python aitext/scripts/migrate_add_chapter_nodes.py
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
import uuid

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / "data" / "aitext.db"


def migrate():
    """执行迁移"""
    print(f"连接数据库: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. 重建 story_nodes 表（增加 chapter 类型）
        print("\n[1/4] 重建 story_nodes 表...")

        # 备份现有数据
        cursor.execute("SELECT * FROM story_nodes")
        existing_nodes = cursor.fetchall()

        # 删除旧表
        cursor.execute("DROP TABLE IF EXISTS story_nodes")

        # 创建新表
        cursor.execute("""
            CREATE TABLE story_nodes (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                parent_id TEXT,
                node_type TEXT NOT NULL CHECK(node_type IN ('part', 'volume', 'act', 'chapter')),
                number INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                order_index INTEGER NOT NULL,

                -- 章节范围（自动计算，仅用于 part/volume/act）
                chapter_start INTEGER,
                chapter_end INTEGER,
                chapter_count INTEGER DEFAULT 0,

                -- 章节内容（仅用于 chapter 类型）
                content TEXT,
                word_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'draft',  -- draft, completed, reviewed

                -- 元数据（JSON 格式）
                metadata TEXT DEFAULT '{}',

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES story_nodes(id) ON DELETE CASCADE
            )
        """)

        # 恢复数据
        if existing_nodes:
            cursor.executemany("""
                INSERT INTO story_nodes
                (id, novel_id, parent_id, node_type, number, title, description,
                 order_index, chapter_start, chapter_end, chapter_count, metadata,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, existing_nodes)
            print(f"✓ 恢复 {len(existing_nodes)} 个节点")

        print("✓ story_nodes 表重建成功")

        # 2. 创建索引
        print("\n[2/4] 创建索引...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_story_nodes_novel
            ON story_nodes(novel_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_story_nodes_parent
            ON story_nodes(parent_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_story_nodes_type
            ON story_nodes(node_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_story_nodes_order
            ON story_nodes(novel_id, order_index)
        """)
        print("✓ 索引创建成功")

        # 3. 迁移现有章节到 story_nodes
        print("\n[3/4] 迁移章节数据...")
        cursor.execute("""
            SELECT id, novel_id, number, title, content,
                   status, act_id, created_at, updated_at
            FROM chapters
            ORDER BY novel_id, number
        """)
        chapters = cursor.fetchall()

        migrated = 0
        for chapter in chapters:
            chapter_id, novel_id, number, title, content, status, act_id, created_at, updated_at = chapter

            # 计算字数
            word_count = len(content) if content else 0

            # 创建 chapter 节点
            node_id = f"chapter-{chapter_id}"
            cursor.execute("""
                INSERT INTO story_nodes
                (id, novel_id, parent_id, node_type, number, title,
                 order_index, content, word_count, status, created_at, updated_at)
                VALUES (?, ?, ?, 'chapter', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (node_id, novel_id, act_id, number, title, number,
                  content, word_count, status or 'draft', created_at, updated_at))
            migrated += 1

        print(f"✓ 迁移 {migrated} 个章节")

        # 4. 添加 story_node_id 到 chapters 表（保持兼容）
        print("\n[4/4] 扩展 chapters 表...")
        cursor.execute("PRAGMA table_info(chapters)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'story_node_id' not in columns:
            cursor.execute("""
                ALTER TABLE chapters ADD COLUMN story_node_id TEXT
                REFERENCES story_nodes(id) ON DELETE CASCADE
            """)
            print("✓ 添加 story_node_id 列")

            # 更新关联
            cursor.execute("""
                UPDATE chapters
                SET story_node_id = 'chapter-' || id
            """)
            print("✓ 更新章节关联")
        else:
            print("✓ story_node_id 列已存在")

        # 提交事务
        conn.commit()
        print("\n✅ 迁移完成！")
        print("\n新的数据结构：")
        print("  📚 部 (Part)")
        print("    📖 卷 (Volume)")
        print("      🎬 幕 (Act)")
        print("        📄 章 (Chapter) ← 新增到树中")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        conn.close()


def verify():
    """验证迁移结果"""
    print("\n" + "="*50)
    print("验证迁移结果...")
    print("="*50)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 检查 node_type 约束
        cursor.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='story_nodes'
        """)
        table_sql = cursor.fetchone()[0]
        if "'chapter'" in table_sql:
            print("✓ story_nodes 支持 chapter 类型")
        else:
            print("✗ story_nodes 不支持 chapter 类型")
            return False

        # 统计各类型节点数量
        cursor.execute("""
            SELECT node_type, COUNT(*)
            FROM story_nodes
            GROUP BY node_type
        """)
        for node_type, count in cursor.fetchall():
            print(f"✓ {node_type}: {count} 个节点")

        # 检查 chapters 表的 story_node_id 列
        cursor.execute("PRAGMA table_info(chapters)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'story_node_id' in columns:
            print("✓ chapters.story_node_id 列存在")
        else:
            print("✗ chapters.story_node_id 列不存在")
            return False

        print("\n✅ 验证通过！")
        return True

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    print("="*50)
    print("数据库迁移：章节纳入树形结构")
    print("="*50)

    migrate()
    verify()

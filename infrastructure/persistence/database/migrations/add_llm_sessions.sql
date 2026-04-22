-- LLM 会话记录表：记录所有与 AI 模型交互的请求和响应
CREATE TABLE IF NOT EXISTS llm_sessions (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('USER', 'ASSISTANT')),
    chat TEXT NOT NULL,
    model TEXT,
    prompt_node TEXT,
    chapter_number INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

-- 为 novel_id 和 created_at 创建索引，加速查询
CREATE INDEX IF NOT EXISTS idx_llm_sessions_novel_id ON llm_sessions(novel_id);
CREATE INDEX IF NOT EXISTS idx_llm_sessions_created_at ON llm_sessions(created_at DESC);

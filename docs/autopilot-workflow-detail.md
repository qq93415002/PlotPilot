# 托管写小说详细流程

> 本文档详细描述 PlotPilot 全托管（Autopilot）模式从启动到完本的全流程，重点覆盖每个阶段的提示词构建逻辑。

---

## 一、全局架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     AutopilotDaemon (守护进程)                    │
│  run_forever() → 死循环轮询 DB → 捞出 RUNNING 小说 → 状态机驱动  │
└─────────────┬───────────────────────────────────────────────────┘
              │
     ┌────────┼────────────────────────────────────────────┐
     │        │                                            │
     ▼        ▼                                            ▼
┌─────────┐ ┌──────────┐                          ┌───────────┐
│MACRO_   │ │ACT_      │                          │AUDITING   │
│PLANNING │ │PLANNING  │                          │(审计)      │
└────┬────┘ └────┬─────┘                          └─────┬─────┘
     │           │                                      │
     │           ▼                                      │
     │    ┌──────────┐                                  │
     │    │WRITING   │──────────────────────────────────┘
     │    │(写作)     │
     │    └──────────┘
     │
     ▼
┌──────────────────┐
│PAUSED_FOR_REVIEW │ ← 人工审阅点（全自动模式可跳过）
└──────────────────┘
```

**核心设计原则**：
- **事务最小化**：DB 写操作只在读状态和更新状态两个瞬间，LLM 请求期间不持有锁
- **节拍级幂等**：每写完一个节拍立刻落库，断点续写从 `current_beat_index` 恢复
- **熔断保护**：连续失败 3 次挂起单本小说，全局熔断器防止 API 雪崩

---

## 二、状态机详解

### 2.1 NovelStage 枚举

| 阶段 | 说明 | 下一阶段 |
|------|------|----------|
| `MACRO_PLANNING` | 宏观规划（部/卷/幕结构） | `PAUSED_FOR_REVIEW` 或 `ACT_PLANNING` |
| `ACT_PLANNING` | 幕级规划（章节拆分） | `PAUSED_FOR_REVIEW` 或 `WRITING` |
| `WRITING` | 写作（节拍级生成） | `AUDITING` |
| `AUDITING` | 审计（文风/张力/叙事同步） | `WRITING`（下一章）或 `COMPLETED` |
| `PAUSED_FOR_REVIEW` | 等待人工审阅 | 由前端确认后推进 |
| `COMPLETED` | 全书完成 | 终态 |

### 2.2 守护进程主循环

```python
# AutopilotDaemon.run_forever() 伪代码
while True:
    if circuit_breaker.is_open():
        sleep(poll_interval)
        continue

    active_novels = _get_active_novels()  # DB: autopilot_status=RUNNING

    for novel in active_novels:
        _process_novel(novel)  # 根据当前 stage 分发到对应 handler

    sleep(poll_interval)  # 默认 5 秒
```

**关键中断机制**：每个 handler 内部在 LLM 调用前后都会检查 `_is_still_running(novel)`，用户点「停止」后立即中断，不会浪费 API 调用。

---

## 三、阶段一：宏观规划（MACRO_PLANNING）

### 3.1 流程

```
_handle_macro_planning(novel)
    │
    ├─ 1. 获取目标章节数 target_chapters
    ├─ 2. planning_service.generate_macro_plan()
    │      ├─ 获取 Bible 上下文（角色/地点/时间线）
    │      ├─ 构建宏观规划提示词
    │      ├─ 调用 LLM 生成结构
    │      └─ 解析 JSON 响应
    ├─ 3. planning_service.apply_macro_plan_from_llm_result()
    │      ├─ 有效结构 → persist_macro_structure_with_fallback()
    │      └─ 无效结构 → build_minimal_macro_structure() 占位骨架
    └─ 4. 更新 novel.current_stage
           ├─ 全自动模式 → ACT_PLANNING
           └─ 半自动模式 → PAUSED_FOR_REVIEW
```

### 3.2 宏观规划提示词构建

托管模式使用**极速模式**（`structure_preference=None`），让 AI 根据目标章节数自主决定结构规模。

#### 3.2.1 规划深度自适应

| 目标章节数 | 规划深度 | 行为 |
|-----------|---------|------|
| >500 | `framework` | 只规划部/卷框架，幕节点动态生成 |
| 100-500 | `partial` | 规划前几部的幕，后续动态生成 |
| <100 | `full` | 完整规划所有部/卷/幕 |

#### 3.2.2 System Prompt 结构

```
# 角色设定
顶级网文主编，精通各种爆款商业节奏。

# 规划深度指令（动态注入）
【规划深度】目标章节数>N，采用渐进式规划：
- 只输出「部」和「卷」的标题与主题
- 每卷必须输出 estimated_chapters
- 所有卷的 estimated_chapters 之和必须等于 {target_chapters}

# 叙事结构理论指导
1. 三幕剧结构：Setup → Confrontation → Resolution
2. 英雄之旅：平凡世界→冒险召唤→试炼→深渊→蜕变→归来
3. 情绪曲线：开篇抓人→中段起伏→终局爆发
4. 钩子密度：每部结尾必须有大悬念

# 核心推演铁律 V3
1. 【结构自主】根据篇幅智能决定部/卷数量
2. 【极致冲突】每一幕必须包含核心对抗+赌注+转折
3. 【世界观融合】主要角色出现在关键幕中
4. 【商业节奏】第一部快速抛悬念，中间部重大失败，最后部收束

# 输出格式
JSON: {"parts": [{"title": "...", "volumes": [...]}]}
```

#### 3.2.3 User Prompt 结构

```
<STORY_CONTEXT>
【世界观】...
【角色设定】（限制前5个主要角色）
【角色关系】（限制前5条）
【关键地点】（限制前5个）
【时间线事件】（限制前5条）
</STORY_CONTEXT>

<TARGET_SCOPE>
目标总篇幅：精确 {target_chapters} 章
【强制约束】所有卷/幕的 estimated_chapters 之和必须等于 {target_chapters}
</TARGET_SCOPE>

请立即生成叙事骨架...
```

#### 3.2.4 降级策略

LLM 无有效输出时，使用 `build_minimal_macro_structure()` 生成最小骨架：

```
第一部 → 第一卷 → 第一幕·开端（1/3章数）
                   第二幕·发展（1/3章数）
                   第三幕·高潮与收尾（1/3章数）
```

---

## 四、阶段二：幕级规划（ACT_PLANNING）

### 4.1 流程

```
_handle_act_planning(novel)
    │
    ├─ 1. 定位当前幕节点 target_act
    │      ├─ 找到 → 继续
    │      └─ 未找到 → 动态幕生成
    │           ├─ 找到父卷节点
    │           ├─ create_next_act_auto() 或创建首幕
    │           └─ 重新加载节点
    ├─ 2. 检查该幕下是否已有章节节点
    │      ├─ 有 → 直接进入写作
    │      └─ 无 → 执行幕级规划
    ├─ 3. planning_service.plan_act_chapters()
    │      ├─ 获取 Bible 上下文
    │      ├─ 获取前序幕摘要
    │      ├─ 构建幕级规划提示词
    │      ├─ 调用 LLM 生成章节列表
    │      └─ 解析 JSON
    ├─ 4. planning_service.confirm_act_planning()
    │      ├─ 删除本幕旧章节节点（如有）
    │      ├─ 创建新章节节点（全局递增章号）
    │      ├─ 创建章节元素关联
    │      └─ 更新幕的 chapter_start/chapter_end
    └─ 5. 更新 novel.current_stage
           ├─ 新落库 → PAUSED_FOR_REVIEW 或 WRITING
           └─ 已存在 → WRITING
```

### 4.2 动态幕生成（超长篇）

当超长篇只规划了部/卷框架时，幕节点需要动态创建：

```python
# 计算应该在第几卷
chapters_per_volume = max(target_chapters // len(volume_nodes), 50)
estimated_volume_number = max(1, current_auto_chapters // chapters_per_volume + 1)

# 使用最后一个幕作为参考，创建下一幕
planning_service.create_next_act_auto(novel_id, current_act_id)
```

### 4.3 幕级规划提示词

幕级规划的提示词由 `_build_act_planning_prompt()` 构建，核心要素：

- **Bible 上下文**：角色、地点、时间线
- **前序幕摘要**：已完成幕的剧情概要
- **当前幕信息**：标题、描述、建议章数
- **输出格式**：`{"chapters": [{"title": "...", "outline": "...", "characters": [...], "locations": [...]}]}`

### 4.4 降级策略

LLM 失败或返回空章节时，使用 `_fallback_act_chapters_plan()` 生成占位章节：

```python
# 生成 N 个占位章节
for i in range(count):
    rows.append({
        "title": f"{act_label} · 第{i+1}章（占位）",
        "outline": f"【占位】{act_label} 第{i+1}章：推进本幕叙事"
    })
```

---

## 五、阶段三：写作（WRITING）—— 核心章节生成流程

### 5.1 总体流程

```
_handle_writing(novel)
    │
    ├─ 1. 目标控制
    │      ├─ current >= target_chapters → COMPLETED
    │      └─ current >= max_auto_chapters → PAUSED_FOR_REVIEW
    ├─ 2. 缓冲章判断（上一章张力 ≥ 8 时插入日常章）
    ├─ 3. 定位下一个未写章节
    ├─ 4. 构建上下文 bundle
    │      ├─ prepare_chapter_generation()（主路径）
    │      └─ build_fallback_chapter_bundle()（降级路径）
    ├─ 5. 节拍拆分 magnify_outline_to_beats()
    ├─ 6. 节拍级幂等生成 + 增量落库
    ├─ 7. 后处理 post_process_generated_chapter()
    ├─ 8. 标记章节 completed
    └─ 9. 更新计数器 → AUDITING
```

### 5.2 上下文构建（prepare_chapter_generation）

这是写作阶段最关键的步骤，决定了 LLM 能看到多少信息。

```
prepare_chapter_generation(novel_id, chapter_number, outline)
    │
    ├─ 1. 故事线上下文 _get_storyline_context()
    │      └─ 获取当前章相关的活跃故事线
    ├─ 2. 情节张力 _get_plot_tension()
    │      └─ 获取情节弧期望张力 + 下一锚点
    ├─ 3. 结构化上下文 context_builder.build_structured_context()
    │      └─ 洋葱模型预算分配（详见 5.3）
    ├─ 4. 风格摘要 _get_style_summary()
    │      └─ 从文风指纹构建风格约束
    └─ 5. 角色声线锚点 build_voice_anchor_system_section()
           └─ Bible 角色声线/小动作锚点
```

### 5.3 洋葱模型预算分配（ContextBudgetAllocator）

总预算默认 **35,000 tokens**，按四层优先级分配：

```
┌─────────────────────────────────────────────────────┐
│  T0 绝对保护层 (25%) — 绝不删减                        │
│  ├─ 🔒 FACT_LOCK（不可篡改事实块）priority=120        │
│  ├─ ✅ COMPLETED_BEATS（已完成节拍锁）priority=115    │
│  ├─ 🔍 REVEALED_CLUES（已揭露线索）priority=110       │
│  ├─ 📋 当前幕摘要 priority=100                       │
│  ├─ 🎣 待回收伏笔 priority=90                        │
│  ├─ 🩺 人设冲突提醒（宏观诊断断点）priority=85        │
│  └─ 👤 角色锚点 priority=80                          │
├─────────────────────────────────────────────────────┤
│  T1 可压缩层 (25%) — 按比例压缩                       │
│  ├─ 🔗 图谱子网（一度关系）priority=70                │
│  └─ 📚 近期幕摘要 priority=60                        │
├─────────────────────────────────────────────────────┤
│  T2 动态层 (30%) — 动态水位线                         │
│  └─ 📖 最近章节内容 priority=50                       │
│      ├─ 上一章：章首250字 + 章末1200字（侧重承接）     │
│      └─ 更早章节：章首500字预览                       │
├─────────────────────────────────────────────────────┤
│  T3 可牺牲层 (20%) — 预算不足时归零                    │
│  └─ 🔍 向量召回片段 priority=40                       │
└─────────────────────────────────────────────────────┘
```

**分配算法**：

1. 收集所有槽位内容
2. 计算 T0 强制保留量（超出总预算则截断）
3. 剩余预算按比例分配给 T1/T2/T3
4. 同层级内按 priority 排序，高优先级尽量保留
5. 超出预算的低优先级内容按比例压缩或舍弃

### 5.4 V6 记忆引擎（MemoryEngine）

记忆引擎解决长文本生成的三大状态崩溃问题：

#### 5.4.1 FACT_LOCK（不可篡改事实块）

从 Bible 动态构建，包含：

```
【🔒 绝对事实边界（一旦违背即为废稿）】

★ 角色白名单（只可使用以下有名字的角色）：
   允许: 顾言之, 乔知诺, 赵宇
   禁止: 创造任何其他有名字的角色！路人可以无名但不许命名！

★ 已死亡角色（绝对不可复活）：
   ❌ 张三(反派) - 被主角击杀（死于第15章）

★ 核心关系（不可更改）：
   顾言之 ——师徒→ 乔知诺
   赵宇 ——敌对→ 顾言之

★ 身份锁死：
   顾言之 = 天才剑修 | [已揭露] 隐藏的魔族血脉 | 当前心理: RESENTFUL

★ 核心事件时间线（不可矛盾）：
   [第1章] 顾言之入门
   [第10章] 发现魔族血脉
```

#### 5.4.2 COMPLETED_BEATS（已完成节拍锁）

防止剧情"鬼打墙"——同一事件被重复写出。

由 LLM 从每章正文中提取，格式：

```json
[
  {"beat_id": "ch3-meeting-first-time", "summary": "顾言之与乔知诺首次见面", "chapter": 3, "characters_involved": ["顾言之", "乔知诺"]},
  {"beat_id": "ch5-confrontation", "summary": "赵宇质问车祸真相", "chapter": 5, "characters_involved": ["赵宇"]}
]
```

#### 5.4.3 REVEALED_CLUES（已揭露线索清单）

防止前后矛盾——已经揭露的信息不能再当作"新发现"。

```json
[
  {"clue_id": "clue-ch4-fake-driver", "content": "顾父在车祸时可能并非驾驶员", "revealed_at_chapter": 4, "category": "truth", "is_still_valid": true}
]
```

#### 5.4.4 记忆提取提示词

章后回写时使用专门的 LLM 提取提示词：

**System Prompt**:
```
你是一个精密的小说叙事状态追踪引擎。你的唯一任务是从刚生成的章节正文里，
精确提取「记忆增量」——即这一章新发生的事情，用于维护跨章节的一致性。

━━━ 提取铁律 ━━━

① 只提取本章新发生的事
② COMPLETED_BEATS：不可逆的剧情推进，有明确的情节意义
③ REVEALED_CLUES：读者/主角第一次知道的信息
④ FACT_VIOLATIONS：对照 FACT_LOCK 逐条检查

只返回一个 JSON 对象，不要 markdown 代码块，不要解释文字。
```

**User Prompt**:
```
【待分析的章节】第 N 章
大纲：...
正文如下：...

━━━ 当前事实锁（FACT_LOCK）━━━
{fact_lock_text}
请逐条检查正文是否违反上述事实。

━━━ 已完成的节拍（COMPLETED_BEATS，不要重复提取）━━━
{existing_beats_summary}

━━━ 已揭露的线索（REVEALED_CLUES，不要重复提取）━━━
{existing_clues_summary}
```

**LLM Contract**（Pydantic 模型，`extra=forbid`）：

```python
class MemoryDeltaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completed_beats: List[CompletedBeatItem]    # max 50
    revealed_clues: List[RevealedClueItem]      # max 100
    fact_violations: List[FactViolationItem]    # max 20
```

---

## 六、章节生成提示词构建（_build_prompt）

这是整个系统最核心的提示词，直接决定生成质量。

### 6.1 System Prompt 完整结构

```
你是一位专业的网络小说作家。根据以下上下文撰写章节内容。

【故事线 / 里程碑】                          ← Phase 1: storyline_context
{storyline_context}

【情节节奏 / 期望张力】                       ← Phase 1: plot_tension
{plot_tension}

【风格约束】                                  ← Phase 2.5: style_summary
{style_summary}

以上约束须与本章大纲及后文 Bible/摘要一致；不得与之矛盾。

【角色声线与肢体语言（Bible 锚点，必须遵守）】  ← voice_anchors
{voice_anchors}

=== 上下文（三层洋葱） ===                    ← Phase 2: context
=== 绝对事实边界(FACT_LOCK) ===               ← T0
...
=== 已完成节拍(COMPLETED_BEATS) ===            ← T0
...
=== 已揭露线索(REVEALED_CLUES) ===             ← T0
...
=== 当前幕摘要 ===                             ← T0
...
=== 待回收伏笔 ===                             ← T0
...
=== 角色锚点 ===                               ← T0
...
=== 图谱子网 ===                               ← T1
...
=== 近期幕摘要 ===                             ← T1
...

=== RECENT CHAPTERS ===                        ← T2
...

=== VECTOR RECALL ===                          ← T3
...

🔒绝对事实边界(FACT_LOCK)                      ← V6 MemoryEngine 注入
✅已完成节拍(COMPLETED_BEATS)
🔍已揭露线索(REVEALED_CLUES)

写作要求：
1. 必须有多个人物互动（至少2-3个角色出场）
2. 必须有对话（不能只有独白和叙述）
3. 必须有冲突或张力
4. 保持人物性格一致
5. 推进情节发展
6. 使用生动的场景描写和细节
7. [字数规则：按节拍/整章动态]
8. 用中文写作，使用第三人称叙事
9. [节拍模式额外规则：续写/避免重复]
```

### 6.2 User Prompt 完整结构

```
请根据以下大纲撰写本章内容：

{outline}

关键要求（必须遵守）：
- 至少2-3个角色出场并互动
- 必须包含对话场景（不少于3段对话）
- 必须有明确的冲突或戏剧张力
- 场景要具体生动，不要空泛叙述
- 推进主线情节，不要原地踏步
- 结尾要有悬念或转折

[节拍模式 + 已有正文时追加]
【本章已生成正文（仅承接；禁止复述、改写或重复已交代的情节与对白；勿写章节标题）】
{chapter_draft_so_far}   ← 截断到 14000 字，保留尾部

[节拍模式追加]
【节拍 N/M】
{beat_prompt}

本段只写该节拍对应正文，紧接上文已写正文之后继续，衔接自然。

开始撰写：
```

### 6.3 字数规则动态选择

| 场景 | 规则 |
|------|------|
| 节拍模式 + 有 `beat_target_words` | `本段约 {beat_target_words} 字（本章分多段输出之一，勿写章节标题）` |
| 节拍模式 + 无具体字数 | `按下方节拍说明控制篇幅，勿写章节标题` |
| 非节拍模式 | `章节长度：3000-4000字` |

---

## 七、节拍放大器（Beat Magnifier）

### 7.1 作用

将章节大纲拆分为微观节拍，强制 AI 放慢节奏，增加感官细节，避免一章推进太多剧情。

### 7.2 特殊章节节拍

#### 第一章（开篇黄金法则）

| 节拍 | 描述 | 目标字数 | 聚焦点 |
|------|------|---------|--------|
| 1 | 开篇黄金法则：展现核心冲突，前300字内抓住读者 | 500 | hook |
| 2 | 剧情引入及人物初步互动 | 1000 | character_intro |
| 3 | 世界观或当前场景细节 | 800 | sensory |
| 4 | 埋下后续剧情伏笔或抛出首个悬念 | 700 | suspense |

#### 第二章

| 节拍 | 描述 | 目标字数 | 聚焦点 |
|------|------|---------|--------|
| 1 | 承接首章悬念：深化关键人物关系 | 800 | dialogue |
| 2 | 推进主要情节线：引入新的次要冲突 | 1200 | action |
| 3 | 情绪细节及内心活动 | 600 | emotion |
| 4 | 为第三章冲突高潮做气氛铺垫 | 400 | suspense |

#### 第三章

| 节拍 | 描述 | 目标字数 | 聚焦点 |
|------|------|---------|--------|
| 1 | 前三章的剧情小结或高潮前奏 | 600 | sensory |
| 2 | 冲突爆发/悬念高潮 | 1200 | action |
| 3 | 暴露深层问题或引出更高层面人物背景 | 800 | emotion |
| 4 | 建立长线悬念结局 | 400 | suspense |

### 7.3 关键词匹配节拍

| 大纲关键词 | 节拍序列 |
|-----------|---------|
| 争吵/冲突/质问 | 氛围→冲突爆发→情绪细节→冲突结果 |
| 战斗/打斗/对决 | 战前准备→第一回合→战斗升级→转折点→战斗结束 |
| 发现/真相/揭露 | 线索汇聚→真相揭露→情绪余波 |

### 7.4 默认节拍（起承转合）

| 节拍 | 描述 | 聚焦点 |
|------|------|--------|
| 起 | 交代场景与人物状态，抛出本章要处理的具体麻烦 | sensory |
| 承 | 阻碍升级或对手施压，人物关系或信息出现新变化 | dialogue |
| 转 | 主角做出选择、亮出底牌或发现盲点 | action |
| 合 | 阶段性结果落地，同时抛出下一章钩子 | suspense |

### 7.5 单节拍提示词（build_beat_prompt）

```
【节拍 N/M】
目标字数：{target_words} 字（软目标：以完成义务为主，勿用废话硬凑）
聚焦点：{focus}

{focus_instruction}   ← 根据聚焦点注入的详细指导

节拍内容：
{beat.description}

密度与可检查要求：
- {anchor_line}       ← 感官轮转：光影/温度/声音/气味
- {obligation}        ← 叙事义务：对话3轮/悬念点/目标阻碍反应

注意：
- 这是完整章节的一部分，不要写章节标题
- 不要在节拍结尾强行总结全章
- 专注于当前节拍的内容，自然衔接到下一节拍
```

**聚焦点指导映射**：

| 聚焦点 | 指导内容 |
|--------|---------|
| sensory | 重点描写感官细节：视觉、听觉、触觉、嗅觉、味觉 |
| dialogue | 重点描写对话：语气、表情、肢体语言、潜台词 |
| action | 重点描写动作：力度、速度、节奏，避免抽象描述 |
| emotion | 重点描写情绪：内心独白、情绪起伏、回忆闪回 |
| hook | 开篇黄金法则：必须包含情感冲击点 |
| character_intro | 通过动作或对话展现人物，不要平铺直叙 |
| suspense | 留下剧情钩子，不要一次性抖露答案 |

**感官轮转**（每节拍自动轮换）：

```
节拍0: 至少一处环境锚点：光影或空间层次
节拍1: 至少一处环境锚点：温度、体感或材质
节拍2: 至少一处环境锚点：声音或节奏
节拍3: 至少一处环境锚点：气味或味觉细节
```

---

## 八、节拍续写逻辑（beat_continuation）

### 8.1 已写正文注入

同章多节拍续写时，将已生成正文注入后续节拍的 user prompt：

```python
_MAX_PRIOR_DRAFT_CHARS = 14_000  # 上限，避免撑爆上下文

def format_prior_draft_for_prompt(chapter_draft_so_far: str) -> str:
    if len(raw) <= _MAX_PRIOR_DRAFT_CHARS:
        return raw  # 完整保留
    # 超长时保留尾部（离当前节拍最近）
    tail = raw[-_MAX_PRIOR_DRAFT_CHARS:]
    omitted = len(raw) - _MAX_PRIOR_DRAFT_CHARS
    return f"…（已省略本章前段约 {omitted} 字，以下从更近情节接续）\n{tail}"
```

### 8.2 节拍级幂等落库

```python
for i, beat in enumerate(beats):
    if i < start_beat:  # 跳过已生成的节拍（断点续写）
        continue

    # 生成当前节拍
    beat_content = await _stream_llm_with_stop_watch(prompt, config, novel=novel)

    # 立即落库（幂等）
    chapter_content += ("\n\n" if chapter_content else "") + beat_content
    await _upsert_chapter_content(novel, chapter_node, chapter_content, status="draft")

    # 记录断点
    novel.current_beat_index = i + 1
    _flush_novel(novel)
```

---

## 九、阶段四：审计（AUDITING）

### 9.1 流程

```
_handle_auditing(novel)
    │
    ├─ 1. 文风预检 _score_voice_only()
    │      └─ 仅做文风评分，不执行章后管线
    ├─ 2. 定向修文循环 _apply_voice_rewrite_loop()
    │      ├─ 相似度 < 0.68 → 触发修文
    │      ├─ 最多 VOICE_REWRITE_MAX_ATTEMPTS 轮
    │      ├─ 每轮：构建修文提示词 → LLM 改写 → 复评
    │      └─ 修文后仍偏离 → 保留本章继续推进（不再删章回滚）
    ├─ 3. 统一章后管线 ChapterAftermathPipeline.run_after_chapter_saved()
    │      ├─ 叙事同步（摘要/事件/埋线/三元组/伏笔 → 向量索引）
    │      ├─ 文风评分（落库 chapter_style_scores）
    │      └─ 知识图谱推断
    ├─ 4. 张力打分 _score_tension()
    │      └─ LLM 打分 1-10，用于判断是否插入缓冲章
    ├─ 5. 章末审阅快照（写入 novels 表）
    ├─ 6. 全书完成检测
    ├─ 7. 自动触发宏观诊断
    └─ 8. 摘要生成钩子
```

### 9.2 文风定向修文提示词

当文风相似度低于阈值（0.68）时，构建专门的修文提示词：

**System Prompt**:
```
你是小说文风修订编辑。你的任务不是重写剧情，而是在不改变故事事实的前提下，
修正文风偏移。

必须遵守：
1. 保留所有剧情事件、因果顺序、角色关系、伏笔信息
2. 保留章节的主要段落结构、对话功能与情绪走向
3. 只调整叙述口吻、句式节奏、措辞密度、描写轻重
4. 输出只能是修订后的完整章节正文

风格约束：
{style_summary}

角色声线锚点：
{voice_anchors}
```

**User Prompt**:
```
当前为第 {chapter_number} 章，第 {attempt} 次文风定向修正。

当前相似度：{similarity_score:.4f}
自动修文触发阈值：{VOICE_REWRITE_THRESHOLD:.2f}

章节大纲：
{outline}

请在不改变剧情事实的前提下，修订以下正文的叙述语气、句式节奏与措辞：
{content}
```

**修文参数**：
- `temperature=0.35`（低创造性，保持忠实）
- `max_tokens=max(4096, min(8192, int(len(content) * 1.5)))`

### 9.3 张力打分提示词

```python
Prompt(
    system="你是小说节奏分析师，只输出一个 1-10 的整数，不要解释。",
    user=f"""根据以下章节开头，打分当前剧情的张力值（1=日常/轻松，10=生死对决/高潮）：

{snippet}  # 只取前 500 字

张力分（只输出数字）："""
)
```

参数：`max_tokens=5, temperature=0.1`

### 9.4 章后管线（ChapterAftermathPipeline）

```
run_after_chapter_saved(novel_id, chapter_number, content)
    │
    ├─ 1. 叙事同步 sync_chapter_narrative_after_save()
    │      ├─ LLM 产出：摘要/事件/埋线 + 三元组 + 伏笔
    │      ├─ → StoryKnowledge + triples + ForeshadowingRegistry
    │      └─ → 向量索引（chapter_narrative_sync）
    ├─ 2. 文风评分
    │      ├─ LLM 模式 → score_chapter_async()
    │      └─ 统计模式 → score_chapter()
    │      → 写入 chapter_style_scores
    └─ 3. 知识图谱推断 infer_kg_from_chapter()
           └─ 结构树章节节点 → 增量三元组推断
```

### 9.5 后处理（post_process_generated_chapter）

```
post_process_generated_chapter(novel_id, chapter_number, outline, content)
    │
    ├─ 1. 俗套扫描 _scan_cliches(content)
    ├─ 2. 状态提取 _extract_chapter_state(content, chapter_number)
    │      └─ LLM 提取 9 维领域状态（ChapterState）
    ├─ 3. 一致性检查 _check_consistency(chapter_state, novel_id)
    │      └─ 从 Bible/Foreshadowing 加载真实数据
    ├─ 4. 冲突检测 _detect_conflicts()
    │      └─ 生成 GhostAnnotation（幽灵批注）
    ├─ 5. StateUpdater.update_from_chapter()
    │      └─ 更新 Bible/Foreshadowing/Timeline
    └─ 6. MemoryEngine.update_from_chapter()  ← V6 新增
           ├─ LLM 提取记忆增量（MemoryDeltaPayload）
           ├─ 去重累积 completed_beats
           ├─ 追踪 revealed_clues 有效性
           └─ 检测 fact_violations
```

---

## 十、辅助流程

### 10.1 缓冲章策略

当上一章张力 ≥ 8 时，插入缓冲章（日常/过渡），避免读者疲劳：

```python
needs_buffer = (novel.last_chapter_tension or 0) >= 8
if needs_buffer:
    # 在大纲前追加缓冲章提示
    buffer_prefix = "【缓冲章】上一章经历了高强度冲突，本章节奏放缓..."
```

### 10.2 宏观诊断自动触发

触发条件（满足任一）：
1. 任一卷（Volume）章节范围完结
2. 累计字数距上次诊断 ≥ 6 万字

诊断结果写入 `context_patch`，供生成上下文头部静默注入，不经前端提案交互。

### 10.3 摘要生成钩子

| 类型 | 触发时机 |
|------|---------|
| 检查点摘要 | 每 20 章 |
| 幕摘要 | 幕完成时 |
| 卷摘要 | 卷完成时 |
| 部摘要 | 部完成时 |

### 10.4 流式推送

守护进程通过 `streaming_bus` 实时推送增量文字，供 SSE 接口消费：

```python
async def _push_streaming_chunk(self, novel_id: str, chunk: str):
    streaming_bus.publish(novel_id, chunk)
```

同时并行轮询 DB 检查停止信号（每 0.35 秒），用户点停止后立即中断流式生成。

---

## 十一、熔断与容错

### 11.1 单本熔断

```
连续失败 3 次 → novel.autopilot_status = ERROR（挂起等待急救）
不影响其他小说
```

### 11.2 全局熔断器

```
CircuitBreaker:
  - 连续失败达到阈值 → 打开熔断器
  - 打开期间暂停所有轮询
  - 等待冷却后进入半开状态试探
```

### 11.3 各阶段降级策略

| 阶段 | 降级策略 |
|------|---------|
| 宏观规划 | `build_minimal_macro_structure()` 最小骨架 |
| 幕级规划 | `_fallback_act_chapters_plan()` 占位章节 |
| 上下文构建 | `build_fallback_chapter_bundle()` 各子步骤独立容错 |
| 节拍生成 | 无节拍时一次生成整章 |
| 章后管线 | `_legacy_auditing_tasks_and_voice()` 旧逻辑降级 |
| 文风修文 | 修文失败则保留原文继续推进 |

---

## 十二、关键文件索引

| 文件 | 职责 |
|------|------|
| [autopilot_daemon.py](file:///f:/WORKSPACE/PlotPilot/application/engine/services/autopilot_daemon.py) | 守护进程主循环 + 状态机 + 所有 handler |
| [auto_novel_generation_workflow.py](file:///f:/WORKSPACE/PlotPilot/application/workflows/auto_novel_generation_workflow.py) | 章节生成工作流 + `_build_prompt()` |
| [context_builder.py](file:///f:/WORKSPACE/PlotPilot/application/engine/services/context_builder.py) | 上下文构建器 + 节拍放大器 |
| [context_budget_allocator.py](file:///f:/WORKSPACE/PlotPilot/application/engine/services/context_budget_allocator.py) | 洋葱模型预算分配 |
| [memory_engine.py](file:///f:/WORKSPACE/PlotPilot/application/engine/services/memory_engine.py) | V6 记忆引擎（FACT_LOCK/BEATS/CLUES） |
| [continuous_planning_service.py](file:///f:/WORKSPACE/PlotPilot/application/blueprint/services/continuous_planning_service.py) | 宏观规划 + 幕级规划 + AI 续规划 |
| [chapter_aftermath_pipeline.py](file:///f:/WORKSPACE/PlotPilot/application/engine/services/chapter_aftermath_pipeline.py) | 章后管线（叙事同步/文风/KG） |
| [beat_continuation.py](file:///f:/WORKSPACE/PlotPilot/application/workflows/beat_continuation.py) | 节拍续写（已写正文注入） |
| [style_constraint_builder.py](file:///f:/WORKSPACE/PlotPilot/application/engine/services/style_constraint_builder.py) | 风格约束构建 |
| [circuit_breaker.py](file:///f:/WORKSPACE/PlotPilot/application/engine/services/circuit_breaker.py) | 熔断器 |

---

## 十三、完整流程时序图

```
用户点击「开始托管」
    │
    ▼
[MACRO_PLANNING]
    │ generate_macro_plan() → LLM
    │ apply_macro_plan_from_llm_result() → DB
    ▼
[PAUSED_FOR_REVIEW] ← 半自动模式等待用户确认
    │                    全自动模式直接跳过
    ▼
[ACT_PLANNING]
    │ plan_act_chapters() → LLM
    │ confirm_act_planning() → DB
    ▼
[PAUSED_FOR_REVIEW] ← 半自动模式等待用户确认
    │                    全自动模式直接跳过
    ▼
[WRITING] ←──────────────────────────────────┐
    │ prepare_chapter_generation()            │
    │   ├─ storyline_context                  │
    │   ├─ plot_tension                       │
    │   ├─ build_structured_context()         │
    │   │   └─ ContextBudgetAllocator         │
    │   │       ├─ T0: FACT_LOCK/BEATS/CLUES  │
    │   │       ├─ T0: 伏笔/角色/幕摘要       │
    │   │       ├─ T1: 图谱/近期幕            │
    │   │       ├─ T2: 最近章节               │
    │   │       └─ T3: 向量召回               │
    │   ├─ style_summary                      │
    │   └─ voice_anchors                      │
    │                                         │
    │ magnify_outline_to_beats()              │
    │   └─ 拆分为 3-5 个微观节拍              │
    │                                         │
    │ for each beat:                          │
    │   ├─ _build_prompt() → Prompt           │
    │   ├─ LLM stream_generate()              │
    │   ├─ 增量落库 (draft)                   │
    │   └─ 断点记录 current_beat_index        │
    │                                         │
    │ post_process_generated_chapter()         │
    │   ├─ 俗套扫描                           │
    │   ├─ 状态提取 (LLM)                     │
    │   ├─ 一致性检查                          │
    │   ├─ 冲突检测                            │
    │   ├─ StateUpdater                       │
    │   └─ MemoryEngine.update_from_chapter() │
    │       └─ LLM 提取记忆增量 → DB          │
    │                                         │
    │ 标记章节 completed                       │
    ▼                                         │
[AUDITING]                                    │
    │ 文风预检 + 定向修文循环                   │
    │ ChapterAftermathPipeline                 │
    │   ├─ 叙事同步 → 向量索引                 │
    │   ├─ 文风评分 → DB                      │
    │   └─ KG 推断                            │
    │ 张力打分 (LLM)                           │
    │ 宏观诊断（条件触发）                      │
    │ 摘要生成（条件触发）                      │
    │                                         │
    │ 全书完成？                               │
    │   ├─ 是 → COMPLETED                     │
    │   └─ 否 → WRITING（下一章）─────────────┘
```

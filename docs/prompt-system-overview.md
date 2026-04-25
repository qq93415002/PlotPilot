# PlotPilot 提示词系统全景文档

> 生成日期：2026-04-24  
> 版本：基于 prompts_defaults.json v2.0.0-anti-ai-v1

---

## 一、系统架构总览

PlotPilot 的提示词系统采用 **数据库驱动 + 种子初始化 + 运行时动态组装** 的三层架构：

```
┌─────────────────────────────────────────────────────────────┐
│                    API 层 (FastAPI)                          │
│         interfaces/api/v1/workbench/llm_control.py          │
│         → CRUD / 版本管理 / 渲染 / 统计                      │
├─────────────────────────────────────────────────────────────┤
│                  管理服务层 (PromptManager)                    │
│         infrastructure/ai/prompt_manager.py                  │
│         → 种子初始化 / 版本管理 / 模板渲染 / SafeDict          │
├─────────────────────────────────────────────────────────────┤
│              运行时动态组装层 (各业务 Service)                  │
│         auto_novel_generation_workflow._build_prompt()       │
│         context_builder / budget_allocator / theme_agent     │
│         → 上下文注入 / 题材增强 / 记忆引擎 / 声线锚点          │
├─────────────────────────────────────────────────────────────┤
│                 持久化层 (SQLite)                             │
│         prompt_templates / prompt_nodes / prompt_versions    │
│         + prompts_defaults.json 种子文件                      │
└─────────────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **提示词存入数据库**：所有提示词节点和版本历史持久化到 SQLite
2. **单节点版本管理**：每次编辑创建新版本，支持回滚（不删除历史）
3. **模板包组合**：template 包含多个 node，可组合成工作流
4. **内置种子幂等初始化**：首次启动从 `prompts_defaults.json` 导入，已存在则跳过
5. **`{variable}` 占位符渲染**：使用 SafeDict，缺失变量保留原样不抛异常

---

## 二、数据模型

### 2.1 数据库表结构

三张表形成一对多层级关系：

```
prompt_templates (1) ──→ (N) prompt_nodes (1) ──→ (N) prompt_versions
```

#### `prompt_templates` — 模板包

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| name | TEXT NOT NULL | 名称 |
| description | TEXT | 描述 |
| category | TEXT DEFAULT 'user' | builtin / user / workflow |
| version | TEXT DEFAULT '1.0.0' | 语义化版本号 |
| author | TEXT | 作者 |
| icon | TEXT DEFAULT '📦' | 图标 emoji |
| color | TEXT DEFAULT '#6b7280' | 主题色 |
| is_builtin | INTEGER NOT NULL DEFAULT 0 | 是否内置 |
| metadata | TEXT DEFAULT '{}' | JSON 扩展字段 |
| created_at / updated_at | TIMESTAMP | 时间戳 |

#### `prompt_nodes` — 提示词节点

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| template_id | TEXT FK → templates | 所属模板包 |
| node_key | TEXT UNIQUE | 唯一标识，如 `chapter-generation-main` |
| name / description | TEXT | 名称/描述 |
| category | TEXT | generation/extraction/review/planning/world/creative |
| source | TEXT | 来源代码位置 |
| output_format | TEXT | text / json |
| contract_module / contract_model | TEXT | Pydantic 合约引用 |
| tags | TEXT JSON | 标签数组 |
| variables | TEXT JSON | 变量定义数组 |
| system_file | TEXT | 引用的 .txt 系统文件名 |
| is_builtin | INTEGER | 是否内置 |
| sort_order | INTEGER | 排序权重 |
| active_version_id | TEXT FK → versions | 当前激活版本 ID |

#### `prompt_versions` — 版本历史

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| node_id | TEXT FK → nodes | 所属节点 |
| version_number | INTEGER | 版本号（自增） |
| system_prompt | TEXT | System 角色提示词 |
| user_template | TEXT | User 模板 |
| change_summary | TEXT | 变更说明 |
| created_by | TEXT | system / user |
| created_at | TIMESTAMP | 创建时间 |

**约束**: `(node_id, version_number)` 唯一

### 2.2 种子数据文件

路径：`infrastructure/ai/prompts/prompts_defaults.json`

```json
{
  "_meta": {
    "version": "2.0.0-anti-ai-v1",
    "description": "PlotPilot 提示词库 v2 - 反AI风/爽文沉浸式/上下文强一致性重写版",
    "engine": "jinja2"
  },
  "categories": [...],
  "prompts": [...]
}
```

首次启动时由 `PromptManager.ensure_seeded()` 自动导入。已存在则跳过。

### 2.3 内置分类定义

| Key | 名称 | 图标 | 说明 | 颜色 |
|-----|------|------|------|------|
| generation | 📝 内容生成 | ✍️ | 章节正文、场景、对白等创作 | #4f46e5 |
| extraction | 🔍 信息提取 | 🔎 | 结构化信息分析 | #0891b2 |
| review | ✅ 审稿质检 | 🔬 | 一致性检查、质量评估 | #b45309 |
| planning | 📐 规划设计 | 📋 | 大纲拆解、节拍表、摘要、宏观规划 | #6d28d9 |
| world | 🌍 世界设定 | 🏰 | Bible 人物、地点、文风生成 | #15803d |
| creative | 🎭 创意辅助 | 💡 | 对白润色、重构提案、卡文诊断 | #be185d |

---

## 三、PromptManager 核心服务

**文件**：`infrastructure/ai/prompt_manager.py`  
**单例获取**：`get_prompt_manager()`

### 3.1 核心 API

| 方法 | 说明 |
|------|------|
| `ensure_seeded()` | 从 prompts_defaults.json 初始化内置种子（幂等） |
| `list_nodes(category, template_id)` | 查询节点列表（支持分类/模板过滤） |
| `get_node(node_key_or_id)` | 单个节点详情（含激活版本） |
| `search_nodes(query)` | 全文搜索（name/description/tags/source/node_key） |
| `create_node(template_id, node_key, name, ...)` | 创建自定义节点（自动 v1） |
| `update_node(node_id, system_prompt, user_template, ...)` | 编辑内容 → 自动创建新版本 |
| `rollback_node(node_id, target_version_id)` | 回滚到指定历史版本（创建回滚快照） |
| `get_node_versions(node_id)` | 版本时间线 |
| `compare_versions(version_id_1, version_id_2)` | 双版本对比 |
| `render(node_key, variables)` | `{variable}` 模板渲染 |
| `get_stats()` | 统计信息 |
| `get_categories_info()` | 分类定义（含计数） |

### 3.2 版本管理机制

**回滚快照模式**（不删除历史）：

```
初始状态:  v1 (系统种子)
              ↓ 用户第一次编辑
          v2 (用户修改, change_summary="优化了角色描写")
              ↓ 用户第二次编辑
          v3 (用户修改, change_summary="调整了节奏")
              ↓ 用户觉得 v2 更好, 点击回滚
          v4 (回滚快照, change_summary="回滚到 v2")
              ↓ ...
```

- 回滚本身也是一个新版本（vN+1），内容复制自目标版本
- 可以无限次来回回滚
- 时间线始终完整可追溯

### 3.3 渲染引擎

**变量语法**：Python `str.format_map()` 兼容的 `{variable}` 语法

**SafeDict 安全特性**：
- 缺失变量保留原样 `{undefined_var}` 而非抛异常
- 纯字符串替换，无 eval / exec
- 变量定义中标注 type 和 required

```python
result = mgr.render("chapter-generation-main", {
    "chapter_number": 42,
    "title": "暗夜重逢",
    "genre": "玄幻"
})
# => {"system": "你是一个玄幻小说家...", "user": "请生成第42章..."}
```

---

## 四、内置提示词清单（prompts_defaults.json）

### 4.1 内容生成类 (generation)

#### ① `chapter-generation-main` — 主工作流章节生成 v6

- **来源**：`application/workflows/auto_novel_generation_workflow.py::_build_prompt()`
- **描述**：v6: 在v5基础上新增记忆引擎，解决长文本生成的三大状态机崩溃问题——人设漂移、设定矛盾、剧情重复。引入FACT_LOCK不可篡改事实块、COMPLETED_BEATS节拍锁、REVEALED_CLUES累积线索清单。
- **标签**：核心, v6, 反AI风, 高字数, 去套路, 记忆引擎
- **System 核心要点**：
  - 叙述者身份定位："你不是AI，你就是那个坐在老街边上的说书人"
  - 17条叙述铁律：开头从动作/画面开始、对话必须有弦外之音、禁止情绪副词、环境是角色心理滤镜、短句就是刀、冲突不能软、字数硬指标、第三人称限制视角、章节衔接像电影转场、每个场景至少承载两件事、禁止上帝视角心理分析、字数爆破要求、杀死套路比喻、严格禁绝私自创造角色、角色外貌/穿着/职业必须与Bible一致、冲突场景必须慢写、前章拉升+大纲锁定+比喻终极封杀
- **变量**：

| 变量名 | 说明 | 类型 | 必填 |
|--------|------|------|------|
| context | 完整上下文（Bible摘要+前情提要） | string | ✅ |
| outline | 本章大纲 | string | ✅ |
| planning_section | 故事线/张力/风格约束块 | string | ❌ |
| voice_block | 角色声线锚点 | string | ❌ |
| length_rule | 字数规则 | string | ❌ (默认3200-4200字) |
| beat_extra | 节拍模式附加说明 | string | ❌ |
| beat_section | 当前节拍指令 | string | ❌ |
| fact_lock | V6 记忆引擎组合文本块 | string | ❌ |

- **User 模板核心指令**：
  - 别平均使力，冲突爆发多写，过渡一笔带过
  - 场景里的人不能是纸片人
  - 结尾别收干净，留一根刺
  - 每个场景双线并行（表面事件+底层暗流）
  - 接住上一章角色状态再展开新情节

#### ② `chapter-generation-basic` — 基础章节生成

- **来源**：`application/engine/services/ai_generation_service.py::_build_chapter_prompt()`
- **描述**：引擎层的基础章节生成，注入 Bible 人物和世界设定
- **System**：你是长篇小说《{novel_title}》的创作者。将宏大世界设定编织进日常/战斗描写中
- **变量**：novel_title, chapter_number, outline, characters_section, world_settings_section

#### ③ `scene-generation` — 场景正文生成 v2

- **来源**：`application/core/services/scene_generation_service.py::_build_scene_prompt()`
- **描述**：基于MRU理论的场景构建，消除"剧本说明书"感
- **System 核心要点**：
  - "你不是在'描写一个场景'。你是一台架在{pov_character}肩上的摄像机"
  - 只能拍到POV角色能看到/听到的东西
  - 场景是一个变化的过程
- **变量**：title, goal, pov_character, location, tone, estimated_words, analysis_block, previous_scenes_block, foreshadowing_block

#### ④ `autopilot-stream-beat` — 自动驾驶·节拍流式写作 v3

- **来源**：`docs/plans/2026-04-05-autopilot-fullstack.md`
- **描述**：v3: 增加章节衔接约束、双线并行要求、反心理描写
- **System 核心要点**：
  - "你写过一千万字的商业小说"
  - 信息密度要高但不是堆砌
  - 爽点要有实感
  - 节奏快时句子就短
  - 再快也不能丢五感
  - 别写标题/别总结/别解释
- **变量**：voice_block, context, outline, beats

---

### 4.2 信息提取类 (extraction)

#### ⑤ `scene-director-analysis` — 场记分析

- **来源**：`application/engine/services/scene_director_service.py`
- **描述**：从编剧大纲中拆解拍戏所需的客观物理元素
- **输出格式**：JSON
- **System**：你是剧组的第一副导演（场记），输出单一JSON
- **JSON 键**：characters, locations, action_types, trigger_keywords, emotional_state, pov, performance_notes
- **变量**：outline

#### ⑥ `chapter-state-extraction` — 章节状态提取（9维度）

- **来源**：`application/ai/chapter_state_llm_contract.py::_CHAPTER_STATE_SYSTEM`
- **描述**：从文学分析师视角提取9维度结构化信息
- **输出格式**：JSON
- **合约**：`ChapterStateLlmPayload` (Pydantic, extra=forbid)
- **9个维度**：
  1. new_characters — 新出现的角色
  2. character_actions — 角色行为
  3. relationship_changes — 关系变化
  4. foreshadowing_planted — 埋下的伏笔
  5. foreshadowing_resolved — 解决的伏笔
  6. events — 事件
  7. timeline_events — 时间线事件（含 timestamp_type: absolute/relative/vague）
  8. advanced_storylines — 推进的已有故事线
  9. new_storylines — 引入的新故事线
- **变量**：章节内容（通过 user prompt 传入）

#### ⑦ `chapter-summarizer` — Claude 章节摘要

- **来源**：`infrastructure/ai/claude_chapter_summarizer.py::summarize()`
- **描述**：高效提炼干货情节，去水留金
- **System**：英文 prompt，"ruthlessly efficient editorial assistant"
- **变量**：content, max_length (默认300)

---

### 4.3 审稿质检类 (review)

#### ⑧ `review-character-consistency` — 人物一致性检查 v2

- **来源**：`application/audit/services/chapter_review_service.py::_build_character_consistency_prompt()`
- **描述**：v2：不仅查OOC，还查AI模板化表达、情绪副词滥用、套路化动作
- **System 核心要点**：
  - "你是最苛刻的审稿人。你手里有两把刀"
  - 第一把刀：OOC检测（人设崩塌）
  - 第二把刀：AI味检测（模板化表达）
- **输出格式**：JSON，inconsistencies 数组（type: OOC/AI-flavor/narrative, severity: critical/warning/suggestion）
- **变量**：character_name, character_profile, chapter_content

#### ⑨ `review-timeline-consistency` — 时间线一致性检查

- **来源**：`application/audit/services/chapter_review_service.py::_build_timeline_consistency_prompt()`
- **描述**：时间穿帮纠错，审查物理空间与时间的硬伤
- **System**：你是小说的逻辑质检员（Continuity Editor）
- **输出格式**：JSON，conflicts 数组
- **变量**：current_events, previous_events, chapter_content

#### ⑩ `review-storyline-consistency` — 故事线连贯性检查

- **来源**：`application/audit/services/chapter_review_service.py::_build_storyline_consistency_prompt()`
- **描述**：避免挖坑不填和主线偏移
- **System**：你是长篇架构审核员
- **输出格式**：JSON，gaps 数组
- **变量**：active_storylines, chapter_content

#### ⑪ `review-foreshadowing-usage` — 伏笔使用检查

- **来源**：`application/audit/services/chapter_review_service.py::_build_foreshadowing_usage_prompt()`
- **描述**：检查并促成"契诃夫的枪"在最佳时机开火
- **System**：你是伏笔追踪大师（契诃夫的猎场看守）
- **输出格式**：JSON，missed_opportunities 数组
- **变量**：foreshadowings, chapter_content

#### ⑫ `review-improvement-suggestions` — 改进建议生成

- **来源**：`application/audit/services/chapter_review_service.py::_build_improvement_suggestions_prompt()`
- **描述**：整合体检报告，提供动作导向的手术刀式修改意见
- **System**：你是金牌小说医生（Script Doctor）
- **输出格式**：JSON，suggestions 数组
- **变量**：chapter_number, chapter_title, issues_list

#### ⑬ `refactor-proposal` — 重构提案

- **来源**：`application/audit/services/macro_refactor_proposal_service.py::_build_prompt()`
- **描述**：规避"机械降神"，提供符合角色主观能动性的宏观重构计划
- **输出格式**：JSON
- **System**：你是宏观剧本重构专家
- **JSON 字段**：natural_language_suggestion, suggested_mutations (add_tag/remove_tag/replace_tag), suggested_tags, reasoning
- **变量**：author_intent, current_event_summary, current_tags, event_id

---

### 4.4 规划设计类 (planning)

#### ⑭ `beat-sheet-decomposition` — 节拍表拆解

- **来源**：`application/blueprint/services/beat_sheet_service.py::_build_beat_sheet_prompt()`
- **描述**：将章纲拆解为实战可写的场景/续场 (Scene & Sequel) 结构
- **输出格式**：JSON
- **合约**：`BeatSheetLlmPayload`
- **System**：你是深谙"场景与续场（Scene & Sequel）"节奏的剧本拆解师
- **切分铁律**：Scene（行动场）含目标+冲突+灾难性后果；Sequel（反应场）含情绪反应+两难抉择+新目标
- **变量**：outline, characters_block, storylines_block, previous_chapter_block, foreshadowings_block, locations_block, timeline_block

#### ⑮ `planning-quick-macro` — 极速宏观规划·破城槌

- **来源**：`PlotPilot-master prompts_defaults.json`
- **描述**：狂热主编风格，基于英雄之旅与救猫咪理论强推商业网文骨架
- **System**：狂热白金级主编身份
- **商业骨架铁律**：结构锚点（建置→游戏/试炼→一无所有→涅槃对决）、矛盾前置、战力/位阶升维、爽感闭环
- **变量**：premise, target_chapters, worldview, characters, depth_instruction

#### ⑯ `planning-act` — 幕级章节规划

- **来源**：`application/blueprint/services/continuous_planning_service.py::_build_act_planning_prompt()`
- **描述**：将抽象的幕大纲落地为充满递进张力的章纲序列
- **输出格式**：JSON
- **System**：你是精密的故事工程师
- **变量**：context, chapter_count

#### ⑰ `planning-main-plot-suggest` — 主线故事选项推演

- **来源**：`PlotPilot-master prompts_defaults.json`
- **描述**：推演3个高概念主线变体，确保切入点犀利、商业张力拉满
- **输出格式**：JSON
- **System**：顶级IP推手身份
- **高概念法则**：A-绝地反杀、B-黑箱博弈、C-规则毒药
- **变量**：worldview, protagonist, locations

#### ⑱ `summary-act` — 幕（Act）摘要

- **来源**：`PlotPilot-master prompts_defaults.json`
- **描述**：存档点快照，精准捕获主角当前的筹码、困境与枪口指向
- **System**：你是小说的战术雷达
- **输出结构**：手牌（筹码/新能力）、刀锋（最近危机）、短期箭头（下一步行动）
- **变量**：current_chapter, chapters_text

---

### 4.5 世界设定类 (world)

#### ⑲ `bible-all` — 完整 Bible 生成

- **来源**：`PlotPilot-master prompts_defaults.json`
- **描述**：一键构建具备内生矛盾与自驱力的五维度世界体系与人物群像
- **输出格式**：JSON
- **合约**：`BibleAllLlmPayload`
- **System**：拥有造物主思维的网文世界架构师
- **构建法则**：人物阵列(3-5人，必须有欲望+致命弱点)、空间折叠(2-3处)、文风公约、五维度底层规则
- **变量**：premise, genre

#### ⑳ `bible-worldbuilding` — 世界观与文风生成

- **来源**：`PlotPilot-master prompts_defaults.json`
- **描述**：生成避免悬浮感、具有厚重社会生态的5维度世界观体系
- **输出格式**：JSON
- **System**：好莱坞科幻/奇幻概念设计师
- **5维度框架**：core_rules(力量逻辑+代价)、geography(地缘环境)、society(阶级结构)、culture(信仰禁忌)、daily_life(沉浸感基石)
- **变量**：premise, existing_settings

#### ㉑ `bible-characters` — 人物生成

- **来源**：`PlotPilot-master prompts_defaults.json`
- **描述**：根据社会生态孵化具有内源性冲突和错综羁绊的立体人物
- **输出格式**：JSON
- **System**：顶级卡司导演（Casting Director）
- **人物塑造三角**：根(阶层)、骨(隐秘恐惧+执念)、网(宿敌/羁绊)
- **变量**：worldbuilding, style_guide, existing_characters

#### ㉒ `bible-locations` — 地点地图生成

- **来源**：`PlotPilot-master prompts_defaults.json`
- **描述**：构建具有叙事功能的地缘拓扑网络
- **输出格式**：JSON
- **System**：关卡设计师（Level Designer）
- **地图构建准则**：叙事功能性、空间嵌套逻辑(parent_id)、通路关系(relations)
- **变量**：worldbuilding, existing_locations, character_context

---

### 4.6 创意辅助类 (creative)

#### ㉓ `dialogue-generation` — 角色对白生成 v2

- **来源**：`application/workbench/services/sandbox_dialogue_service.py::build_dialogue_generation_prompt()`
- **描述**：v2重写：真实人类不会直说想法。每句台词都是一次博弈、试探或伪装。
- **System 核心要点**：
  - "现实中两个人对话，90%的信息不在台词里"
  - 写出角色会说的话+下意识做的动作
- **变量**：character_name, description, public_profile, mental_state, verbal_tic, idle_behavior, relationship_block, related_block, history_block, scene_text

#### ㉔ `tension-analysis-diagnosis` — 卡文诊断与张力分析

- **来源**：`PlotPilot-master prompts_defaults.json`
- **描述**：结合统计数据诊断卡文病因，提供"鲶鱼效应"重构方案
- **输出格式**：JSON
- **System**：拯救卡文的剧作结构大师
- **输出结构**：冰冷解剖(统计数据+病因)、鲶鱼效应建议(动词导向破局手段)
- **变量**：novel_id, chapter_number, stuck_reason_text, events_text, stats_text

---

## 五、运行时动态提示词组装

除了数据库中的模板化提示词，系统还有大量在运行时动态组装的提示词逻辑。

### 5.1 主工作流提示词组装

**文件**：`application/workflows/auto_novel_generation_workflow.py::_build_prompt()`

这是最核心的提示词组装逻辑，将多个子系统注入到最终 Prompt 中：

```
System Message 组装流程：
┌──────────────────────────────────────────┐
│ 基础身份："你是一位专业的网络小说作家"        │
│                                          │
│ + planning_section (故事线/张力/风格约束)   │
│   ├── 【故事线 / 里程碑】                  │
│   ├── 【情节节奏 / 期望张力】               │
│   └── 【风格约束】                         │
│                                          │
│ + voice_block (角色声线与肢体语言锚点)      │
│   └── Bible 角色声线/小动作锚点             │
│                                          │
│ + context (三层上下文)                     │
│   ├── Layer1: T0+T1 核心上下文             │
│   ├── Layer2: T2 近期章节正文              │
│   └── Layer3: T3 向量召回                  │
│                                          │
│ + fact_lock (V6 记忆引擎)                  │
│   ├── FACT_LOCK 不可篡改事实块             │
│   ├── COMPLETED_BEATS 已完成节拍锁         │
│   └── REVEALED_CLUES 已揭露线索清单        │
│                                          │
│ + 写作要求（8条）                          │
│   1. 多人物互动                            │
│   2. 必须有对话                            │
│   3. 必须有冲突或张力                      │
│   4. 保持人物性格一致                      │
│   5. 推进情节发展                          │
│   6. 生动场景描写                          │
│   7. 字数规则（动态）                      │
│   8. 第三人称叙事                          │
└──────────────────────────────────────────┘

User Message 组装流程：
┌──────────────────────────────────────────┐
│ 基础指令："请根据以下大纲撰写本章内容"        │
│                                          │
│ + outline (章节大纲)                       │
│                                          │
│ + 关键要求（6条）                          │
│                                          │
│ + [节拍模式] 本章已生成正文（续写）          │
│                                          │
│ + [节拍模式] 节拍 N/M 指令                 │
└──────────────────────────────────────────┘
```

### 5.2 上下文预算分配器（洋葱模型）

**文件**：`application/engine/services/context_budget_allocator.py`

```
优先级层级（预算紧张时从 T3 → T2 → T1 逐层挤压，T0 绝对保护）：

T0_CRITICAL (绝对不删减)
  ├── 系统 Prompt
  ├── 当前幕摘要
  ├── 强制伏笔
  └── 角色锚点

T1_COMPRESSIBLE (按比例压缩)
  ├── 图谱子网
  └── 近期幕摘要

T2_DYNAMIC (动态水位线)
  └── 最近章节内容

T3_SACRIFICIAL (可牺牲泡沫)
  └── 向量召回片段

特殊注入：
  └── 🚨强制剧情收束令🚨（过期伏笔必须在本章推进）
```

### 5.3 V6 记忆引擎

**文件**：`application/engine/services/memory_engine.py`

解决长文本生成的三大状态崩溃问题：

| 组件 | 功能 | 注入位置 |
|------|------|----------|
| FACT_LOCK | 不可篡改事实块（角色白名单、死亡名单、关系图谱、身份锁、时间线） | T0-α |
| COMPLETED_BEATS | 已完成节拍锁（防止剧情鬼打墙/重复） | T0-β |
| REVEALED_CLUES | 已揭露线索清单（防止前后矛盾） | T0-γ |

**LLM 合约**：`MemoryDeltaPayload` (Pydantic, extra=forbid)
- completed_beats: 本章新完成的剧情节拍
- revealed_clues: 本章新向读者揭露的信息或真相

### 5.4 场景导演服务

**文件**：`application/engine/services/scene_director_service.py`

独立于 prompts_defaults.json 的硬编码提示词：

```python
SCENE_DIRECTOR_SYSTEM = """你是小说场记。根据给定章节大纲，只输出一个 JSON 对象，
键为：characters, locations, action_types, trigger_keywords, emotional_state, pov, performance_notes。..."""
```

### 5.5 风格约束构建器

**文件**：`application/engine/services/style_constraint_builder.py`

从 voice fingerprint 数据构建简洁风格摘要（≤1K tokens），注入 LLM prompt：

```
- 形容词密度：X.X%（保持简洁/适度修饰/丰富描写）
- 平均句长：XX字（保持短句/长短结合/偏好长句）
```

### 5.6 章节状态提取

**文件**：`application/ai/chapter_state_llm_contract.py`

硬编码的9维度提取 system prompt，与 `ChapterStateLlmPayload` Pydantic 合约同源维护。

### 5.7 初始知识图谱生成

**文件**：`application/ai/knowledge_llm_contract.py`

LLM 输出契约 + 提示词：
- `LlmInitialKnowledgePayload` (extra=forbid)
- 字段：premise_lock + facts (id/subject/predicate/object/note)
- 同时提供 OpenAI function tool 定义

### 5.8 张力评分

**文件**：`application/ai/tension_scoring_contract.py`

LLM 输出契约：
- `TensionScoringLlmPayload` (extra=ignore)
- 三维度评分：plot_tension / emotional_tension / pacing_tension (0-100)
- 三条依据：plot_justification / emotional_justification / pacing_justification
- composite_score 由服务端加权计算

### 5.9 LLM 文风分析

**文件**：`application/analyst/services/llm_voice_analysis_service.py`

两个独立 prompt：
1. `STYLE_ANALYSIS_PROMPT` — 单章风格分析（8维度：narrative_voice/dialogue_ratio/description_depth/emotional_intensity/pacing/sensory_richness/metaphor_usage/sentence_variety）
2. `BASELINE_PROMPT` — 基准风格提取（从多章节中提取平均风格+标准差）

### 5.10 张力评分服务

**文件**：`application/analyst/services/tension_scoring_service.py`

包含兜底模板 `_FALLBACK_TEMPLATE`（当 PromptManager/DB 不可用时使用），含前章张力参考。

---

## 六、题材 Agent 系统（Theme Agent）

### 6.1 架构

```
ThemeAgent (抽象接口)
├── get_system_persona()          → 人设/角色设定指导
├── get_writing_rules()           → 题材专项写作规则
├── get_context_directives()      → 世界观/氛围约束上下文 → 注入 T0 槽位
├── get_beat_templates()          → 题材专项节拍模板
├── get_buffer_chapter_template() → 缓冲章模板
├── get_audit_criteria()          → 题材专项审计规则
└── get_skills()                  → Skills 增强插槽

ThemeAgentRegistry (注册中心)
├── auto_discover()               → 自动注册内置题材
├── register(agent)               → 手动注册
└── get(genre_key)                → 按 genre 获取
```

### 6.2 ThemeDirectives 注入

`ThemeDirectives` 数据结构注入到 ContextBudgetAllocator 的 T0 槽位：

| 字段 | 说明 |
|------|------|
| world_rules | 世界观规则（如"修仙体系分九境"） |
| atmosphere | 氛围描写指令 |
| taboos | 禁忌清单 |
| tropes_to_use | 推荐使用的叙事套路 |
| tropes_to_avoid | 应避免的叙事套路 |

### 6.3 已注册题材 Agent

| Agent | genre_key | 说明 |
|-------|-----------|------|
| XuanhuanThemeAgent | xuanhuan | 玄幻/仙侠/修仙 |
| WuxiaThemeAgent | wuxia | 武侠 |
| XianxiaThemeAgent | xianxia | 仙侠 |
| FantasyThemeAgent | fantasy | 西幻 |
| ScifiThemeAgent | scifi | 科幻 |
| RomanceThemeAgent | romance | 言情 |
| SuspenseThemeAgent | suspense | 悬疑 |
| HistoryThemeAgent | history | 历史 |
| GameThemeAgent | game | 游戏 |
| DushiThemeAgent | dushi | 都市 |
| OtherThemeAgent | other | 其他 |

### 6.4 Skills 增强插槽

| Skill | 说明 |
|-------|------|
| BattleChoreographySkill | 战斗编排 |
| CultivationSystemSkill | 修炼体系 |
| DeductionLogicSkill | 推理逻辑 |
| EmotionPacingSkill | 情绪节奏 |
| CustomSkillWrapper | 自定义技能包装器 |

---

## 七、结构化 JSON 输出管线

**文件**：`application/ai/structured_json_pipeline.py`

所有需要 LLM 返回结构化 JSON 的服务共用此管线：

```
LLM 原始输出
  → 正则清洗（BOM/reasoning/markdown围栏）
  → json_repair 修复
  → Pydantic schema 校验
  → 失败则重试（指数退避）
```

### 已注册的 Pydantic 合约

| 合约模型 | 文件 | 用途 |
|----------|------|------|
| ChapterStateLlmPayload | chapter_state_llm_contract.py | 9维度章节状态提取 |
| LlmInitialKnowledgePayload | knowledge_llm_contract.py | 初始知识图谱 |
| TensionScoringLlmPayload | tension_scoring_contract.py | 三维张力评分 |
| MemoryDeltaPayload | memory_engine.py | 记忆引擎增量状态 |
| BeatSheetLlmPayload | beat_sheet_llm_contract.py | 节拍表拆解 |
| BibleAllLlmPayload | bible_llm_contract.py | 完整Bible生成 |

---

## 八、API 接口

**基础路径**：`/api/v1/llm-control/prompts`

### 统计 & 分类

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stats` | 库统计（总节点数/版本数/各分类计数） |
| GET | `/categories-info` | 分类定义列表（含节点计数） |

### 模板包 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/templates` | 模板包列表 |
| POST | `/templates` | 创建自定义模板包 |

### 节点 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/prompts?category=&search=` | 节点列表（支持过滤） |
| GET | `/prompts/by-category` | 按分类分组 |
| GET | `/prompts/{node_key}` | 节点详情（含完整 system/user） |
| POST | `/prompts/nodes` | 创建自定义节点 |
| DELETE | `/prompts/nodes/{id}` | 删除自定义节点（内置不可删） |

### 版本管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/prompts/{key}/versions` | 版本时间线 |
| GET | `/prompts/versions/{ver_id}` | 版本详情 |
| PUT | `/prompts/{key}` | 更新（自动创建新版本） |
| POST | `/prompts/{key}/rollback/{ver_id}` | 回滚到指定版本 |
| GET | `/prompts/compare/{v1_id}/{v2_id}` | 双版本对比 |

---

## 九、提示词在业务流程中的完整流转

### 9.1 章节生成主流程

```
1. AutoNovelGenerationWorkflow.prepare_chapter_generation()
   ├── _get_storyline_context() → 故事线上下文
   ├── _get_plot_tension() → 情节弧张力
   ├── ContextBuilder.build_structured_context() → 三层上下文
   │   └── ContextBudgetAllocator.allocate() → 洋葱模型预算分配
   │       ├── T0: 伏笔/角色锚点/幕摘要/FACT_LOCK
   │       ├── T1: 图谱子网/近期幕摘要
   │       ├── T2: 最近章节正文
   │       └── T3: 向量召回
   ├── _get_style_summary() → 风格指纹摘要
   └── build_voice_anchor_system_section() → 角色声线锚点

2. _build_prompt() → 组装最终 Prompt
   ├── system: 身份 + planning + voice + context + fact_lock + 写作要求
   └── user: 大纲 + 关键要求 + [节拍续写]

3. LLMService.generate(prompt, config) → 生成内容

4. 后处理管线
   ├── strip_reasoning_artifacts() → 清洗
   ├── StateExtractor.extract_chapter_state() → 9维度状态提取
   ├── ConsistencyChecker.check() → 一致性检查
   ├── StateUpdater.update() → 状态更新
   └── MemoryEngine.update_from_chapter() → 记忆引擎回写
```

### 9.2 自动驾驶守护进程

```
AutopilotDaemon (死循环轮询)
  ├── poll → 捞出 autopilot_status=RUNNING 的小说
  ├── 状态机逻辑
  │   ├── PLANNING → ContinuousPlanningService (幕级规划)
  │   ├── GENERATING → AutoNovelGenerationWorkflow (章节生成)
  │   │   └── 节拍级幂等：每写完一个节拍立刻落库
  │   └── REVIEWING → ChapterAftermathPipeline (章后处理)
  └── 熔断保护：连续失败3次挂起单本小说
```

---

## 十、扩展指南

### 添加新的内置提示词

1. 编辑 `infrastructure/ai/prompts/prompts_defaults.json`
2. 在 `prompts` 数组中添加新条目（遵循现有格式）
3. 如果需要独立的 System 文件，创建 `.txt` 放在同目录并设置 `system_file`
4. 不需要迁移 — 删除数据库后重启即可重新 seed

### 在业务代码中使用提示词

```python
from infrastructure.ai.prompt_manager import get_prompt_manager

mgr = get_prompt_manager()
mgr.ensure_seeded()

result = mgr.render("chapter-generation-main", {
    "chapter_number": 10,
    "outline": "...",
    "context": "...",
})

messages = [
    {"role": "system", "content": result["system"]},
    {"role": "user", "content": result["user"]},
]
response = await llm_client.chat(messages)
```

### 添加新的题材 Agent

1. 在 `application/engine/theme/agents/` 下创建新文件
2. 继承 `ThemeAgent` 抽象类
3. 实现所需方法（get_system_persona / get_writing_rules / get_context_directives 等）
4. 在 `ThemeAgentRegistry.auto_discover()` 中注册

---

## 十一、关键文件索引

| 文件路径 | 职责 |
|----------|------|
| `infrastructure/ai/prompts/prompts_defaults.json` | 内置提示词种子数据（24个提示词） |
| `infrastructure/ai/prompt_manager.py` | 提示词管理器（CRUD/版本/渲染） |
| `domain/ai/value_objects/prompt.py` | Prompt 值对象（system + user → messages） |
| `application/workflows/auto_novel_generation_workflow.py` | 主工作流提示词组装 |
| `application/engine/services/context_builder.py` | 上下文构建器 |
| `application/engine/services/context_budget_allocator.py` | 上下文预算分配器（洋葱模型） |
| `application/engine/services/memory_engine.py` | V6 记忆引擎（FACT_LOCK/BEATS/CLUES） |
| `application/engine/services/scene_director_service.py` | 场景导演（硬编码 prompt） |
| `application/engine/services/style_constraint_builder.py` | 风格约束构建器 |
| `application/engine/theme/theme_agent.py` | 题材 Agent 抽象接口 |
| `application/engine/theme/theme_registry.py` | 题材注册中心 |
| `application/ai/chapter_state_llm_contract.py` | 章节状态提取合约 |
| `application/ai/knowledge_llm_contract.py` | 知识图谱合约 |
| `application/ai/tension_scoring_contract.py` | 张力评分合约 |
| `application/ai/structured_json_pipeline.py` | 结构化 JSON 输出管线 |
| `application/ai/llm_control_service.py` | LLM 控制面板服务 |
| `application/analyst/services/state_extractor.py` | 状态提取服务 |
| `application/analyst/services/tension_scoring_service.py` | 张力评分服务 |
| `application/analyst/services/llm_voice_analysis_service.py` | 文风分析服务 |
| `application/audit/services/chapter_review_service.py` | 章节审稿服务（5种检查） |
| `application/audit/services/macro_refactor_proposal_service.py` | 宏观重构提案服务 |
| `application/blueprint/services/beat_sheet_service.py` | 节拍表生成服务 |
| `application/blueprint/services/continuous_planning_service.py` | 持续规划服务 |
| `application/blueprint/services/volume_summary_service.py` | 卷级摘要服务 |
| `application/blueprint/services/setup_main_plot_suggestion_service.py` | 主线推演服务 |
| `application/world/services/auto_bible_generator.py` | Bible 自动生成器 |
| `application/world/services/auto_knowledge_generator.py` | 知识图谱自动生成器 |
| `application/workbench/services/sandbox_dialogue_service.py` | 沙盒对白服务 |
| `application/engine/services/autopilot_daemon.py` | 自动驾驶守护进程 |
| `interfaces/api/v1/workbench/llm_control.py` | API 路由 |
| `infrastructure/persistence/database/schema.sql` | 数据库表定义 |

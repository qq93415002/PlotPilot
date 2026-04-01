"""AutoNovelGenerationWorkflow 单元测试"""
import pytest
from unittest.mock import Mock, AsyncMock
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.dtos.generation_result import GenerationResult
from application.services.context_builder import ContextBuilder
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.services.storyline_manager import StorylineManager
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.value_objects.consistency_report import ConsistencyReport, Issue, IssueType, Severity
from domain.novel.value_objects.chapter_state import ChapterState
from domain.ai.services.llm_service import LLMService, GenerationResult as LLMResult
from domain.ai.value_objects.token_usage import TokenUsage


@pytest.fixture
def mock_context_builder():
    """Mock ContextBuilder"""
    builder = Mock(spec=ContextBuilder)
    builder.build_context.return_value = "Mock context with 35K tokens"
    builder.estimate_tokens.return_value = 8750  # 35K tokens / 4
    return builder


@pytest.fixture
def mock_consistency_checker():
    """Mock ConsistencyChecker"""
    checker = Mock(spec=ConsistencyChecker)
    checker.check_all.return_value = ConsistencyReport(
        issues=[],
        warnings=[],
        suggestions=[]
    )
    return checker


@pytest.fixture
def mock_storyline_manager():
    """Mock StorylineManager"""
    manager = Mock(spec=StorylineManager)
    manager.repository = Mock()
    manager.repository.find_by_novel.return_value = []
    manager.get_storyline_context.return_value = "Main storyline context"
    return manager


@pytest.fixture
def mock_plot_arc_repository():
    """Mock PlotArcRepository"""
    repo = Mock(spec=PlotArcRepository)
    return repo


async def _mock_stream_generate(*args, **kwargs):
    yield "Generated chapter content"


@pytest.fixture
def mock_llm_service():
    """Mock LLMService"""
    service = Mock(spec=LLMService)
    service.generate = AsyncMock(return_value=LLMResult(
        content="Generated chapter content",
        token_usage=TokenUsage(input_tokens=500, output_tokens=500)
    ))
    service.stream_generate = _mock_stream_generate
    return service


@pytest.fixture
def workflow(
    mock_context_builder,
    mock_consistency_checker,
    mock_storyline_manager,
    mock_plot_arc_repository,
    mock_llm_service
):
    """创建 AutoNovelGenerationWorkflow 实例"""
    return AutoNovelGenerationWorkflow(
        context_builder=mock_context_builder,
        consistency_checker=mock_consistency_checker,
        storyline_manager=mock_storyline_manager,
        plot_arc_repository=mock_plot_arc_repository,
        llm_service=mock_llm_service
    )


class TestGenerateChapter:
    """测试 generate_chapter 方法"""

    @pytest.mark.asyncio
    async def test_generate_chapter_success(self, workflow, mock_context_builder, mock_llm_service):
        """测试成功生成章节"""
        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline"
        )

        # 验证返回结果
        assert isinstance(result, GenerationResult)
        assert result.content == "Generated chapter content"
        assert result.token_count == 8750
        assert result.context_used == "Mock context with 35K tokens"
        assert isinstance(result.consistency_report, ConsistencyReport)

        # 验证调用顺序
        mock_context_builder.build_context.assert_called_once_with(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline",
            max_tokens=35000
        )
        mock_llm_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_chapter_with_consistency_issues(
        self, workflow, mock_consistency_checker
    ):
        """测试生成章节时发现一致性问题"""
        # 设置一致性检查返回问题
        mock_consistency_checker.check_all.return_value = ConsistencyReport(
            issues=[
                Issue(
                    type=IssueType.CHARACTER_INCONSISTENCY,
                    severity=Severity.CRITICAL,
                    description="Character not found",
                    location=1
                )
            ],
            warnings=[],
            suggestions=[]
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline"
        )

        # 验证返回结果包含问题
        assert result.consistency_report.has_critical_issues()
        assert len(result.consistency_report.issues) == 1

    @pytest.mark.asyncio
    async def test_generate_chapter_invalid_chapter_number(self, workflow):
        """测试无效的章节号"""
        with pytest.raises(ValueError, match="chapter_number must be positive"):
            await workflow.generate_chapter(
                novel_id="novel-1",
                chapter_number=0,
                outline="Chapter outline"
            )

    @pytest.mark.asyncio
    async def test_generate_chapter_empty_outline(self, workflow):
        """测试空大纲"""
        with pytest.raises(ValueError, match="outline cannot be empty"):
            await workflow.generate_chapter(
                novel_id="novel-1",
                chapter_number=1,
                outline=""
            )


class TestGenerateChapterWithReview:
    """测试 generate_chapter_with_review 方法"""

    @pytest.mark.asyncio
    async def test_generate_with_review_success(self, workflow):
        """测试带审查的生成成功"""
        content, report = await workflow.generate_chapter_with_review(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline"
        )

        assert content == "Generated chapter content"
        assert isinstance(report, ConsistencyReport)
        assert not report.has_critical_issues()

    @pytest.mark.asyncio
    async def test_generate_with_review_returns_issues(
        self, workflow, mock_consistency_checker
    ):
        """测试带审查的生成返回问题"""
        mock_consistency_checker.check_all.return_value = ConsistencyReport(
            issues=[
                Issue(
                    type=IssueType.EVENT_LOGIC_ERROR,
                    severity=Severity.IMPORTANT,
                    description="Event logic error",
                    location=1
                )
            ],
            warnings=[],
            suggestions=["Consider revising the event sequence"]
        )

        content, report = await workflow.generate_chapter_with_review(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline"
        )

        assert content == "Generated chapter content"
        assert len(report.issues) == 1
        assert len(report.suggestions) == 1


class TestSuggestOutline:
    """测试 suggest_outline"""

    @pytest.mark.asyncio
    async def test_suggest_outline_returns_llm_text(self, workflow, mock_llm_service):
        mock_llm_service.generate = AsyncMock(
            return_value=LLMResult(
                content="1. 开场\n2. 转折",
                token_usage=TokenUsage(input_tokens=10, output_tokens=20),
            )
        )
        text = await workflow.suggest_outline("novel-1", 3)
        assert "开场" in text
        mock_llm_service.generate.assert_called_once()


class TestGenerateChapterStream:
    """测试 generate_chapter_stream 流式事件"""

    @pytest.mark.asyncio
    async def test_stream_emits_phases_chunk_and_done(self, workflow):
        events = []
        async for e in workflow.generate_chapter_stream("novel-1", 1, "Chapter outline"):
            events.append(e)
        types = [x["type"] for x in events]
        assert "phase" in types
        assert "chunk" in types
        assert events[-1]["type"] == "done"
        assert events[-1]["content"] == "Generated chapter content"
        assert events[-1]["token_count"] == 8750


class TestExtractChapterState:
    """测试 _extract_chapter_state 方法"""

    def test_extract_chapter_state_from_content(self, workflow):
        """测试从内容中提取章节状态"""
        content = "Chapter content with character actions"

        state = workflow._extract_chapter_state(content, chapter_number=1)

        assert isinstance(state, ChapterState)
        # 基本实现应该返回空列表
        assert isinstance(state.new_characters, list)
        assert isinstance(state.character_actions, list)
        assert isinstance(state.relationship_changes, list)


class TestBuildPrompt:
    """测试 _build_prompt 方法"""

    def test_build_prompt_with_context(self, workflow):
        """测试构建提示词"""
        prompt = workflow._build_prompt(
            context="Full context",
            outline="Chapter outline"
        )

        assert "Full context" in prompt.system
        assert "Chapter outline" in prompt.user

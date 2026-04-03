<template>
  <aside class="sidebar">
    <div class="sidebar-head">
      <n-button quaternary size="small" class="back-btn" @click="handleBack">
        <template #icon>
          <span class="ico-arrow">←</span>
        </template>
        书目列表
      </n-button>

      <!-- 视图模式切换 -->
      <div class="view-mode-row">
        <n-select
          v-model:value="viewMode"
          :options="viewModeOptions"
          size="small"
          style="flex: 1;"
        />
        <n-button
          v-if="!chapters.length"
          size="small"
          type="primary"
          secondary
          :loading="planning"
          @click="handlePlanNovel"
          title="使用 AI 生成初始 Bible 和章节大纲"
        >
          ✦ AI 初始规划
        </n-button>
        <n-button
          v-else
          size="small"
          type="primary"
          secondary
          :loading="extending"
          @click="handleExtendOutline"
          title="基于当前进度续写后续章节大纲"
        >
          ➕ 续写大纲
        </n-button>
      </div>
    </div>

    <n-scrollbar class="sidebar-scroll">
      <!-- 平铺视图：仅显示章节列表 -->
      <div v-if="viewMode === 'flat'">
        <div v-if="!chapters.length" class="sidebar-empty">暂无章节大纲，可先执行「结构规划」</div>
        <n-list v-else hoverable clickable>
          <n-list-item
            v-for="ch in chapters"
            :key="ch.id"
            :class="{ 'is-active': currentChapterId === ch.id }"
            @click="handleChapterClick(ch.id)"
          >
            <n-thing :title="`第${ch.number}章`">
              <template #description>
                <div style="display: flex; flex-direction: column; gap: 4px;">
                  <n-text depth="3" style="font-size: 12px;">{{ ch.title }}</n-text>
                  <n-tag size="small" :type="ch.word_count > 0 ? 'success' : 'default'" round>
                    {{ ch.word_count > 0 ? '已收稿' : '未收稿' }}
                  </n-tag>
                </div>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
      </div>

      <!-- 树形视图：显示完整叙事结构（部-卷-幕-章） -->
      <div v-else-if="viewMode === 'tree'">
        <StoryStructureTree
          :slug="slug"
          :current-chapter-id="currentChapterId"
          @select-chapter="handleChapterClick"
        />
      </div>
    </n-scrollbar>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { workflowApi } from '@/api/workflow'
import StoryStructureTree from '@/components/StoryStructureTree.vue'

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
}

interface ChapterListProps {
  slug: string
  chapters: Chapter[]
  currentChapterId?: number | null
}

const props = withDefaults(defineProps<ChapterListProps>(), {
  chapters: () => [],
  currentChapterId: null
})

const emit = defineEmits<{
  select: [id: number]
  back: []
  refresh: []
}>()

const message = useMessage()
const dialog = useDialog()

const viewMode = ref('tree')
const viewModeOptions = [
  { label: '🌳 树形视图', value: 'tree' },
  { label: '📄 平铺视图', value: 'flat' }
]

const planning = ref(false)
const extending = ref(false)

const handleChapterClick = (id: number) => {
  emit('select', id)
}

const handleBack = () => {
  emit('back')
}

// AI 初始规划
const handlePlanNovel = async () => {
  dialog.warning({
    title: 'AI 初始规划',
    content: '将使用 AI 生成初始 Bible（世界设定）和章节大纲。此操作可能需要 1-2 分钟，确认继续？',
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      planning.value = true
      try {
        const res = await workflowApi.planNovel(props.slug, 'initial', false)
        message.success(res.message || 'AI 规划完成')
        emit('refresh')
      } catch (e: any) {
        message.error(e?.response?.data?.detail || 'AI 规划失败，请确认 API Key 已配置')
      } finally {
        planning.value = false
      }
    }
  })
}

// 续写大纲
const handleExtendOutline = () => {
  const lastChapter = props.chapters[props.chapters.length - 1]
  const fromChapter = lastChapter ? lastChapter.number + 1 : 1
  const extendCount = ref(5)

  dialog.warning({
    title: '续写大纲',
    content: `将从第 ${fromChapter} 章开始续写大纲，默认生成 5 章（可在后续版本中自定义数量）`,
    positiveText: '开始续写',
    negativeText: '取消',
    onPositiveClick: async () => {
      extending.value = true
      try {
        const res = await workflowApi.extendOutline(props.slug, fromChapter, extendCount.value)
        message.success(`成功生成 ${res.chapters_added} 章大纲`)
        emit('refresh')
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '续写大纲失败，请确认 API Key 已配置')
      } finally {
        extending.value = false
      }
    }
  })
}
</script>

<style scoped>
.sidebar {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 10px;
  background: var(--app-surface);
  border-right: 1px solid var(--aitext-split-border);
}

.sidebar-head {
  margin-bottom: 10px;
}

.back-btn {
  margin-bottom: 8px;
  font-weight: 500;
}

.ico-arrow {
  font-size: 14px;
  margin-right: 2px;
}

.view-mode-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.sidebar-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.sidebar-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.sidebar-scroll {
  flex: 1;
  min-height: 0;
}

.sidebar-empty {
  padding: 12px;
  font-size: 13px;
  color: var(--app-muted);
  line-height: 1.5;
}

.sidebar :deep(.n-list-item) {
  border-radius: 10px;
  margin-bottom: 4px;
  transition: background var(--app-transition), transform 0.15s ease;
}

.sidebar :deep(.n-list-item:hover) {
  background: rgba(79, 70, 229, 0.06);
}

.sidebar :deep(.n-list-item.is-active) {
  background: rgba(79, 70, 229, 0.12);
  box-shadow: inset 0 0 0 1px rgba(79, 70, 229, 0.25);
}
</style>
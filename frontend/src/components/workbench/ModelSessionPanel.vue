<template>
  <div class="model-session-panel">
    <header class="panel-header">
      <div class="header-main">
        <h3 class="panel-title">模型会话</h3>
        <p class="panel-lead">
          记录所有与 AI 大模型的交互内容
        </p>
      </div>
      <n-space class="header-actions" :size="8" align="center">
        <n-button size="small" type="primary" :loading="loading" @click="load">刷新</n-button>
      </n-space>
    </header>

    <div class="panel-content">
      <n-spin :show="loading">
        <template v-if="sessions.length === 0">
          <n-empty description="暂无会话记录">
            <template #icon><span class="empty-ico" aria-hidden="true">💬</span></template>
          </n-empty>
        </template>
        <n-space v-else vertical :size="8" class="session-list">
          <n-card
            v-for="(session, index) in sessions"
            :key="index"
            size="small"
            :bordered="true"
            hoverable
            class="session-card"
          >
            <template #header>
              <div class="session-header">
                <n-tag :type="session.ROLE === 'USER' ? 'info' : 'success'" size="small" round>
                  {{ session.ROLE === 'USER' ? '用户' : 'AI' }}
                </n-tag>
                <n-text class="session-date">{{ session.DATE }}</n-text>
                <n-tag v-if="session.CHAPTER" size="tiny" type="warning">
                  第{{ session.CHAPTER }}章
                </n-tag>
              </div>
            </template>
            <div class="session-preview">
              <n-text depth="3" class="preview-text">{{ session.CHAT.substring(0, 30) }}...</n-text>
            </div>
            <template #action>
              <n-button size="tiny" secondary @click="showDetail(session)">查看详情</n-button>
            </template>
          </n-card>
        </n-space>
      </n-spin>
    </div>

    <n-modal v-model:show="detailVisible" preset="card" title="会话详情" style="max-width: 600px;" :bordered="false">
      <n-input
        v-model:value="currentChat"
        type="textarea"
        readonly
        :autosize="{ minRows: 10, maxRows: 20 }"
      />
      <template #footer>
        <n-space justify="end">
          <n-tag v-if="currentSession?.MODEL">模型: {{ currentSession.MODEL }}</n-tag>
          <n-tag v-if="currentSession?.PROMPT_NODE">节点: {{ currentSession.PROMPT_NODE }}</n-tag>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NSpace, NCard, NButton, NEmpty, NSpin, NTag, NText, NModal, NInput } from 'naive-ui'

const props = defineProps<{
  slug: string
}>()

const loading = ref(false)
const sessions = ref<any[]>([])
const detailVisible = ref(false)
const currentSession = ref<any>(null)
const currentChat = ref('')

async function load() {
  loading.value = true
  try {
    const response = await fetch(`/api/v1/novels/${props.slug}/llm-sessions?limit=200`)
    if (response.ok) {
      const data = await response.json()
      sessions.value = data.sessions || []
    }
  } catch (e) {
    console.error('加载会话记录失败:', e)
  } finally {
    loading.value = false
  }
}

function showDetail(session: any) {
  currentSession.value = session
  currentChat.value = session.CHAT
  detailVisible.value = true
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.model-session-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 12px 16px;
  border-bottom: 1px solid var(--n-border-color);
}

.header-main {
  flex: 1;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.panel-lead {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--n-text-color-3);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.session-list {
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}

.session-card {
  margin-bottom: 8px;
}

.session-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-date {
  font-size: 12px;
  color: var(--n-text-color-3);
}

.session-preview {
  padding: 4px 0;
}

.preview-text {
  font-size: 13px;
}

.empty-ico {
  font-size: 32px;
}
</style>

import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
})

export interface LLMSessionRecord {
  ROLE: 'USER' | 'ASSISTANT'
  DATE: string
  CHAT: string
  MODEL?: string
  PROMPT_NODE?: string
  CHAPTER?: number
}

export interface LLMSessionListResponse {
  sessions: LLMSessionRecord[]
  total: number
}

export interface SaveLLMSessionRequest {
  novel_id: string
  role: 'USER' | 'ASSISTANT'
  chat: string
  model?: string
  prompt_node?: string
  chapter_number?: number
}

export const llmSessionApi = {
  getSessions(novelId: string, limit: number = 100): Promise<LLMSessionListResponse> {
    return api.get(`/novels/${novelId}/llm-sessions`, { params: { limit } }).then(res => res.data)
  },

  saveSession(data: SaveLLMSessionRequest): Promise<{ id: string; success: boolean }> {
    return api.post('/novels/llm-sessions', data).then(res => res.data)
  },

  deleteSessions(novelId: string): Promise<{ success: boolean; deleted: number }> {
    return api.delete(`/novels/${novelId}/llm-sessions`).then(res => res.data)
  },
}

export type AgentIntent = 'RECENT_SUMMARY' | 'HOMEWORK_DIAGNOSIS' | 'LESSON_FEEDBACK' | 'PARENT_REPLY'

export type AgentChatParams = {
  intent: AgentIntent
  time_range: string
  subject: string
  lesson_id: string | null
  tone: string
  length: string
  parent_question: string | null
}

export type AgentChatRequest = {
  conversation_id?: string | null
  teacher_id: string
  student_id?: string
  message: string
  scene: string
  params: AgentChatParams
  context: Record<string, unknown>
}

export type AgentSection = {
  name: string
  items: string[]
}

export type AgentChatResponse = {
  request_id: string
  intent: string
  status: string
  title: string
  content: string
  sections: AgentSection[]
  evidence: string[]
  warnings: string[]
  available_actions: string[]
  is_draft: boolean
  auto_send: boolean
  write_database: boolean
}

export type ChatMessage = {
  id: string
  role: 'user' | 'agent'
  text: string
  response?: AgentChatResponse
  timestamp: string
}

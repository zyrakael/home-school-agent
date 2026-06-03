export type ClassInfo = {
  id: string
  name: string
  grade: string
}

export type StudentSummary = {
  id: string
  name: string
  status: string
}

export type StudentStats = {
  homework_completed: number
  homework_total: number
  accuracy_avg: number
  last_active: string
}

export type StudentDetail = {
  id: string
  name: string
  grade: string
  class_id: string
  stats: StudentStats
}

export type HomeworkSummary = {
  id: string
  title: string
  subject: string
  assigned_at: string
  due_at: string
  status: 'pending' | 'submitted' | 'late' | 'missing'
  accuracy: number | null
}

export type HomeworkDetail = {
  id: string
  title: string
  subject: string
  assigned_at: string
  due_at: string
  status: 'pending' | 'submitted' | 'late' | 'missing'
  accuracy: number | null
  wrong_count: number
  notes: string
  questions: string[]
}

export type AiAssistRequest = {
  student_id: string
  homework_id?: string | null
  prompt: string
}

export type AiAssistResponse = {
  request_id: string
  draft: string
  tips: string[]
}

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
  teacher_id: string
  student_id: string
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

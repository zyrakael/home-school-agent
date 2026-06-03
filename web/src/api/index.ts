import { apiClient, apiRoot } from './client'
import type {
  AgentChatRequest,
  AgentChatResponse,
  AiAssistRequest,
  AiAssistResponse,
  ClassInfo,
  HomeworkDetail,
  HomeworkSummary,
  StudentDetail,
  StudentSummary,
} from './types'

export const fetchClasses = async (): Promise<ClassInfo[]> => {
  const response = await apiClient.get<ClassInfo[]>('/classes')
  return response.data
}

export const fetchStudents = async (classId: string): Promise<StudentSummary[]> => {
  const response = await apiClient.get<StudentSummary[]>(`/classes/${classId}/students`)
  return response.data
}

export const fetchStudentDetail = async (studentId: string): Promise<StudentDetail> => {
  const response = await apiClient.get<StudentDetail>(`/students/${studentId}`)
  return response.data
}

export const fetchHomeworks = async (studentId: string): Promise<HomeworkSummary[]> => {
  const response = await apiClient.get<HomeworkSummary[]>(`/students/${studentId}/homeworks`)
  return response.data
}

export const fetchHomeworkDetail = async (homeworkId: string): Promise<HomeworkDetail> => {
  const response = await apiClient.get<HomeworkDetail>(`/homeworks/${homeworkId}`)
  return response.data
}

export const requestAiAssist = async (payload: AiAssistRequest): Promise<AiAssistResponse> => {
  const response = await apiClient.post<AiAssistResponse>('/ai/assist', payload)
  return response.data
}

export const requestAgentChat = async (payload: AgentChatRequest): Promise<AgentChatResponse> => {
  const response = await fetch(`${apiRoot}/agent/mvp/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`Agent chat failed: ${response.statusText}`)
  }
  return response.json()
}

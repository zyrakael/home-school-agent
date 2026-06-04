import { apiRoot } from './client'
import type { AgentChatRequest, AgentChatResponse } from './types'

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

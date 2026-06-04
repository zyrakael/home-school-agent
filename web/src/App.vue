<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { requestAgentChat } from './api'
import type { AgentChatResponse, AgentIntent, ChatMessage } from './api/types'

const chatMessages = ref<ChatMessage[]>([
  {
    id: 'msg_welcome',
    role: 'agent',
    text: '你好！我是家校沟通助手。\n\n我可以帮老师生成近期学习总结、作业诊断、课后反馈和家长问题回复草稿。你可以直接描述需求，也可以使用下方快捷入口。',
    timestamp: new Date().toISOString(),
  },
])
const chatInput = ref('')
const chatLoading = ref(false)
const chatContainer = ref<HTMLElement | null>(null)

const quickButtons: Array<{ label: string; text: string; intent: AgentIntent }> = [
  { label: '近况总结', text: '帮我总结一下这个学生最近一周的学习情况', intent: 'RECENT_SUMMARY' },
  { label: '错题诊断', text: '这个学生最近错在哪里？帮我做一下错题诊断', intent: 'HOMEWORK_DIAGNOSIS' },
  { label: '课后反馈', text: '帮我生成今天的课后反馈草稿', intent: 'LESSON_FEEDBACK' },
  { label: '回复家长', text: '家长问孩子最近有没有进步，我怎么回？', intent: 'PARENT_REPLY' },
]

const scrollChatToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

const inferIntent = (text: string): AgentIntent => {
  if (text.includes('错题') || text.includes('诊断')) return 'HOMEWORK_DIAGNOSIS'
  if (text.includes('课后') || text.includes('反馈')) return 'LESSON_FEEDBACK'
  if (text.includes('家长') || text.includes('回复')) return 'PARENT_REPLY'
  return 'RECENT_SUMMARY'
}

const sendMessage = async (intent?: AgentIntent) => {
  const text = chatInput.value.trim()
  if (!text || chatLoading.value) return

  chatInput.value = ''
  chatMessages.value.push({
    id: `msg_${Date.now()}`,
    role: 'user',
    text,
    timestamp: new Date().toISOString(),
  })
  await scrollChatToBottom()

  chatLoading.value = true
  try {
    const response: AgentChatResponse = await requestAgentChat({
      teacher_id: 'teacher_demo',
      student_id: 'student_demo',
      message: text,
      scene: 'agent_workspace',
      params: {
        intent: intent ?? inferIntent(text),
        time_range: '7d',
        subject: '数学',
        lesson_id: null,
        tone: '温和',
        length: '标准版',
        parent_question: text,
      },
      context: {},
    })

    chatMessages.value.push({
      id: `msg_${Date.now()}_agent`,
      role: 'agent',
      text: response.content,
      response,
      timestamp: new Date().toISOString(),
    })
  } catch {
    chatMessages.value.push({
      id: `msg_${Date.now()}_err`,
      role: 'agent',
      text: '请求失败，请确认后端 Agent API 与 MCP Data Service 都已启动。',
      timestamp: new Date().toISOString(),
    })
  } finally {
    chatLoading.value = false
    await scrollChatToBottom()
  }
}

const handleQuickButton = (text: string, intent: AgentIntent) => {
  chatInput.value = text
  sendMessage(intent)
}
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand">
        <span class="brand-icon">AI</span>
        <div>
          <div class="brand-title">家校沟通 Agent</div>
          <div class="brand-sub">老师可编辑草稿生成工作台</div>
        </div>
      </div>
      <el-tag type="success" effect="plain">Agent Only</el-tag>
    </el-header>

    <el-main class="main-area">
      <div class="chat-shell">
        <div class="chat-header">
          <span class="chat-header-icon">Chat</span>
          <span>智能助手对话</span>
          <el-tag size="small" type="info" effect="plain">远程 MCP 数据工具</el-tag>
        </div>

        <div class="chat-messages" ref="chatContainer">
          <transition-group name="msg-fade">
            <div v-for="msg in chatMessages" :key="msg.id" class="chat-msg" :class="msg.role">
              <div class="msg-avatar">
                {{ msg.role === 'user' ? '师' : 'AI' }}
              </div>
              <div class="msg-body">
                <div class="msg-bubble">
                  <div class="msg-text" v-text="msg.text"></div>
                </div>

                <div v-if="msg.response && msg.response.status === 'success'" class="agent-card">
                  <div class="agent-card-header">
                    <span class="agent-card-icon">Draft</span>
                    {{ msg.response.title }}
                  </div>

                  <div v-for="sec in msg.response.sections" :key="sec.name" class="agent-section">
                    <div class="agent-section-name">{{ sec.name }}</div>
                    <ul class="agent-section-items">
                      <li v-for="item in sec.items" :key="item">{{ item }}</li>
                    </ul>
                  </div>

                  <div v-if="msg.response.evidence.length" class="agent-evidence">
                    <div class="agent-evidence-title">数据依据</div>
                    <ul>
                      <li v-for="e in msg.response.evidence" :key="e">{{ e }}</li>
                    </ul>
                  </div>

                  <div v-if="msg.response.warnings.length" class="agent-warnings">
                    <div class="agent-warnings-title">提示</div>
                    <ul>
                      <li v-for="w in msg.response.warnings" :key="w">{{ w }}</li>
                    </ul>
                  </div>

                  <div v-if="msg.response.available_actions.length" class="agent-actions">
                    <el-tag
                      v-for="act in msg.response.available_actions"
                      :key="act"
                      size="small"
                      class="action-tag"
                    >
                      {{ act }}
                    </el-tag>
                  </div>
                </div>
              </div>
            </div>
          </transition-group>

          <div v-if="chatLoading" class="chat-msg agent">
            <div class="msg-avatar">AI</div>
            <div class="msg-body">
              <div class="msg-bubble thinking">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span>
              </div>
            </div>
          </div>
        </div>

        <div class="quick-buttons">
          <el-button
            v-for="btn in quickButtons"
            :key="btn.label"
            size="small"
            :disabled="chatLoading"
            @click="handleQuickButton(btn.text, btn.intent)"
          >
            {{ btn.label }}
          </el-button>
        </div>

        <div class="chat-input-row">
          <el-input
            v-model="chatInput"
            placeholder="输入需求，例如：帮我总结一下这个学生最近一周的学习情况..."
            size="large"
            :disabled="chatLoading"
            class="chat-input"
            @keyup.enter="sendMessage()"
          >
            <template #append>
              <el-button type="primary" :loading="chatLoading" @click="sendMessage()">发送</el-button>
            </template>
          </el-input>
        </div>
      </div>
    </el-main>
  </el-container>
</template>

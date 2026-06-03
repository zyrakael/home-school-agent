<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import {
  fetchClasses,
  fetchHomeworkDetail,
  fetchHomeworks,
  fetchStudentDetail,
  fetchStudents,
  requestAgentChat,
} from './api'
import type {
  AgentChatResponse,
  ChatMessage,
  ClassInfo,
  HomeworkDetail,
  HomeworkSummary,
  StudentDetail,
  StudentSummary,
} from './api/types'
import { statusLabelMap } from './types/ui'

// ── state ──────────────────────────────────────────────

const classes = ref<ClassInfo[]>([])
const selectedClassId = ref('')
const students = ref<StudentSummary[]>([])
const selectedStudentId = ref('')
const studentDetail = ref<StudentDetail | null>(null)
const homeworks = ref<HomeworkSummary[]>([])
const selectedHomeworkId = ref('')
const homeworkDetail = ref<HomeworkDetail | null>(null)

const chatMessages = ref<ChatMessage[]>([])
const chatInput = ref('')
const chatLoading = ref(false)
const chatContainer = ref<HTMLElement | null>(null)
const loadError = ref('')

const isLoading = ref({
  classes: false,
  students: false,
  student: false,
  homeworks: false,
  homework: false,
})

// ── helpers ────────────────────────────────────────────

const formatAccuracy = (value: number | null) =>
  value === null ? '-' : `${Math.round(value * 100)}%`

const selectedClassName = computed(() => {
  const classInfo = classes.value.find((item) => item.id === studentDetail.value?.class_id)
  return classInfo?.name ?? studentDetail.value?.class_id ?? '-'
})

const scrollChatToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

const quickButtons = [
  { label: '近况总结', text: '帮我总结一下这个学生最近一周的学习情况' },
  { label: '错题诊断', text: '这个学生最近错在哪里？帮我做一下错题诊断' },
  { label: '课后反馈', text: '帮我生成今天的课后反馈草稿' },
  { label: '回复家长', text: '家长问孩子最近有没有进步，我怎么回？' },
]

// ── data loading ───────────────────────────────────────

const loadClasses = async () => {
  isLoading.value.classes = true
  loadError.value = ''
  try {
    classes.value = await fetchClasses()
    if (!selectedClassId.value && classes.value.length > 0) {
      selectedClassId.value = classes.value[0].id
    }
  } catch (error) {
    console.error(error)
    loadError.value = '班级数据加载失败，请确认后端已启动且数据库中有 classes 数据。'
  } finally {
    isLoading.value.classes = false
  }
}

const loadStudents = async (classId: string) => {
  isLoading.value.students = true
  loadError.value = ''
  try {
    students.value = await fetchStudents(classId)
    selectedStudentId.value = students.value[0]?.id ?? ''
  } catch (error) {
    console.error(error)
    students.value = []
    selectedStudentId.value = ''
    loadError.value = '学生数据加载失败，请确认 students 表里有当前班级的数据。'
  } finally {
    isLoading.value.students = false
  }
}

const loadStudentDetail = async (studentId: string) => {
  if (!studentId) return
  isLoading.value.student = true
  loadError.value = ''
  try {
    studentDetail.value = await fetchStudentDetail(studentId)
  } catch (error) {
    console.error(error)
    studentDetail.value = null
    loadError.value = '学生详情加载失败，请确认学生数据完整。'
  } finally {
    isLoading.value.student = false
  }
}

const loadHomeworks = async (studentId: string) => {
  if (!studentId) return
  isLoading.value.homeworks = true
  loadError.value = ''
  try {
    homeworks.value = await fetchHomeworks(studentId)
    selectedHomeworkId.value = homeworks.value[0]?.id ?? ''
  } catch (error) {
    console.error(error)
    homeworks.value = []
    selectedHomeworkId.value = ''
    loadError.value = '作业数据加载失败，请确认 homeworks 表里有当前学生的数据。'
  } finally {
    isLoading.value.homeworks = false
  }
}

const loadHomeworkDetail = async (homeworkId: string) => {
  if (!homeworkId) {
    homeworkDetail.value = null
    return
  }
  isLoading.value.homework = true
  loadError.value = ''
  try {
    homeworkDetail.value = await fetchHomeworkDetail(homeworkId)
  } catch (error) {
    console.error(error)
    homeworkDetail.value = null
    loadError.value = '作业详情加载失败，请确认 homework_details / homework_questions 数据完整。'
  } finally {
    isLoading.value.homework = false
  }
}

// ── chat ───────────────────────────────────────────────

const sendMessage = async () => {
  const text = chatInput.value.trim()
  if (!text || chatLoading.value) return

  chatInput.value = ''
  const userMsg: ChatMessage = {
    id: `msg_${Date.now()}`,
    role: 'user',
    text,
    timestamp: new Date().toISOString(),
  }
  chatMessages.value.push(userMsg)
  await scrollChatToBottom()

  chatLoading.value = true
  try {
    const response: AgentChatResponse = await requestAgentChat({
      teacher_id: 't_mock_001',
      student_id: selectedStudentId.value || 's_mock_001',
      message: text,
      scene: 'chat',
      params: {
        intent: 'RECENT_SUMMARY',
        time_range: '7d',
        subject: '数学',
        lesson_id: null,
        tone: '温和',
        length: '标准版',
        parent_question: text,
      },
      context: {},
    })

    const agentMsg: ChatMessage = {
      id: `msg_${Date.now()}_agent`,
      role: 'agent',
      text: response.content,
      response,
      timestamp: new Date().toISOString(),
    }
    chatMessages.value.push(agentMsg)
  } catch {
    const errorMsg: ChatMessage = {
      id: `msg_${Date.now()}_err`,
      role: 'agent',
      text: '抱歉，请求失败，请稍后重试。',
      timestamp: new Date().toISOString(),
    }
    chatMessages.value.push(errorMsg)
  } finally {
    chatLoading.value = false
    await scrollChatToBottom()
  }
}

const handleQuickButton = (text: string) => {
  chatInput.value = text
  sendMessage()
}

// ── row click handlers ─────────────────────────────────

const handleStudentSelect = (row: StudentSummary) => {
  selectedStudentId.value = row.id
}

const handleHomeworkSelect = (row: HomeworkSummary) => {
  selectedHomeworkId.value = row.id
}

const studentRowClass = ({ row }: { row: StudentSummary }) =>
  row.id === selectedStudentId.value ? 'table-row--active' : ''
const homeworkRowClass = ({ row }: { row: HomeworkSummary }) =>
  row.id === selectedHomeworkId.value ? 'table-row--active' : ''

// ── watchers ───────────────────────────────────────────

watch(selectedClassId, async (value) => {
  if (!value) return
  await loadStudents(value)
})

watch(selectedStudentId, async (value) => {
  if (!value) return
  await Promise.all([loadStudentDetail(value), loadHomeworks(value)])
})

watch(selectedHomeworkId, async (value) => {
  await loadHomeworkDetail(value)
})

onMounted(() => {
  loadClasses()
})

// initial greeting
chatMessages.value.push({
  id: 'msg_welcome',
  role: 'agent',
  text: '你好！我是家校沟通助手 🤖\n\n我可以帮你：\n• 总结学生近期学习情况\n• 诊断作业和错题问题\n• 生成课后反馈草稿\n• 帮您回复家长问题\n\n请选择一个学生，然后输入你的需求，或者点击下方的快捷按钮。',
  timestamp: new Date().toISOString(),
})
</script>

<template>
  <el-container class="app-shell">
    <!-- ── Header ──────────────────────────────── -->
    <el-header class="app-header">
      <div class="brand">
        <span class="brand-icon">🤖</span>
        <div>
          <div class="brand-title">家校沟通工作台</div>
          <div class="brand-sub">AI 智能助手 · 让沟通更高效</div>
        </div>
      </div>
      <div class="header-actions">
        <el-alert
          v-if="loadError"
          class="header-alert"
          type="error"
          :title="loadError"
          show-icon
          :closable="false"
        />
        <span class="header-hint">选择班级 &darr;</span>
        <el-select
          v-model="selectedClassId"
          class="class-select"
          placeholder="选择班级"
          size="large"
          :loading="isLoading.classes"
        >
          <el-option v-for="item in classes" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </div>
    </el-header>

    <el-container class="content-shell">
      <!-- ── Left: Student Panel ─────────────────── -->
      <el-aside class="panel panel-left" width="300px">
        <!-- student list -->
        <div class="panel-section">
          <div class="panel-title">👨‍🎓 学生列表</div>
          <el-table
            :data="students"
            height="220"
            size="small"
            :row-class-name="studentRowClass"
            @row-click="handleStudentSelect"
            v-loading="isLoading.students"
          >
            <el-table-column prop="name" label="姓名" min-width="90" />
            <el-table-column prop="status" label="状态" width="70">
              <template #default="scope">
                <el-tag :type="scope.row.status === 'active' ? 'success' : 'info'" size="small">
                  {{ scope.row.status === 'active' ? '在读' : scope.row.status }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- student profile -->
        <div class="panel-section">
          <div class="panel-title">📋 学生概览</div>
          <div v-if="studentDetail" class="profile-card">
            <div class="profile-name">{{ studentDetail.name }}</div>
            <div class="profile-meta">
              <span>{{ studentDetail.grade }}</span>
              <span>·</span>
              <span>{{ selectedClassName }}</span>
            </div>
            <div class="profile-stats">
              <div class="stat-item">
                <div class="stat-num">{{ studentDetail.stats.homework_completed }}/{{ studentDetail.stats.homework_total }}</div>
                <div class="stat-label">作业完成</div>
              </div>
              <div class="stat-item">
                <div class="stat-num">{{ formatAccuracy(studentDetail.stats.accuracy_avg) }}</div>
                <div class="stat-label">平均正确率</div>
              </div>
              <div class="stat-item">
                <div class="stat-num">{{ studentDetail.stats.last_active }}</div>
                <div class="stat-label">最近活跃</div>
              </div>
            </div>
          </div>
          <el-empty v-else description="请选择学生" :image-size="60" />
        </div>

        <!-- homework list -->
        <div class="panel-section">
          <div class="panel-title">📝 作业列表</div>
          <el-table
            :data="homeworks"
            height="auto"
            max-height="180"
            size="small"
            :row-class-name="homeworkRowClass"
            @row-click="handleHomeworkSelect"
            v-loading="isLoading.homeworks"
          >
            <el-table-column prop="title" label="作业" min-width="120" />
            <el-table-column label="状态" width="75">
              <template #default="scope">
                <el-tag
                  :type="scope.row.status === 'submitted' ? 'success' : scope.row.status === 'missing' ? 'danger' : 'warning'"
                  size="small"
                >
                  {{ statusLabelMap[scope.row.status] }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- homework detail -->
        <div class="panel-section">
          <div class="panel-title">🔍 作业详情</div>
          <div v-if="homeworkDetail" class="hw-detail">
            <div class="hw-title">{{ homeworkDetail.title }}</div>
            <div class="hw-meta">
              <span>{{ homeworkDetail.subject }}</span>
              <span>· 截至 {{ homeworkDetail.due_at }}</span>
            </div>
            <div class="hw-stats">
              <div class="hw-stat">
                <span class="hw-stat-label">正确率</span>
                <span class="hw-stat-value">{{ formatAccuracy(homeworkDetail.accuracy) }}</span>
              </div>
              <div class="hw-stat">
                <span class="hw-stat-label">错题数</span>
                <span class="hw-stat-value">{{ homeworkDetail.wrong_count }}</span>
              </div>
            </div>
            <div class="hw-notes" v-if="homeworkDetail.notes">{{ homeworkDetail.notes }}</div>
            <ul class="hw-questions" v-if="homeworkDetail.questions.length">
              <li v-for="q in homeworkDetail.questions" :key="q">{{ q }}</li>
            </ul>
          </div>
          <el-empty v-else description="请选择作业" :image-size="50" />
        </div>
      </el-aside>

      <!-- ── Right: Chat Area ────────────────────── -->
      <el-main class="main-area">
        <div class="chat-shell">
          <!-- chat header -->
          <div class="chat-header">
            <span class="chat-header-icon">💬</span>
            <span>智能助手对话</span>
            <el-tag v-if="selectedStudentId && studentDetail" size="small" type="warning" effect="plain">
              当前学生：{{ studentDetail?.name }}
            </el-tag>
            <el-tag v-else size="small" type="info">未选择学生</el-tag>
          </div>

          <!-- chat messages -->
          <div class="chat-messages" ref="chatContainer">
            <transition-group name="msg-fade">
              <div
                v-for="msg in chatMessages"
                :key="msg.id"
                class="chat-msg"
                :class="msg.role"
              >
                <div class="msg-avatar">
                  {{ msg.role === 'user' ? '👩‍🏫' : '🤖' }}
                </div>
                <div class="msg-body">
                  <div class="msg-bubble">
                    <div class="msg-text" v-text="msg.text"></div>
                  </div>

                  <!-- agent response card -->
                  <div v-if="msg.response && msg.response.status === 'success'" class="agent-card">
                    <div class="agent-card-header">
                      <span class="agent-card-icon">📊</span>
                      {{ msg.response.title }}
                    </div>

                    <!-- sections -->
                    <div
                      v-for="sec in msg.response.sections"
                      :key="sec.name"
                      class="agent-section"
                    >
                      <div class="agent-section-name">{{ sec.name }}</div>
                      <ul class="agent-section-items">
                        <li v-for="item in sec.items" :key="item">{{ item }}</li>
                      </ul>
                    </div>

                    <!-- evidence -->
                    <div v-if="msg.response.evidence.length" class="agent-evidence">
                      <div class="agent-evidence-title">📌 数据依据</div>
                      <ul>
                        <li v-for="e in msg.response.evidence" :key="e">{{ e }}</li>
                      </ul>
                    </div>

                    <!-- warnings -->
                    <div v-if="msg.response.warnings.length" class="agent-warnings">
                      <div class="agent-warnings-title">⚠️ 提示</div>
                      <ul>
                        <li v-for="w in msg.response.warnings" :key="w">{{ w }}</li>
                      </ul>
                    </div>

                    <!-- actions -->
                    <div v-if="msg.response.available_actions.length" class="agent-actions">
                      <el-tag
                        v-for="act in msg.response.available_actions"
                        :key="act"
                        size="small"
                        class="action-tag"
                      >
                        {{ act === 'copy' ? '📋 复制' : act === 'edit' ? '✏️ 编辑' : act === 'regenerate' ? '🔄 重新生成' : act === 'shorten' ? '📏 缩短' : act === 'change_tone' ? '🎭 换语气' : act }}
                      </el-tag>
                    </div>
                  </div>
                </div>
              </div>
            </transition-group>

            <!-- typing indicator -->
            <div v-if="chatLoading" class="chat-msg agent">
              <div class="msg-avatar">🤖</div>
              <div class="msg-body">
                <div class="msg-bubble thinking">
                  <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                </div>
              </div>
            </div>
          </div>

          <!-- quick buttons -->
          <div class="quick-buttons">
            <el-button
              v-for="btn in quickButtons"
              :key="btn.label"
              size="small"
              :disabled="chatLoading"
              @click="handleQuickButton(btn.text)"
            >
              {{ btn.label }}
            </el-button>
          </div>

          <!-- chat input -->
          <div class="chat-input-row">
            <el-input
              v-model="chatInput"
              placeholder="输入你的问题，例如：帮我总结一下这个学生最近一周的学习情况..."
              size="large"
              :disabled="chatLoading"
              @keyup.enter="sendMessage"
              class="chat-input"
            >
              <template #suffix>
                <el-button
                  type="primary"
                  :icon="chatLoading ? 'Loading' : 'Promotion'"
                  :loading="chatLoading"
                  @click="sendMessage"
                  circle
                />
              </template>
            </el-input>
          </div>
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

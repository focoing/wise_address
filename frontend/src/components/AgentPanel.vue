<template>
  <section class="panel agent-panel">
    <div class="panel-head agent-head">
      <div class="panel-title">
        <Bot :size="18" />
        <h2>智能体对话</h2>
      </div>
      <nav class="panel-actions" aria-label="对话导航">
        <RouterLink class="detail-link" to="/history">历史</RouterLink>
        <RouterLink
          class="detail-link"
          :class="{ disabled: !store.currentSessionId }"
          :to="store.currentSessionId ? `/history/${store.currentSessionId}` : '/'"
          @click="guardDetail"
        >
          详情
        </RouterLink>
      </nav>
    </div>

    <div class="messages" aria-live="polite">
      <article v-for="(message, index) in store.messages" :key="index" :class="['message', message.role]">
        <MessageContent v-if="message.content" :content="message.content" />
        <span v-else class="thinking">正在分析<span class="loading-dot"></span></span>
      </article>
    </div>

    <form class="chat-form" @submit.prevent="submit">
      <div class="chat-input-wrap">
        <input
          v-model="question"
          :disabled="store.loading"
          aria-label="智能体问题"
          placeholder="询问当前点位的选址潜力、风险或优化动作"
        />
        <button
          class="voice-btn"
          type="button"
          :class="{ active: listening }"
          :title="listening ? '停止语音输入' : '语音输入'"
          @click="toggleVoice"
        >
          <Mic :size="16" />
        </button>
      </div>
      <button :disabled="store.loading || !question.trim()" type="submit" title="发送">
        <span v-if="store.loading" class="spinner" aria-label="正在发送"></span>
        <SendHorizontal v-else :size="18" />
      </button>
    </form>
    <p v-if="store.error" class="error-line" role="alert">{{ store.error }}</p>
  </section>
</template>

<script setup lang="ts">
import { Bot, Mic, SendHorizontal } from 'lucide-vue-next'
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { streamAgent } from '../api'
import MessageContent from './MessageContent.vue'
import { moduleLabels, useWorkspaceStore } from '../store'

const store = useWorkspaceStore()
const question = ref('')
const listening = ref(false)
let recognition: any

async function submit() {
  const text = question.value.trim()
  if (!text) return
  const inferredBusinessType = inferBusinessType(text)
  const scenario = {
    ...store.scenario,
    businessType: inferredBusinessType || store.scenario.businessType.trim()
  }
  if (inferredBusinessType) {
    store.scenario.businessType = inferredBusinessType
  }
  store.error = ''
  store.loading = true
  store.pushMessage('user', `${moduleLabels[store.activeModule]}：${text}`)
  question.value = ''
  try {
    const payload = {
      module: store.activeModule,
      location: store.location,
      scenario,
      question: text,
      storeMetrics: store.activeModule === 'store_diagnosis' ? store.storeMetrics : undefined
    }
    const assistantIndex = store.messages.length
    store.pushMessage('assistant', '正在分析...')
    let streamedAnswer = ''
    let usedModel = ''
    await streamAgent(payload, {
      onAnalysis(data) {
        usedModel = data.usedModel
        store.lastResult = {
          answer: '',
          analysis: data.analysis,
          usedModel: data.usedModel,
          fallback: false
        }
      },
      onStage(data) {
        if (data.label) {
          store.messages[assistantIndex].content = `${data.label}……`
        }
      },
      onDelta(text) {
        streamedAnswer += text
        store.messages[assistantIndex].content = streamedAnswer
      },
      onDone(data) {
        store.setAgentResult({
          answer: data.answer || streamedAnswer,
          analysis: store.lastResult!.analysis,
          usedModel: data.usedModel || usedModel,
          fallback: data.fallback,
          sessionId: data.sessionId,
          turnId: data.turnId
        })
        store.messages[assistantIndex].content = data.answer || streamedAnswer
      }
    })
  } catch (err) {
    store.error = err instanceof Error ? err.message : String(err)
    store.pushMessage('assistant', '分析请求失败，请检查后端服务、高德配置或网络连接。')
  } finally {
    store.loading = false
  }
}

function guardDetail(event: MouseEvent) {
  if (!store.currentSessionId) {
    event.preventDefault()
    store.error = '请先发起一次智能体分析，再查看详情。'
  }
}

function inferBusinessType(text: string) {
  const normalized = text.replace(/\s+/g, '')
  const patterns = [
    /开(?:一家|一个|一间|个|间)?([^，。！？?,\s]{1,24}?)(?:吗|么|呢|[，。！？?,]|$)/,
    /经营([^，。！？?,\s]{1,24}?)(?:吗|么|呢|[，。！？?,]|$)/,
    /做([^，。！？?,\s]{1,24}?)(?:吗|么|呢|[，。！？?,]|$)/,
    /适合(?:开)?(?:一家|一个|一间|个|间)?([^，。！？?,\s]{1,24}?)(?:吗|么|呢|[，。！？?,]|$)/
  ]
  for (const pattern of patterns) {
    const matched = normalized.match(pattern)
    const businessType = cleanBusinessType(matched?.[1] || '')
    if (businessType) return businessType
  }
  return ''
}

function cleanBusinessType(value: string) {
  return value
    .replace(/^(一家|一个|一间|个|间|开)/, '')
    .replace(/(合适|适合|可以|可行|怎么样|如何|好不好|行不行)$/g, '')
    .replace(/[？?，。！？!\s]/g, '')
    .trim()
}

function toggleVoice() {
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) {
    store.error = '当前浏览器不支持语音识别。'
    return
  }
  if (listening.value) {
    recognition?.stop()
    listening.value = false
    return
  }
  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = false
  recognition.onresult = (event: any) => {
    question.value = event.results[0][0].transcript
  }
  recognition.onend = () => {
    listening.value = false
  }
  listening.value = true
  recognition.start()
}
</script>

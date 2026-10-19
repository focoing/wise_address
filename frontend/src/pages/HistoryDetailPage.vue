<template>
  <main class="history-page">
    <header class="history-header">
      <div>
        <h1>{{ detail?.session.title || '历史详情' }}</h1>
        <p v-if="detail">{{ moduleLabels[detail.session.module] }} · {{ detail.session.address }}</p>
      </div>
      <div class="history-actions">
        <RouterLink class="nav-button" to="/">返回工作台</RouterLink>
        <RouterLink class="nav-button" to="/history">历史列表</RouterLink>
      </div>
    </header>

    <section v-if="loading" class="panel detail-panel">正在加载详情...</section>
    <section v-else-if="error" class="panel detail-panel error-line">{{ error }}</section>
    <section v-else-if="detail" class="detail-layout">
      <aside class="panel session-summary">
        <h2>会话信息</h2>
        <dl>
          <dt>模块</dt>
          <dd>{{ moduleLabels[detail.session.module] }}</dd>
          <dt>地址</dt>
          <dd>{{ detail.session.address }}</dd>
          <dt>坐标</dt>
          <dd>{{ detail.session.lng.toFixed(5) }}, {{ detail.session.lat.toFixed(5) }}</dd>
          <dt>问答次数</dt>
          <dd>{{ detail.session.turnCount }}</dd>
          <dt>更新时间</dt>
          <dd>{{ formatTime(detail.session.updatedAt) }}</dd>
        </dl>
      </aside>

      <section class="turns">
        <article v-for="(turn, index) in detail.turns" :key="turn.id" class="panel turn-card">
          <div class="turn-head">
            <h2>第 {{ index + 1 }} 轮问答</h2>
            <span>{{ formatTime(turn.createdAt) }}</span>
          </div>
          <div class="turn-chat">
            <div class="message user"><MessageContent :content="turn.question" /></div>
            <div class="message assistant"><MessageContent :content="turn.answer" /></div>
          </div>
          <div class="scenario-snapshot">
            <span>业态：{{ turn.request.scenario.businessType || '未指定' }}</span>
            <span>半径：{{ turn.request.scenario.radius }}m</span>
            <span>预算：{{ turn.request.scenario.budgetLevel }}</span>
            <span>客群：{{ turn.request.scenario.targetCustomers || '未指定' }}</span>
          </div>
          <AnalysisDetail :analysis="turn.analysis" />
        </article>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import AnalysisDetail from '../components/AnalysisDetail.vue'
import MessageContent from '../components/MessageContent.vue'
import { getHistorySession } from '../api'
import { moduleLabels } from '../store'
import type { HistorySessionDetail } from '../types'

const props = defineProps<{
  sessionId: string
}>()

const detail = ref<HistorySessionDetail | null>(null)
const loading = ref(false)
const error = ref('')

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    detail.value = await getHistorySession(props.sessionId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN')
}
</script>

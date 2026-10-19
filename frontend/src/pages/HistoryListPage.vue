<template>
  <main class="history-page">
    <header class="history-header">
      <div>
        <h1>历史记录</h1>
        <p>查看不同点位、模块和问答对应的分析结果。</p>
      </div>
      <RouterLink class="nav-button" to="/">返回工作台</RouterLink>
    </header>

    <section class="history-list">
      <div v-if="loading" class="empty-state">正在加载历史记录...</div>
      <div v-else-if="error" class="error-line">{{ error }}</div>
      <div v-else-if="sessions.length === 0" class="empty-state">暂无历史记录，先在工作台发起一次智能体分析。</div>

      <article v-for="session in sessions" v-else :key="session.id" class="history-card">
        <RouterLink class="history-card-main" :to="`/history/${session.id}`">
          <div class="history-card-title">
            <strong>{{ session.title }}</strong>
            <span>{{ moduleLabels[session.module] }}</span>
          </div>
          <p>{{ session.address || `${session.lng.toFixed(5)}, ${session.lat.toFixed(5)}` }}</p>
          <p>最近问题：{{ session.latestQuestion }}</p>
          <div class="history-meta">
            <span>问答 {{ session.turnCount }} 次</span>
            <span v-if="session.latestScore !== undefined">评分 {{ session.latestScore }}</span>
            <span>{{ formatTime(session.updatedAt) }}</span>
          </div>
        </RouterLink>
        <button class="delete-button" type="button" @click="remove(session.id)">删除</button>
      </article>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { deleteHistorySession, listHistorySessions } from '../api'
import { moduleLabels } from '../store'
import type { HistorySessionSummary } from '../types'

const sessions = ref<HistorySessionSummary[]>([])
const loading = ref(false)
const error = ref('')

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    sessions.value = await listHistorySessions()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function remove(sessionId: string) {
  error.value = ''
  try {
    await deleteHistorySession(sessionId)
    sessions.value = sessions.value.filter((session) => session.id !== sessionId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN')
}
</script>

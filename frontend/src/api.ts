import axios from 'axios'
import type { AgentResponse, AnalysisRequest, HistorySessionDetail, HistorySessionSummary } from './types'

export const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

export async function getPublicConfig(): Promise<{ mapProvider: string; amapKey: string; defaultCity: string }> {
  const { data } = await api.get('/config/public')
  return data
}

export async function reverseGeo(lng: number, lat: number) {
  const { data } = await api.get('/geo/reverse', { params: { lng, lat } })
  return data
}

export async function askAgent(payload: AnalysisRequest): Promise<AgentResponse> {
  const { data } = await api.post('/agent/chat', payload)
  return data
}

export async function streamAgent(
  payload: AnalysisRequest,
  handlers: {
    onAnalysis: (data: Pick<AgentResponse, 'analysis' | 'usedModel'>) => void
    onDelta: (text: string) => void
    onDone: (data: Omit<AgentResponse, 'analysis'>) => void
  }
): Promise<void> {
  const response = await fetch('/api/agent/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!response.ok || !response.body) {
    throw new Error(`流式请求失败：${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''
    for (const eventText of events) {
      handleSseEvent(eventText, handlers)
    }
  }
  if (buffer.trim()) {
    handleSseEvent(buffer, handlers)
  }
}

function handleSseEvent(
  eventText: string,
  handlers: {
    onAnalysis: (data: Pick<AgentResponse, 'analysis' | 'usedModel'>) => void
    onDelta: (text: string) => void
    onDone: (data: Omit<AgentResponse, 'analysis'>) => void
  }
) {
  const event = eventText
    .split('\n')
    .find((line) => line.startsWith('event:'))
    ?.replace('event:', '')
    .trim()
  const dataLine = eventText
    .split('\n')
    .find((line) => line.startsWith('data:'))
    ?.replace('data:', '')
    .trim()
  if (!event || !dataLine) return
  const data = JSON.parse(dataLine)
  if (event === 'analysis') handlers.onAnalysis(data)
  if (event === 'delta') handlers.onDelta(data.text || '')
  if (event === 'done') handlers.onDone(data)
}

export async function listHistorySessions(): Promise<HistorySessionSummary[]> {
  const { data } = await api.get('/history/sessions')
  return data
}

export async function getHistorySession(sessionId: string): Promise<HistorySessionDetail> {
  const { data } = await api.get(`/history/sessions/${sessionId}`)
  return data
}

export async function deleteHistorySession(sessionId: string): Promise<void> {
  await api.delete(`/history/sessions/${sessionId}`)
}

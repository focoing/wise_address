import { defineStore } from 'pinia'
import type { AgentResponse, LocationState, ModuleKey, Scenario, StoreMetrics } from './types'

export const moduleLabels: Record<ModuleKey, string> = {
  site_selection: '品牌新店精准选址',
  store_diagnosis: '存量门店优化诊断',
  ecosystem_planning: '商业生态规划',
  regional_potential: '区域商业潜力评估'
}

export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    activeModule: 'site_selection' as ModuleKey,
    location: {
      lng: 121.4737,
      lat: 31.2304,
      address: '上海市人民广场',
      district: '黄浦区'
    } as LocationState,
    scenario: {
      businessType: '',
      radius: 1200,
      budgetLevel: '中',
      rentSensitivity: 50,
      competitorTolerance: 45,
      targetCustomers: ''
    } as Scenario,
    storeMetrics: {
      monthlyRevenue: 260000,
      monthlyRent: 52000,
      dailyOrders: 420,
      conversionRate: 0.14
    } as StoreMetrics,
    messages: [
      {
        role: 'assistant',
        content: '选择地图位置和业务模块后，输入问题即可生成选址分析。'
      }
    ] as Array<{ role: 'user' | 'assistant'; content: string }>,
    lastResult: null as AgentResponse | null,
    currentSessionId: '',
    loading: false,
    error: ''
  }),
  actions: {
    setLocation(location: LocationState) {
      this.location = { ...this.location, ...location }
    },
    setModule(module: ModuleKey) {
      this.activeModule = module
    },
    pushMessage(role: 'user' | 'assistant', content: string) {
      this.messages.push({ role, content })
    },
    setAgentResult(result: AgentResponse) {
      this.lastResult = result
      this.currentSessionId = result.sessionId || this.currentSessionId
    }
  }
})

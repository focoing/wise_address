export type ModuleKey = 'site_selection' | 'store_diagnosis' | 'ecosystem_planning' | 'regional_potential'

export interface LocationState {
  lng: number
  lat: number
  address?: string
  district?: string
}

export interface Scenario {
  businessType: string
  radius: number
  budgetLevel: string
  rentSensitivity: number
  competitorTolerance: number
  targetCustomers: string
}

export interface StoreMetrics {
  monthlyRevenue?: number
  monthlyRent?: number
  dailyOrders?: number
  conversionRate?: number
}

export interface AnalysisRequest {
  module: ModuleKey
  location: LocationState
  scenario: Scenario
  question: string
  storeMetrics?: StoreMetrics
}

export interface PoiSummary {
  total: number
  byCategory: Record<string, number>
  topPois: Array<{ id?: string; name: string; type: string; address?: string; distance?: number; location?: string }>
  radius: number
  estimated: boolean
}

export interface AnalysisResponse {
  module: ModuleKey
  score: number
  dimensions: Record<string, number>
  poiSummary: PoiSummary
  charts: Record<string, unknown>
  recommendation: string
  actions: string[]
  risks: string[]
  evidence: string[]
  estimatedFields: string[]
  alternatives: AlternativeRecommendation[]
}

export interface AlternativeRecommendation {
  title: string
  type: 'business_type' | 'operation' | 'location_condition' | string
  reason: string
  steps: string[]
  expectedImpact: string
}

export interface AgentResponse {
  answer: string
  analysis: AnalysisResponse
  usedModel: string
  fallback: boolean
  sessionId?: string
  turnId?: string
}

export interface HistorySessionSummary {
  id: string
  title: string
  module: ModuleKey
  address: string
  district?: string
  lng: number
  lat: number
  latestQuestion: string
  latestScore?: number
  turnCount: number
  createdAt: string
  updatedAt: string
}

export interface HistoryTurn {
  id: string
  sessionId: string
  question: string
  answer: string
  request: AnalysisRequest
  analysis: AnalysisResponse
  usedModel: string
  fallback: boolean
  createdAt: string
}

export interface HistorySessionDetail {
  session: HistorySessionSummary
  turns: HistoryTurn[]
}

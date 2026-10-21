from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AnalysisModule(str, Enum):
    site_selection = "site_selection"
    store_diagnosis = "store_diagnosis"
    ecosystem_planning = "ecosystem_planning"
    regional_potential = "regional_potential"


class Location(BaseModel):
    lng: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)
    address: str | None = None
    district: str | None = None


class Scenario(BaseModel):
    businessType: str = ""
    radius: int = Field(default=1200, ge=300, le=5000)
    budgetLevel: str = "中"
    rentSensitivity: int = Field(default=50, ge=0, le=100)
    competitorTolerance: int = Field(default=45, ge=0, le=100)
    targetCustomers: str = ""


class StoreMetrics(BaseModel):
    monthlyRevenue: float | None = Field(default=None, ge=0)
    monthlyRent: float | None = Field(default=None, ge=0)
    dailyOrders: int | None = Field(default=None, ge=0)
    conversionRate: float | None = Field(default=None, ge=0, le=1)


class AnalysisRequest(BaseModel):
    module: AnalysisModule
    location: Location
    scenario: Scenario = Field(default_factory=Scenario)
    question: str = ""
    storeMetrics: StoreMetrics | None = None


class PoiItem(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    address: str = ""
    distance: int | None = None
    location: str = ""


class PointSample(BaseModel):
    label: str = ""
    lng: float
    lat: float
    radius: int
    total: int
    byCategory: dict[str, int] = Field(default_factory=dict)


class PoiSummary(BaseModel):
    total: int
    byCategory: dict[str, int]
    topPois: list[PoiItem]
    radius: int
    estimated: bool = False
    competitorCount: int = 0
    samplePoints: list[PointSample] = Field(default_factory=list)


class AlternativeRecommendation(BaseModel):
    title: str
    type: str
    reason: str
    steps: list[str]
    expectedImpact: str


class AnalysisResponse(BaseModel):
    module: AnalysisModule
    score: int
    dimensions: dict[str, int]
    poiSummary: PoiSummary
    charts: dict[str, Any]
    recommendation: str
    actions: list[str]
    risks: list[str]
    evidence: list[str]
    estimatedFields: list[str]
    alternatives: list[AlternativeRecommendation] = Field(default_factory=list)
    moduleFindings: dict[str, Any] | None = None


class AgentTrace(BaseModel):
    dataAgent: str = "fallback"  # ok | fallback
    analyst: str = "fallback"  # ok | fallback
    reviewer: str = "skipped"  # ok | revise | skipped
    retrievalNotes: str = ""
    reviewerNotes: str = ""


class AgentResponse(BaseModel):
    answer: str
    analysis: AnalysisResponse
    usedModel: str
    fallback: bool = False
    sessionId: str | None = None
    turnId: str | None = None
    agentTrace: AgentTrace | None = None


class HistorySessionSummary(BaseModel):
    id: str
    title: str
    module: AnalysisModule
    address: str
    district: str | None = None
    lng: float
    lat: float
    latestQuestion: str
    latestScore: int | None = None
    turnCount: int
    createdAt: str
    updatedAt: str


class HistoryTurn(BaseModel):
    id: str
    sessionId: str
    question: str
    answer: str
    request: AnalysisRequest
    analysis: AnalysisResponse
    usedModel: str
    fallback: bool
    createdAt: str


class HistorySessionDetail(BaseModel):
    session: HistorySessionSummary
    turns: list[HistoryTurn]

<template>
  <section class="panel scenario-panel">
    <div class="panel-head">
      <div class="panel-title">
        <SlidersHorizontal :size="18" />
        <h2>场景模拟</h2>
      </div>
    </div>
    <div class="form-grid">
      <label>
        <span>目标业态</span>
        <input v-model="store.scenario.businessType" placeholder="可留空，系统会优先从问题中识别" />
      </label>
      <label>
        <span>预算等级</span>
        <select v-model="store.scenario.budgetLevel">
          <option>低</option>
          <option>中</option>
          <option>高</option>
        </select>
      </label>
      <label>
        <span>辐射半径 {{ store.scenario.radius }}m</span>
        <input v-model.number="store.scenario.radius" max="5000" min="300" step="100" type="range" />
      </label>
      <label>
        <span>租金敏感度 {{ store.scenario.rentSensitivity }}</span>
        <input v-model.number="store.scenario.rentSensitivity" max="100" min="0" type="range" />
      </label>
      <label>
        <span>竞品容忍度 {{ store.scenario.competitorTolerance }}</span>
        <input v-model.number="store.scenario.competitorTolerance" max="100" min="0" type="range" />
      </label>
      <label>
        <span>目标客群</span>
        <input v-model="store.scenario.targetCustomers" placeholder="可选，例如办公白领、社区居民" />
      </label>
    </div>
    <div v-if="store.activeModule === 'store_diagnosis'" class="store-metrics">
      <label>
        <span>月营收</span>
        <input v-model.number="store.storeMetrics.monthlyRevenue" type="number" />
      </label>
      <label>
        <span>月租金</span>
        <input v-model.number="store.storeMetrics.monthlyRent" type="number" />
      </label>
      <label>
        <span>日订单</span>
        <input v-model.number="store.storeMetrics.dailyOrders" type="number" />
      </label>
      <label>
        <span>转化率</span>
        <input v-model.number="store.storeMetrics.conversionRate" max="1" min="0" step="0.01" type="number" />
      </label>
    </div>
  </section>
</template>

<script setup lang="ts">
import { SlidersHorizontal } from 'lucide-vue-next'
import { useWorkspaceStore } from '../store'

const store = useWorkspaceStore()
</script>

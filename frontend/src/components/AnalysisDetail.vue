<template>
  <div class="analysis-detail">
    <section class="score-row">
      <div class="score">{{ analysis.score }}</div>
      <div>
        <strong>综合潜力评分</strong>
        <p>{{ analysis.recommendation }}</p>
      </div>
    </section>

    <div class="result-lists priority-lists">
      <section class="result-section risk-section">
        <h3>风险提示</h3>
        <ul>
          <li v-for="item in analysis.risks" :key="item">{{ item }}</li>
        </ul>
      </section>
      <section class="result-section">
        <h3>实施步骤</h3>
        <ol>
          <li v-for="item in analysis.actions" :key="item">{{ item }}</li>
        </ol>
      </section>
      <section class="result-section">
        <h3>关键依据</h3>
        <ul>
          <li v-for="item in analysis.evidence" :key="item">{{ item }}</li>
        </ul>
      </section>
    </div>

    <div class="charts">
      <ChartBox title="维度雷达" :option="radarOption" />
      <ChartBox title="周边业态" :option="barOption" />
      <ChartBox title="生态结构" :option="pieOption" />
    </div>

    <section v-if="analysis.alternatives?.length" class="alternatives">
      <h3>替代推荐方案</h3>
      <article v-for="item in analysis.alternatives" :key="item.title" class="alternative-card">
        <div class="alternative-head">
          <strong>{{ item.title }}</strong>
          <span>{{ typeLabel(item.type) }}</span>
        </div>
        <p>{{ item.reason }}</p>
        <p><b>预期改善：</b>{{ item.expectedImpact }}</p>
        <ol>
          <li v-for="step in item.steps" :key="step">{{ step }}</li>
        </ol>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ChartBox from './ChartBox.vue'
import type { AnalysisResponse } from '../types'

const props = defineProps<{
  analysis: AnalysisResponse
}>()

const radarOption = computed(() => {
  const dimensions = props.analysis.dimensions || {}
  const names = Object.keys(dimensions)
  return {
    radar: {
      indicator: names.map((name) => ({ name, max: 100 })),
      radius: '58%',
      center: ['50%', '52%']
    },
    series: [{ type: 'radar', data: [{ value: Object.values(dimensions), name: '评分' }], areaStyle: {} }]
  }
})

const barOption = computed(() => {
  const summary = props.analysis.poiSummary
  return {
    xAxis: { type: 'category', data: Object.keys(summary?.byCategory || {}) },
    yAxis: { type: 'value' },
    grid: { left: 36, right: 20, top: 22, bottom: 46, containLabel: true },
    series: [{ type: 'bar', data: Object.values(summary?.byCategory || {}), itemStyle: { borderRadius: 4 } }]
  }
})

const pieOption = computed(() => {
  const summary = props.analysis.poiSummary
  return {
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '66%'],
        center: ['50%', '52%'],
        data: Object.entries(summary?.byCategory || {}).map(([name, value]) => ({ name, value }))
      }
    ]
  }
})

function typeLabel(type: string) {
  const labels: Record<string, string> = {
    business_type: '业态替代',
    operation: '经营策略',
    location_condition: '选址条件'
  }
  return labels[type] || type
}
</script>

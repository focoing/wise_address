<template>
  <section class="panel insight-panel">
    <div class="panel-head">
      <div class="panel-title">
        <BarChart3 :size="18" />
        <h2>分析结果</h2>
      </div>
      <span v-if="result?.fallback" class="badge">本地兜底</span>
    </div>
    <div v-if="!analysis" class="empty-state">提交问题后，这里会展示评分、风险、行动建议和支撑图表。</div>

    <AnalysisDetail v-if="analysis" :analysis="analysis" />
  </section>
</template>

<script setup lang="ts">
import { BarChart3 } from 'lucide-vue-next'
import { computed } from 'vue'
import AnalysisDetail from './AnalysisDetail.vue'
import { useWorkspaceStore } from '../store'

const store = useWorkspaceStore()
const result = computed(() => store.lastResult)
const analysis = computed(() => store.lastResult?.analysis)
</script>

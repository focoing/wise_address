<template>
  <div class="chart-box">
    <h3>{{ title }}</h3>
    <div ref="chartEl" class="chart"></div>
  </div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  title: string
  option: Record<string, unknown>
}>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (chartEl.value) {
    chart = echarts.init(chartEl.value)
    chart.setOption(props.option)
    resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(chartEl.value)
    window.addEventListener('resize', resize)
    nextTick(resize)
  }
})

watch(
  () => props.option,
  (option) => {
    chart?.setOption(option, true)
  },
  { deep: true }
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  resizeObserver?.disconnect()
  chart?.dispose()
})

function resize() {
  chart?.resize()
}
</script>

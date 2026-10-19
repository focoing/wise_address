<template>
  <main class="shell">
    <section class="map-pane">
      <header class="topbar">
        <div>
          <h1>商枢智能体</h1>
          <p>{{ locationLabel }}</p>
        </div>
        <div class="module-tabs" role="tablist">
          <button
            v-for="item in modules"
            :key="item.key"
            :class="{ active: store.activeModule === item.key }"
            type="button"
            @click="store.setModule(item.key)"
          >
            <component :is="item.icon" :size="16" />
            <span>{{ item.label }}</span>
          </button>
        </div>
      </header>

      <MapPanel />
    </section>

    <aside ref="sidePaneEl" class="side-pane" :style="sidePaneStyle">
      <ScenarioPanel />
      <button
        class="resize-handle"
        type="button"
        title="拖动调整场景模拟与智能体对话高度"
        @pointerdown="startResize"
      >
        <span></span>
      </button>
      <AgentPanel />
      <InsightPanel />
    </aside>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Building2, ChartNoAxesCombined, MapPinned, Store } from 'lucide-vue-next'
import AgentPanel from '../components/AgentPanel.vue'
import InsightPanel from '../components/InsightPanel.vue'
import MapPanel from '../components/MapPanel.vue'
import ScenarioPanel from '../components/ScenarioPanel.vue'
import { moduleLabels, useWorkspaceStore } from '../store'
import type { ModuleKey } from '../types'

const store = useWorkspaceStore()
const sidePaneEl = ref<HTMLElement | null>(null)
const scenarioHeight = ref(260)

const modules: Array<{ key: ModuleKey; label: string; icon: unknown }> = [
  { key: 'site_selection', label: moduleLabels.site_selection, icon: MapPinned },
  { key: 'store_diagnosis', label: moduleLabels.store_diagnosis, icon: Store },
  { key: 'ecosystem_planning', label: moduleLabels.ecosystem_planning, icon: Building2 },
  { key: 'regional_potential', label: moduleLabels.regional_potential, icon: ChartNoAxesCombined }
]

const locationLabel = computed(() => {
  const { address, lng, lat } = store.location
  return address || `${lng.toFixed(5)}, ${lat.toFixed(5)}`
})

const sidePaneStyle = computed(() => ({
  '--scenario-height': `${scenarioHeight.value}px`
}))

function startResize(event: PointerEvent) {
  const pane = sidePaneEl.value
  if (!pane || window.matchMedia('(max-width: 1180px)').matches) return

  const startY = event.clientY
  const startHeight = scenarioHeight.value
  const paneHeight = pane.getBoundingClientRect().height
  const minScenario = 190
  const maxScenario = Math.max(minScenario, paneHeight - 520)

  const onMove = (moveEvent: PointerEvent) => {
    const next = startHeight + moveEvent.clientY - startY
    scenarioHeight.value = Math.min(maxScenario, Math.max(minScenario, next))
  }

  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    document.body.classList.remove('is-resizing')
  }

  document.body.classList.add('is-resizing')
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}
</script>

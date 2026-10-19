<template>
  <div class="map-wrap">
    <div ref="mapEl" class="map-canvas"></div>
    <div v-if="loading" class="map-loading">地图加载中...</div>
    <div class="map-tools">
      <button type="button" title="放大" @click="zoomIn"><ZoomIn :size="18" /></button>
      <button type="button" title="缩小" @click="zoomOut"><ZoomOut :size="18" /></button>
      <button type="button" title="回到上海" @click="resetCenter"><LocateFixed :size="18" /></button>
    </div>
    <div class="map-status">
      <MapPin :size="16" />
      <span>{{ store.location.lng.toFixed(5) }}, {{ store.location.lat.toFixed(5) }}</span>
    </div>
    <div v-if="error" class="map-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import AMapLoader from '@amap/amap-jsapi-loader'
import { LocateFixed, MapPin, ZoomIn, ZoomOut } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'
import { getPublicConfig, reverseGeo } from '../api'
import { useWorkspaceStore } from '../store'

const store = useWorkspaceStore()
const mapEl = ref<HTMLDivElement | null>(null)
const error = ref('')
const loading = ref(true)
let map: any
let marker: any

onMounted(async () => {
  try {
    const config = await getPublicConfig()
    const AMap = await AMapLoader.load({
      key: config.amapKey,
      version: '2.0',
      plugins: ['AMap.Scale', 'AMap.ToolBar', 'AMap.PlaceSearch']
    })
    map = new AMap.Map(mapEl.value, {
      zoom: 14,
      center: [store.location.lng, store.location.lat],
      viewMode: '2D',
      resizeEnable: true,
      mapStyle: 'amap://styles/normal',
      features: ['bg', 'road', 'building', 'point'],
      layers: [new AMap.TileLayer()]
    })
    map.addControl(new AMap.Scale())
    marker = new AMap.Marker({
      position: [store.location.lng, store.location.lat],
      title: '当前分析点位'
    })
    map.add(marker)
    map.on('complete', () => {
      loading.value = false
      map.resize()
    })
    window.setTimeout(() => {
      loading.value = false
      map?.resize()
      map?.setCenter([store.location.lng, store.location.lat])
    }, 900)
    map.on('click', async (event: any) => {
      const lng = event.lnglat.getLng()
      const lat = event.lnglat.getLat()
      marker.setPosition([lng, lat])
      store.setLocation({ lng, lat, address: '正在解析地址...' })
      try {
        const geo = await reverseGeo(lng, lat)
        store.setLocation({ lng, lat, address: geo.address, district: geo.district })
      } catch {
        store.setLocation({ lng, lat, address: '地址解析失败，可继续分析该坐标' })
      }
    })
  } catch (err) {
    error.value = `地图加载失败：${err instanceof Error ? err.message : String(err)}`
    loading.value = false
  }
})

function zoomIn() {
  map?.zoomIn()
}

function zoomOut() {
  map?.zoomOut()
}

function resetCenter() {
  const center = [121.4737, 31.2304]
  map?.setZoomAndCenter(14, center)
  map?.resize()
  marker?.setPosition(center)
  store.setLocation({ lng: 121.4737, lat: 31.2304, address: '上海市人民广场', district: '黄浦区' })
}
</script>

import { createRouter, createWebHistory } from 'vue-router'
import WorkspacePage from './pages/WorkspacePage.vue'
import HistoryListPage from './pages/HistoryListPage.vue'
import HistoryDetailPage from './pages/HistoryDetailPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'workspace', component: WorkspacePage },
    { path: '/history', name: 'history', component: HistoryListPage },
    { path: '/history/:sessionId', name: 'history-detail', component: HistoryDetailPage, props: true }
  ]
})

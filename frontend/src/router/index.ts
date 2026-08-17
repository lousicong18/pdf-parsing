import { createRouter, createWebHistory } from 'vue-router'
import ParserView from '@/views/ParserView.vue'
import HistoryView from '@/views/HistoryView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'parser', component: ParserView },
    { path: '/history', name: 'history', component: HistoryView },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})

export default router

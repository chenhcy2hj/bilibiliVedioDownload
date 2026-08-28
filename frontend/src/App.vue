<script setup>
// 应用根组件：纯白主题 + 任务面板 + 右侧操作区（无 3D）
import { onBeforeUnmount, onMounted } from 'vue'

import { WsClient } from './api/ws'
import CookieBar from './components/CookieBar.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import TaskPanel from './components/TaskPanel.vue'
import UrlForm from './components/UrlForm.vue'
import { bootstrap, handleWsMessage, store } from './store'

let ws = null

onMounted(async () => {
  // 初始数据（caps/cookie/settings/tasks）— WS 未连上时也能工作
  try {
    await bootstrap()
  } catch (e) {
    console.warn('[app] 初始数据加载失败（后端未启动？）', e)
  }

  // WebSocket：连接 + 自动重连 + 快照兜底
  ws = new WsClient({
    onMessage: handleWsMessage,
    onState: (s) => (store.wsState = s),
  })
  ws.connect()
})

onBeforeUnmount(() => ws?.close())
</script>

<template>
  <div class="page">
    <header>
      <h1>Bili<em>Downloader</em></h1>
      <span class="ws" :class="store.wsState">
        {{ store.wsState === 'open' ? '实时连接' : '连接中…' }}
      </span>
    </header>

    <main>
      <section class="left">
        <TaskPanel />
      </section>
      <section class="right">
        <CookieBar />
        <UrlForm />
        <SettingsPanel />
      </section>
    </main>
  </div>
</template>

<style scoped>
.page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 20px 16px 40px;
}
header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
header h1 em {
  font-style: normal;
  color: #2563eb;
}
.ws {
  font-size: 12px;
  color: #94a3b8;
}
.ws.open {
  color: #16a34a;
}
main {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 820px) {
  main {
    grid-template-columns: 1fr;
  }
}
</style>
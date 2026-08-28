// 轻量全局状态（Vue reactive）：任务 / 设置 / Cookie / 能力清单 / WS 状态
import { reactive } from 'vue'

import { api } from './api'

export const store = reactive({
  tasks: [],
  settings: { output_dir: '', audio_format: 'mp3', audio_quality: '192' },
  cookie: { valid: false, uname: null, message: '尚未配置 Cookie', has_cookie_file: false },
  capabilities: [],
  wsState: 'closed', // connecting / open / closed
  authAlert: false, // 有任务因 Cookie 失效而失败 → 引导重新获取
  version: { app: '', ytdlp: '' }, // 关于信息（/api/health）
})

export async function bootstrap() {
  const [caps, cookie, settings, tasks, health] = await Promise.all([
    api.capabilities(),
    api.cookieStatus(),
    api.getSettings(),
    api.listTasks(),
    api.health(),
  ])
  store.capabilities = caps.parsers || []
  store.cookie = cookie
  store.settings = settings
  store.tasks = tasks
  store.version = health
}

export function upsertTask(task) {
  const i = store.tasks.findIndex((t) => t.id === task.id)
  if (i >= 0) store.tasks[i] = task
  else store.tasks.push(task)
}

// WS 事件 → store（后端已做 200ms 进度节流，前端直接写入）
export function handleWsMessage(msg) {
  switch (msg.type) {
    case 'task.snapshot':
      store.tasks = msg.payload.tasks || []
      break
    case 'task.created':
    case 'task.progress':
    case 'task.phase':
    case 'task.done':
    case 'task.canceled':
      upsertTask(msg.payload)
      break
    case 'task.failed':
      upsertTask(msg.payload)
      // Cookie 失效联动：提示重新获取
      if (msg.payload.error_code === 'auth') store.authAlert = true
      break
    default:
      break // 未知类型忽略
  }
}
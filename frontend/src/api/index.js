// REST API 封装：所有后端接口的唯一入口
import { del, get, post, put } from './http'

export const api = {
  // 任务
  createTasks: (urls, opts = {}) => post('/tasks', { urls, ...opts }),
  listTasks: () => get('/tasks'),
  cancelTask: (id) => del(`/tasks/${id}`),
  taskFileUrl: (id) => `/api/tasks/${id}/file`,

  // 能力
  capabilities: () => get('/capabilities'),

  // Cookie
  cookieStatus: () => get('/cookie/status'),
  cookieGuide: () => get('/cookie/guide'),
  submitCookie: (cookie) => post('/cookie', { cookie }),
  acquireCookie: () => post('/cookie/acquire'), // 无感获取：弹出浏览器窗口自动捕获

  // 设置
  getSettings: () => get('/settings'),
  updateSettings: (outputDir) => put('/settings', { output_dir: outputDir }),

  // 版本信息
  health: () => get('/health'),
}
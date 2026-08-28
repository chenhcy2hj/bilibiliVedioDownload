// WebSocket 客户端：自动重连（指数退避）+ 事件分发
// 连接同源 /api/ws（开发模式经 Vite proxy，打包版同源），重连后由后端全量快照补齐状态
const BACKOFF_BASE_MS = 1000
const BACKOFF_MAX_MS = 16000

export class WsClient {
  constructor({ onMessage, onState }) {
    this.onMessage = onMessage || (() => {})
    this.onState = onState || (() => {})
    this.socket = null
    this.closed = false
    this.backoff = BACKOFF_BASE_MS
    this.retryTimer = null
  }

  connect() {
    this.closed = false
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const params = new URLSearchParams(location.search)
    const token = params.get('token')
    const url = `${proto}://${location.host}/api/ws${token ? `?token=${token}` : ''}`
    const socket = new WebSocket(url)
    this.socket = socket
    this.onState('connecting')

    socket.onopen = () => {
      this.backoff = BACKOFF_BASE_MS
      this.onState('open')
    }
    socket.onmessage = (evt) => {
      try {
        this.onMessage(JSON.parse(evt.data))
      } catch (e) {
        // 未知/畸形消息：忽略并告警，不崩溃页面
        console.warn('[ws] 忽略无法解析的消息', e)
      }
    }
    socket.onclose = () => {
      this.onState('closed')
      if (!this.closed) this.scheduleReconnect()
    }
    socket.onerror = () => socket.close()
  }

  scheduleReconnect() {
    const delay = Math.min(this.backoff, BACKOFF_MAX_MS)
    this.backoff *= 2
    this.retryTimer = setTimeout(() => this.connect(), delay)
  }

  close() {
    this.closed = true
    if (this.retryTimer) clearTimeout(this.retryTimer)
    if (this.socket) {
      this.socket.onclose = null
      this.socket.close()
      this.socket = null
    }
    this.onState('closed')
  }
}
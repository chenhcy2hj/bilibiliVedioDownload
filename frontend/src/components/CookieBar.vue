<script setup>
// Cookie 状态条：一键"无感获取"（后端弹出浏览器窗口，登录后自动捕获保存）
// 手动方式（书签脚本 / 粘贴）作为兜底保留在折叠区
import { onBeforeUnmount, ref } from 'vue'

import { api } from '../api'
import { store } from '../store'

const POLL_MS = 3000
const ACQUIRE_TIMEOUT_MS = 300_000 // 与后端 300s 超时对齐

const acquiring = ref(false)
const acquireStatus = ref('') // 正在等待 / 失败原因
const showManual = ref(false)
const paste = ref('')
const message = ref('')
const error = ref('')
const copied = ref(false)
const guide = ref(null)

let pollTimer = null
let acquireDeadline = 0

// ---- 无感获取主流程：POST acquire → 轮询 status 直到结果 ----

async function acquireCookie() {
  error.value = ''
  message.value = ''
  try {
    await api.acquireCookie()
  } catch (e) {
    if (e.code === 'ACQUIRE_IN_PROGRESS') {
      // 已有获取进行中（如刷新页面后），直接进入等待态
    } else {
      error.value = e.message
      return
    }
  }
  acquiring.value = true
  acquireStatus.value = '已弹出浏览器窗口：请在窗口中完成扫码/登录，Cookie 将自动保存（无需复制粘贴）'
  acquireDeadline = Date.now() + ACQUIRE_TIMEOUT_MS
  clearInterval(pollTimer)
  pollTimer = setInterval(pollStatus, POLL_MS)
  await pollStatus()
}

async function pollStatus() {
  let status
  try {
    status = await api.cookieStatus()
  } catch (e) {
    return // 网络抖动，下一轮再试
  }
  if (status.valid) {
    store.cookie = status
    store.authAlert = false
    finishAcquiring()
    message.value = 'Cookie 已自动保存并生效 ✨'
    return
  }
  if (!status.acquiring || Date.now() > acquireDeadline) {
    finishAcquiring()
    acquireStatus.value = status.acquire_message || '获取未完成，请重试'
    return
  }
  // 仍在获取中（后端轮询周期 2s，前端这里无需更新文案）
}

function finishAcquiring() {
  acquiring.value = false
  clearInterval(pollTimer)
  pollTimer = null
}

// ---- 手动方式（兜底）：书签脚本 / 粘贴 ----

async function toggleManual() {
  showManual.value = !showManual.value
  if (showManual.value && !guide.value) {
    try {
      guide.value = await api.cookieGuide()
    } catch (e) {
      error.value = e.message
    }
  }
}

async function copyBookmarklet() {
  if (!guide.value?.bookmarklet) return
  try {
    await navigator.clipboard.writeText(guide.value.bookmarklet)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch (e) {
    error.value = '复制失败，请手动选中脚本复制'
  }
}

async function submitPaste() {
  error.value = ''
  try {
    const status = await api.submitCookie(paste.value.trim())
    store.cookie = status
    store.authAlert = false
    paste.value = ''
    message.value = 'Cookie 已保存并生效'
  } catch (e) {
    error.value = e.message
  }
}

async function refresh() {
  store.cookie = await api.cookieStatus()
  store.authAlert = false
}

onBeforeUnmount(() => clearInterval(pollTimer))
</script>

<template>
  <section class="cookie-bar" :class="store.cookie.valid ? 'ok' : 'bad'">
    <span class="dot" />
    <span class="text">
      <template v-if="store.cookie.valid">
        ✅ Cookie 有效 · 登录用户：{{ store.cookie.uname }}
      </template>
      <template v-else>
        ⚠️ {{ store.cookie.message }}
      </template>
    </span>

    <button class="mini primary" :disabled="acquiring" @click="acquireCookie">
      {{ acquiring ? '获取中…' : '获取 Cookie' }}
    </button>
    <button v-if="store.cookie.has_cookie_file" class="mini ghost" @click="refresh">刷新状态</button>
    <button class="mini ghost" @click="toggleManual">手动方式</button>

    <!-- 无感获取进度 -->
    <p v-if="acquiring" class="notice">
      {{ acquireStatus }}
      <span class="spinner" />
    </p>
    <p v-if="!acquiring && acquireStatus && !store.cookie.valid" class="notice bad">
      {{ acquireStatus }}
    </p>
    <p v-if="store.authAlert" class="alert">
      有任务因 Cookie 失效而失败：
      <button class="mini" @click="acquireCookie">重新获取</button>
    </p>

    <!-- 手动方式（兜底） -->
    <div v-if="showManual" class="manual">
      <div v-if="guide?.bookmarklet" class="bookmark">
        <p class="step">① 复制书签脚本（新建书签时地址粘贴即可）</p>
        <div class="bm-row">
          <button class="mini primary" @click="copyBookmarklet">
            {{ copied ? '已复制 ✓' : '复制书签脚本' }}
          </button>
          <a class="show" @click="() => (guide.showRaw = !guide.showRaw)">展开脚本</a>
        </div>
        <p v-if="guide.showRaw" class="raw">{{ guide.bookmarklet }}</p>
        <p class="step">② 在已登录的 B 站页面点击书签 → 自动回传校验</p>
      </div>
      <div class="paste">
        <textarea v-model="paste" rows="2" placeholder="或手动粘贴 Cookie（F12 → Network → 请求头 Cookie）" />
        <button class="mini primary" @click="submitPaste">提交校验</button>
      </div>
    </div>

    <p v-if="message" class="msg">{{ message }}</p>
    <p v-if="error" class="msg bad">{{ error }}</p>
  </section>
</template>

<style scoped>
.cookie-bar {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgb(15 23 42 / 0.06);
  border-radius: 10px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.cookie-bar.ok {
  border-color: #86efac;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f87171;
}
.cookie-bar.ok .dot {
  background: #4ade80;
}
.text {
  flex: 1;
  font-size: 12px;
  color: #334155;
}
.mini {
  flex: none;
  font-size: 11px;
  background: #1d4ed8;
  color: #fff;
  border: 0;
  border-radius: 6px;
  padding: 5px 10px;
  cursor: pointer;
}
.mini.primary {
  background: #166534;
}
.mini:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.mini.ghost {
  background: transparent;
  color: #64748b;
  border: 1px solid #e2e8f0;
}
.notice {
  width: 100%;
  margin: 0;
  font-size: 12px;
  color: #1d4ed8;
  background: #eff6ff;
  border-radius: 6px;
  padding: 6px 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.notice.bad {
  color: #b91c1c;
  background: #fef2f2;
}
.spinner {
  width: 12px;
  height: 12px;
  flex: none;
  border: 2px solid #3b82f6;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.alert {
  width: 100%;
  margin: 0;
  font-size: 12px;
  color: #b91c1c;
  background: #fef2f2;
  border-radius: 6px;
  padding: 6px 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.manual {
  width: 100%;
  border-top: 1px dashed #e2e8f0;
  padding-top: 8px;
  margin-top: 4px;
}
.step {
  margin: 0 0 6px;
  font-size: 12px;
  color: #64748b;
}
.bm-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.show {
  font-size: 12px;
  color: #2563eb;
  cursor: pointer;
}
.raw {
  margin: 0 0 6px;
  font-size: 10px;
  color: #64748b;
  word-break: break-all;
  max-height: 80px;
  overflow: auto;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 6px;
  border-radius: 6px;
}
.paste {
  width: 100%;
  display: flex;
  gap: 8px;
}
textarea {
  flex: 1;
  background: #f8fafc;
  color: #0f172a;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  resize: vertical;
}
.msg {
  width: 100%;
  font-size: 12px;
  color: #334155;
  margin: 0;
}
.msg.bad {
  color: #f87171;
}
</style>
<script setup>
// 设置面板：下载目录显示与修改
// pywebview 窗口：调用原生目录选择对话框（window.pywebview.api.choose_dir，M6 由 launcher expose）
// 浏览器开发模式：手动输入绝对路径
import { ref } from 'vue'

import { api } from '../api'
import { store } from '../store'

const input = ref('')
const message = ref('')
const error = ref('')
const saving = ref(false)
const hasNativePicker = typeof window !== 'undefined' && !!window.pywebview?.api?.choose_dir

async function chooseDir() {
  message.value = ''
  error.value = ''
  if (hasNativePicker) {
    try {
      const picked = await window.pywebview.api.choose_dir()
      if (picked) input.value = picked
    } catch (e) {
      error.value = '目录选择失败：' + (e?.message || e)
    }
  } else {
    input.value = store.settings.output_dir
  }
}

async function save() {
  saving.value = true
  message.value = ''
  error.value = ''
  try {
    const settings = await api.updateSettings(input.value.trim())
    store.settings = settings
    message.value = '已保存，新任务将输出到新目录'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="panel">
    <h3>设置</h3>
    <div class="line">
      <span class="cur">下载目录：<b>{{ store.settings.output_dir }}</b></span>
      <button class="mini" @click="chooseDir">
        {{ hasNativePicker ? '选择目录…' : '修改' }}
      </button>
    </div>
    <div v-if="input" class="edit">
      <input v-model="input" type="text" placeholder="绝对路径，如 /Users/me/Music" @keyup.enter="save" />
      <button class="mini primary" :disabled="saving" @click="save">保存</button>
    </div>
    <p v-if="message" class="msg ok">{{ message }}</p>
    <p v-if="error" class="msg bad">{{ error }}</p>
    <p class="about">
      BiliDownloader v{{ store.version.version }} · yt-dlp {{ store.version.ytdlp_version }}
    </p>
    <p class="about warn">⚠️ 仅供个人学习使用，风控与合规责任由使用者自行承担</p>
  </section>
</template>

<style scoped>
.line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: #475569;
}
.cur b {
  color: #0f172a;
  font-weight: 500;
  word-break: break-all;
}
.edit {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
input {
  flex: 1;
  background: #f8fafc;
  color: #0f172a;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  font-family: inherit;
}
.mini {
  flex: none;
  font-size: 11px;
  background: #f1f5f9;
  color: #0f172a;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
}
.mini:hover {
  background: #e2e8f0;
}
.mini.primary {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}
.mini.primary:hover {
  background: #1d4ed8;
}
.mini:disabled {
  opacity: 0.5;
}
.msg {
  font-size: 12px;
  margin: 6px 0 0;
}
.msg.ok {
  color: #15803d;
}
.msg.bad {
  color: #b91c1c;
}
.about {
  margin: 10px 0 0;
  font-size: 11px;
  color: #94a3b8;
}
.about.warn {
  color: #b45309;
}
</style>
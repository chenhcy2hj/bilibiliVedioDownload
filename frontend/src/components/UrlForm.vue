<script setup>
// URL 批量提交表单：本地识别链接形态 + 格式选项 + 提交
import { computed, ref } from 'vue'

import { api } from '../api'
import { store } from '../store'

const DEFAULT_PATTERNS = [
  { key: 'standard', label: '标准链接', re: /^https?:\/\/(www\.|m\.)?bilibili\.com\/video\/BV[0-9A-Za-z]{10}/ },
  { key: 'bare', label: '裸BV号', re: /^BV[0-9A-Za-z]{10}$/ },
  { key: 'short', label: '短链', re: /^https?:\/\/b23\.tv\/[0-9A-Za-z]+$/ },
]

// 单次提交链接数上限（与后端 MAX_URLS_PER_BATCH 一致）
const MAX_ROWS = 10

const text = ref('')
const format = ref({ audio_format: 'mp3', audio_quality: '192' })
const submitting = ref(false)
const error = ref('')
const success = ref('')

const urls = computed(() =>
  text.value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean),
)

// 每行识别结果：recognized / unsupported / empty
const rows = computed(() =>
  urls.value.map((u) => {
    const hit = DEFAULT_PATTERNS.find((p) => p.re.test(u))
    return { url: u, ok: !!hit, label: hit?.label || '不支持' }
  }),
)

const validCount = computed(() => rows.value.filter((r) => r.ok).length)

// 超出上限：不阻塞粘贴，仅拦截提交
const overLimit = computed(() => rows.value.length > MAX_ROWS)

async function submit() {
  error.value = ''
  success.value = ''
  const valid = urls.value.filter((u) => DEFAULT_PATTERNS.some((p) => p.re.test(u)))
  if (!valid.length) {
    error.value = '没有可识别的链接'
    return
  }
  submitting.value = true
  try {
    const created = await api.createTasks(valid, format.value)
    success.value = `已创建 ${created.length} 个任务`
    text.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="panel">
    <h3>新建下载任务</h3>
    <textarea
      v-model="text"
      rows="5"
      placeholder="每行一个链接：&#10;https://www.bilibili.com/video/BV1hk4y1W76R/&#10;BV1JRuA6vEvd&#10;https://b23.tv/xxxx"
    />
    <ul v-if="rows.length" class="rows">
      <li v-for="(r, i) in rows" :key="i" :class="r.ok ? 'ok' : 'bad'">
        <span class="tag">{{ r.label }}</span>
        <span class="url">{{ r.url }}</span>
      </li>
    </ul>
    <div class="options">
      <label>格式
        <select v-model="format.audio_format">
          <option value="mp3">MP3</option>
        </select>
      </label>
      <label>码率
        <select v-model="format.audio_quality">
          <option value="128">128k</option>
          <option value="192">192k</option>
          <option value="320">320k</option>
        </select>
      </label>
      <button :disabled="submitting || !validCount || overLimit" @click="submit">
        {{ submitting ? '创建中…' : `创建任务（${validCount}）` }}
      </button>
    </div>
    <p v-if="overLimit" class="msg bad">最多 {{ MAX_ROWS }} 条（当前 {{ rows.length }}），请删减后提交</p>
    <p v-if="success" class="msg ok">{{ success }}</p>
    <p v-if="error" class="msg bad">{{ error }}</p>
  </section>
</template>

<style scoped>
textarea {
  width: 100%;
  box-sizing: border-box;
  background: #f8fafc;
  color: #0f172a;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
  font-size: 13px;
  resize: vertical;
  font-family: inherit;
}
textarea:focus {
  outline: 2px solid #bfdbfe;
  border-color: #60a5fa;
}
.rows {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  max-height: 96px;
  overflow: auto;
  font-size: 12px;
}
.rows li {
  display: flex;
  gap: 6px;
  padding: 2px 0;
}
.tag {
  flex: none;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 11px;
}
.ok .tag {
  background: #dcfce7;
  color: #15803d;
}
.bad .tag {
  background: #fee2e2;
  color: #b91c1c;
}
.url {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #475569;
}
.options {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}
.options label {
  font-size: 12px;
  color: #475569;
}
select {
  background: #f8fafc;
  color: #0f172a;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 4px 6px;
  margin-left: 4px;
  font-family: inherit;
}
button {
  margin-left: auto;
  background: #2563eb;
  color: #fff;
  border: 0;
  border-radius: 8px;
  padding: 8px 14px;
  cursor: pointer;
  font-family: inherit;
}
button:hover:not(:disabled) {
  background: #1d4ed8;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.msg {
  font-size: 12px;
}
.msg.ok {
  color: #15803d;
}
.msg.bad {
  color: #b91c1c;
}
</style>
<script setup>
// 任务面板：名称 + 条形码动态进度条 + 百分比（100% 绿色）
// 注意：active/history 必须是 computed（响应式），否则任务行不会随 store 更新出现
import { computed } from 'vue'

import { api } from '../api'
import { store } from '../store'

const STATUS_LABEL = {
  pending: '排队中',
  parsing: '解析中',
  downloading: '下载中',
  converting: '转码中',
  done: '完成',
  failed: '失败',
  canceled: '已取消',
  interrupted: '中断',
}

// 失败原因 → 建议动作
const ERROR_ADVICE = {
  auth: '建议：点击上方"获取 Cookie"重新获取',
  network: '建议：检查网络后重试',
  convert: '建议：检查 FFmpeg 是否可用 / 输出目录权限',
  not_found: '建议：检查链接或分P 是否存在',
  path: '建议：在"设置"中修改下载目录',
  canceled: '',
}

// 进度：优先使用后端统一计算的 progress（分片下载 total 缺失时也不为 0）
function ratio(t) {
  if (t.progress != null) return Math.min(t.progress, 1)
  if (!t.total || !t.downloaded) return 0
  return Math.min(t.downloaded / t.total, 1)
}

const pct = (t) => Math.round(ratio(t) * 100)

// 100% 即绿色（下载中 100% 也变绿，符合"进度 100% 显示绿色"）
const isFull = (t) => ratio(t) >= 1 || t.status === 'done'

// 名称：优先视频标题，未探测到则回退输入 URL
const name = (t) => t.title || t.input_url

function fmtSpeed(v) {
  if (v == null) return ''
  if (v >= 1048576) return (v / 1048576).toFixed(1) + ' MB/s'
  return Math.round(v / 1024) + ' KB/s'
}

async function cancel(t) {
  try {
    await api.cancelTask(t.id)
  } catch (e) {
    alert(e.message)
  }
}

// 响应式分组：任务列表随 store 更新实时渲染
// 历史 = 全部终态（done/failed/canceled/interrupted）；active 之外的自动归入历史
const ACTIVE_STATUSES = ['pending', 'parsing', 'downloading', 'converting']
const active = computed(() => store.tasks.filter((t) => ACTIVE_STATUSES.includes(t.status)))
const history = computed(() => store.tasks.filter((t) => !ACTIVE_STATUSES.includes(t.status)))
</script>

<template>
  <section class="panel">
    <h3>任务列表 <span class="count">{{ store.tasks.length }}</span></h3>

    <div v-if="store.tasks.length === 0" class="empty">暂无任务，在右侧输入链接开始下载</div>

    <template v-if="active.length">
      <h4 class="group">进行中 {{ active.length }}</h4>
      <ul class="tasks">
        <li v-for="t in active" :key="t.id" class="row">
          <!-- 第一行：徽标 + 名称 + 操作 -->
          <div class="top">
            <span class="badge" :class="t.status">{{ STATUS_LABEL[t.status] }}</span>
            <span class="name" :title="name(t)">{{ name(t) }}</span>
            <button class="mini danger" @click="cancel(t)">取消</button>
          </div>
          <!-- 第二行：名称前缀 + 条形码进度条 + 百分比（100% 绿色） -->
          <div class="barline">
            <div class="barcode" :title="`${pct(t)}%`">
              <div
                class="fill"
                :class="{
                  scan: t.status === 'downloading' && !isFull(t),
                  converting: t.status === 'converting' && !isFull(t),
                  full: isFull(t),
                }"
                :style="{ width: pct(t) + '%' }"
              />
            </div>
            <span class="pct" :class="{ full: isFull(t) }">{{ pct(t) }}%</span>
            <span v-if="t.speed && !isFull(t)" class="speed">{{ fmtSpeed(t.speed) }}</span>
          </div>
        </li>
      </ul>
    </template>

    <template v-if="history.length">
      <h4 class="group">历史 {{ history.length }}</h4>
      <ul class="tasks">
        <li v-for="t in history" :key="t.id" class="row">
          <div class="top">
            <span class="badge" :class="t.status">{{ STATUS_LABEL[t.status] }}</span>
            <span class="name" :title="name(t)">{{ name(t) }}</span>
          </div>
          <div class="barline">
            <div class="barcode">
              <div class="fill" :class="[{ full: t.status === 'done' }, t.status]" :style="{ width: (t.status === 'done' ? 100 : pct(t)) + '%' }" />
            </div>
            <span class="pct" :class="{ full: t.status === 'done' }">
              {{ t.status === 'done' ? '100%' : pct(t) + '%' }}
            </span>
          </div>
          <p v-if="t.error_message" class="err" :title="t.error_message">{{ t.error_message }}</p>
          <p v-if="t.status === 'failed' && ERROR_ADVICE[t.error_code]" class="advice">
            {{ ERROR_ADVICE[t.error_code] }}
          </p>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.count {
  color: #94a3b8;
  font-size: 12px;
}
.group {
  margin: 12px 0 6px;
  font-size: 12px;
  color: #64748b;
}
.empty {
  color: #94a3b8;
  font-size: 13px;
  padding: 10px 0;
}
.tasks {
  list-style: none;
  margin: 0;
  padding: 0;
}
.row {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: #ffffff;
}
.top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.name {
  flex: 1;
  font-size: 13px;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.badge {
  flex: none;
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 999px;
  font-weight: 500;
}
.badge.downloading {
  background: #dbeafe;
  color: #1d4ed8;
}
.badge.converting {
  background: #fef3c7;
  color: #b45309;
}
.badge.done {
  background: #dcfce7;
  color: #15803d;
}
.badge.failed {
  background: #fee2e2;
  color: #b91c1c;
}
.badge.pending,
.badge.parsing {
  background: #f1f5f9;
  color: #475569;
}
.badge.canceled {
  background: #f1f5f9;
  color: #94a3b8;
}
.badge.interrupted {
  background: #f1f5f9;
  color: #64748b;
}

/* ---- 条形码动态进度条 ---- */
.barline {
  display: flex;
  align-items: center;
  gap: 10px;
}
.barcode {
  position: relative;
  flex: 1;
  height: 22px;
  border-radius: 5px;
  background: repeating-linear-gradient(
    90deg,
    #f1f5f9 0px,
    #f1f5f9 4px,
    #ffffff 4px,
    #ffffff 8px
  );
  border: 1px solid #e2e8f0;
  overflow: hidden;
}
.barcode .fill {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  background: repeating-linear-gradient(
    90deg,
    #1d4ed8 0px,
    #1d4ed8 4px,
    #60a5fa 4px,
    #60a5fa 8px,
    #93c5fd 8px,
    #93c5fd 10px
  );
  transition: width 0.25s ease;
}
/* 下载中：条纹滚动（动态条码扫描效果） */
.barcode .fill.scan {
  background-size: 30px 100%;
  animation: barcode-scroll 0.4s linear infinite;
}
@keyframes barcode-scroll {
  from {
    background-position: 0 0;
  }
  to {
    background-position: 30px 0;
  }
}
/* 转码中（未满）：琥珀色 */
.barcode .fill.converting {
  background: repeating-linear-gradient(
    90deg,
    #d97706 0px,
    #d97706 4px,
    #fbbf24 4px,
    #fbbf24 8px
  );
}
/* 进度 100%：绿色（任何状态，含下载/转码完成瞬间） */
.barcode .fill.full {
  background: repeating-linear-gradient(
    90deg,
    #15803d 0px,
    #15803d 4px,
    #4ade80 4px,
    #4ade80 8px
  );
  animation: none;
}
/* 失败/取消/中断：红/灰条码 */
.barcode .fill.failed {
  background: repeating-linear-gradient(90deg, #b91c1c 0px, #b91c1c 4px, #fca5a5 4px, #fca5a5 8px);
}
.barcode .fill.canceled,
.barcode .fill.interrupted {
  background: repeating-linear-gradient(90deg, #94a3b8 0px, #94a3b8 4px, #cbd5e1 4px, #cbd5e1 8px);
}

.pct {
  flex: none;
  font-size: 13px;
  font-weight: 600;
  color: #1d4ed8;
  font-variant-numeric: tabular-nums;
  width: 44px;
  text-align: right;
}
.pct.full {
  color: #15803d;
}
.speed {
  flex: none;
  font-size: 11px;
  color: #2563eb;
}
.err {
  margin: 6px 0 0;
  font-size: 11px;
  color: #b91c1c;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.advice {
  margin: 4px 0 0;
  font-size: 11px;
  color: #b45309;
}
.mini {
  flex: none;
  font-size: 11px;
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  padding: 3px 10px;
  cursor: pointer;
  text-decoration: none;
}
.mini:hover {
  background: #dbeafe;
}
.mini.danger {
  background: #fef2f2;
  color: #b91c1c;
  border-color: #fecaca;
}
.mini.danger:hover {
  background: #fee2e2;
}
</style>
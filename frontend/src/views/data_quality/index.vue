<template>
  <section class="page" data-module="data_quality">
    <header class="page-head">
      <div>
        <h2>流式质检管理</h2>
        <p class="page-desc">维护实时数据流的质量监控规则、窗口统计和异常告警机制。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记质检规则</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出流式质检清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无流式质检数据，可先登记质检规则</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记质检规则</h3>
        <label v-for="field in columns" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>


    <section class="publish-view" data-testid="publish-view">
      <header class="publish-head">
        <h3>指标批次发布视图</h3>
        <span class="page-desc">扫描口径：准备落盘的指标批次能不能发布，取决于同批检查是否已经完成并全部通过。</span>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th>批次编号</th>
            <th>指标批次</th>
            <th>放行状态</th>
            <th>检查进度</th>
            <th>可发布</th>
            <th>阻断原因</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in publishItems"
            :key="String(item['批次编号'])"
            :data-testid="`publish-row-${item['批次编号']}`"
            :data-releasable="String(item['可发布'])"
          >
            <td>{{ item['批次编号'] }}</td>
            <td>{{ item['指标批次'] }}</td>
            <td>{{ item['状态'] }}</td>
            <td>{{ item['检查进度'] }}</td>
            <td>{{ item['可发布'] ? '可发布' : '不可发布' }}</td>
            <td class="gap-cell">
              {{ item['可发布'] ? '—' : blockedText(item) }}
            </td>
          </tr>
          <tr v-if="!publishItems.length">
            <td colspan="6" class="empty-state">暂无待发布的指标批次</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条流式质检记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/data_quality'
const columns = ["规则编号", "关联流", "检查项", "上限阈值", "下限阈值", "告警级别", "统计窗口", "连续异常"]
const actions = ["启用规则", "关闭规则", "确认告警"]
const statuses = ["未启用", "运行中", "已告警", "已关闭"]
const metricNames = ["规则总数", "运行中规则", "已告警规则"]

const rows = ref<Row[]>([])
const publishItems = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const stats = computed(() => [
  { label: metricNames[0], value: total.value },
  { label: metricNames[1], value: rows.value.filter((row) => row.status === statuses[1]).length },
  { label: metricNames[2], value: rows.value.filter((row) => row.status === statuses[statuses.length - 1]).length },
])

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value).toString()
  try {
    const response = await request(`${ENDPOINT}/export?${query}`)
    if (!response.ok) throw new Error('导出失败，请稍后重试')
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = 'data_quality.csv'
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(columns.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST', body: JSON.stringify(createValues.value),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '登记失败')
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('流式质检动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '流式质检操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('质检规则列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await reloadPublishView()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '流式质检列表读取失败'
  }
}

function blockedText(item: Row): string {
  const reasons = item['阻断原因']
  if (Array.isArray(reasons) && reasons.length) return reasons.join('；')
  return String(item['结论'] ?? '缺少放行依据')
}

async function reloadPublishView() {
  try {
    const response = await request(`${ENDPOINT}/publish-view`)
    if (!response.ok) throw new Error('发布视图读取失败')
    const payload = await response.json()
    publishItems.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发布视图读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.publish-view { margin-top: 20px; }
.publish-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
.publish-head h3 { margin: 0; font-size: 15px; }
.publish-view tr[data-releasable='true'] td:nth-child(5) { color: #166534; font-weight: 600; }
.publish-view tr[data-releasable='false'] td:nth-child(5) { color: #b45309; }
.gap-cell { max-width: 360px; font-size: 12px; color: #475569; }
</style>

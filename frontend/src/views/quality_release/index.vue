<template>
  <section class="page" data-module="quality_release">
    <header class="page-head">
      <div>
        <h2>质量审核放行</h2>
        <p class="page-desc">
          把监控对象、检查阈值和待落盘的指标批次绑定为审核批次；只有本批次本轮检查全部通过才能放行。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记放行批次</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出放行批次清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>批次编号</span>
        <input v-model="filters['批次编号']" data-testid="filter-批次编号" placeholder="按批次编号检索" />
      </label>
      <label class="filter-item">
        <span>放行状态</span>
        <select v-model="statusFilter" data-testid="filter-status" @change="reload">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table release-table">
      <thead>
        <tr>
          <th>批次编号</th>
          <th>指标批次</th>
          <th>放行状态</th>
          <th>检查轮次</th>
          <th>检查进度</th>
          <th>通过 / 超阈值 / 缺样本</th>
          <th>已入账 / 未入账</th>
          <th>缺失环节</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :data-testid="`row-${row.id}`"
          :data-status="String(row.status)"
          :class="{ selected: selectedId === row.id }"
          @click="selectRow(row)"
        >
          <td>{{ row['批次编号'] }}</td>
          <td>{{ row['指标批次'] }}</td>
          <td>
            <span class="status-pill" :data-status="String(row.status)">{{ row.status }}</span>
          </td>
          <td>{{ row['检查轮次'] ? `第 ${row['检查轮次']} 轮` : '—' }}</td>
          <td>{{ row['检查进度'] }}</td>
          <td>{{ row['通过数'] }} / {{ row['超阈值数'] }} / {{ row['缺样本数'] }}</td>
          <td>{{ row['已入账项'] }} / {{ row['未入账项'] }}</td>
          <td class="gap-cell">{{ row['缺失环节'] }}</td>
          <td class="row-actions" @click.stop>
            <button
              v-for="action in rowActions(row)"
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
          <td colspan="9" class="empty-state">暂无放行批次，等待质检生成</td>
        </tr>
      </tbody>
    </table>

    <section v-if="detail" class="release-detail" data-testid="release-detail">
      <header class="release-detail-head">
        <div>
          <h3>{{ detail['批次编号'] }} · {{ detail['指标批次'] }}</h3>
          <p class="page-desc">{{ detail['说明'] }}</p>
        </div>
        <div class="page-actions">
          <button class="btn" type="button" data-testid="open-samples" @click="openSamples">修正样本</button>
          <button class="btn primary" type="button" data-testid="write-batch" @click="writeBatch">
            按批次落盘
          </button>
        </div>
      </header>

      <div class="release-summary">
        <span>放行状态：<strong>{{ detail.status }}</strong></span>
        <span>检查进度：{{ detail['检查进度'] }}（第 {{ detail['检查轮次'] || 0 }} 轮）</span>
        <span>结论：{{ detail['结论说明'] }}</span>
        <span v-if="detail['放行冲突']" class="warn-text">冲突：{{ detail['冲突说明'] }}</span>
      </div>
      <p class="release-gap" data-testid="release-gap">缺失环节：{{ detail['缺失环节'] }}</p>

      <h4>监控对象检查视图</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>监控对象</th>
            <th>检查项</th>
            <th>阈值区间</th>
            <th>本批样本</th>
            <th>结论</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in detail['检查视图']?.['检查项'] ?? []"
            :key="`${item['监控对象']}-${item['检查项']}`"
            :data-testid="`check-${item['监控对象']}`"
            :data-verdict="item['结论']"
          >
            <td>{{ item['监控对象'] }}</td>
            <td>{{ item['检查项'] }}</td>
            <td>{{ item['阈值'] }}</td>
            <td>{{ item['样本值'] ?? '缺测' }}</td>
            <td>{{ item['结论'] }}</td>
            <td>{{ item['结论说明'] }}</td>
          </tr>
        </tbody>
      </table>

      <h4>报告项写入结果</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>槽位编号</th>
            <th>指标</th>
            <th>指标值</th>
            <th>监控对象</th>
            <th>对象结论</th>
            <th>写入状态</th>
            <th>入账依据 / 未入账原因</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in detail['报告项视图'] ?? []"
            :key="`${item['槽位编号']}-${item['指标编号']}`"
            :data-testid="`report-${item['槽位编号']}`"
            :data-write-status="item['写入状态']"
          >
            <td>{{ item['槽位编号'] }}</td>
            <td>{{ item['指标编号'] }} · {{ item['指标名称'] }}</td>
            <td>{{ item['指标值'] }}</td>
            <td>{{ item['监控对象'] }}</td>
            <td>{{ item['对象结论'] }}</td>
            <td>{{ item['写入状态'] }}</td>
            <td>{{ item['入账依据'] || item['未入账原因'] }}</td>
          </tr>
        </tbody>
      </table>

      <p v-if="detail['落盘结论']" class="release-gap">{{ detail['落盘结论'] }}</p>

      <details v-if="(detail['检查历史'] ?? []).length" class="release-history">
        <summary>历史检查轮次</summary>
        <ul>
          <li v-for="round in detail['检查历史']" :key="round['轮次']">
            第 {{ round['轮次'] }} 轮 · {{ round['状态'] }} ·
            {{ (round['检查项结果'] ?? []).map((r: Row) => `${r['监控对象']}=${r['结论']}`).join('，') }}
          </li>
        </ul>
      </details>
      <details v-if="(detail['样本修正记录'] ?? []).length" class="release-history">
        <summary>样本修正记录</summary>
        <ul>
          <li v-for="(record, index) in detail['样本修正记录']" :key="index">
            {{ record['修正时间'] }} · {{ (record['监控对象'] as string[]).join('、') }}
          </li>
        </ul>
      </details>
    </section>

    <div v-if="showSamples" class="modal-backdrop" data-testid="sample-modal">
      <form class="modal" @submit.prevent="submitSamples">
        <h3>修正本批样本</h3>
        <p class="page-desc">修正后旧结论与放行依据立即失效，需要重新检查一轮。</p>
        <label
          v-for="item in detail?.['检查视图']?.['检查项'] ?? []"
          :key="String(item['监控对象'])"
          class="create-field"
        >
          <span>{{ item['监控对象'] }} · {{ item['检查项'] }}</span>
          <input
            v-model="sampleValues[String(item['监控对象'])]"
            :data-testid="`sample-${item['监控对象']}`"
            placeholder="留空表示仍然缺测"
          />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showSamples = false">取消</button>
          <button class="btn primary" data-testid="submit-samples" type="submit">提交修正</button>
        </div>
      </form>
    </div>


    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal create-release" @submit.prevent="submitCreate">
        <h3>登记放行批次</h3>
        <p class="page-desc">把监控对象、检查阈值和准备落盘的指标批次绑定在一起，登记后从第 1 轮开始检查。</p>
        <label class="create-field">
          <span>批次编号</span>
          <input v-model="createForm['批次编号']" data-testid="create-批次编号" required />
        </label>
        <label class="create-field">
          <span>指标批次</span>
          <input v-model="createForm['指标批次']" data-testid="create-指标批次" required />
        </label>
        <label class="create-field">
          <span>说明</span>
          <input v-model="createForm['说明']" data-testid="create-说明" />
        </label>

        <h4>检查项（监控对象 + 阈值）</h4>
        <div v-for="(item, index) in createForm['检查项']" :key="`check-${index}`" class="create-row">
          <input v-model="item['监控对象']" :data-testid="`create-check-monitor-${index}`" placeholder="监控对象" />
          <input v-model="item['检查项']" :data-testid="`create-check-name-${index}`" placeholder="检查项" />
          <input v-model="item['阈值上限']" :data-testid="`create-check-high-${index}`" placeholder="阈值上限" />
          <input v-model="item['阈值下限']" :data-testid="`create-check-low-${index}`" placeholder="阈值下限" />
          <input v-model="item['样本值']" :data-testid="`create-check-sample-${index}`" placeholder="本批样本（可留空）" />
          <button class="link" type="button" @click="createForm['检查项'].splice(index, 1)">移除</button>
        </div>
        <button class="btn ghost" type="button" data-testid="add-check" @click="addCheck">添加检查项</button>

        <h4>报告项（待落盘指标）</h4>
        <div v-for="(item, index) in createForm['报告项']" :key="`report-${index}`" class="create-row">
          <input v-model="item['槽位编号']" :data-testid="`create-report-slot-${index}`" placeholder="槽位编号" />
          <input v-model="item['指标编号']" :data-testid="`create-report-metric-${index}`" placeholder="指标编号" />
          <input v-model="item['指标名称']" :data-testid="`create-report-name-${index}`" placeholder="指标名称" />
          <input v-model="item['指标值']" :data-testid="`create-report-value-${index}`" placeholder="指标值" />
          <input v-model="item['监控对象']" :data-testid="`create-report-monitor-${index}`" placeholder="监控对象" />
          <button class="link" type="button" @click="createForm['报告项'].splice(index, 1)">移除</button>
        </div>
        <button class="btn ghost" type="button" data-testid="add-report" @click="addReport">添加报告项</button>

        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 个放行批次</span>
      <span v-if="message" class="foot-message">{{ message }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/quality_release'
const statuses = ['待检查', '检查中', '检查中断', '已放行', '拒绝放行', '缺少样本']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const message = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const selectedId = ref<number | null>(null)
const detail = ref<Row | null>(null)
const showSamples = ref(false)
const sampleValues = ref<Record<string, string>>({})
const showCreate = ref(false)
const creating = ref(false)
type CreateCheck = Record<string, string>
type CreateReport = Record<string, string>
type CreateForm = {
  批次编号: string
  指标批次: string
  说明: string
  检查项: CreateCheck[]
  报告项: CreateReport[]
}
const blankCheck = (): CreateCheck => ({ 监控对象: '', 检查项: '', 阈值上限: '', 阈值下限: '', 样本值: '' })
const blankReport = (): CreateReport => ({
  槽位编号: '', 指标编号: '', 指标名称: '', 指标值: '', 监控对象: '',
})
const createForm = ref<CreateForm>({
  批次编号: '', 指标批次: '', 说明: '',
  检查项: [blankCheck()], 报告项: [blankReport()],
})

const stats = computed(() => [
  { label: '放行批次数', value: total.value },
  { label: '已放行', value: rows.value.filter((row) => row.status === '已放行').length },
  {
    label: '待补齐',
    value: rows.value.filter((row) => row.status !== '已放行').length,
  },
])

function rowActions(row: Row): string[] {
  if (row.status === '检查中') return ['检查一项', '完成检查', '中断检查']
  if (row.status === '待检查') return ['开始检查']
  // 中断、拒绝放行、缺少样本、已放行都只能开新一轮，不能沿用旧结论。
  return ['重试检查']
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value).toString()
  const status = statusFilter.value ? `&status=${encodeURIComponent(statusFilter.value)}` : ''
  try {
    const response = await request(`${ENDPOINT}?${query}${status}`)
    if (!response.ok) throw new Error('放行批次列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (selectedId.value !== null && !rows.value.some((row) => row.id === selectedId.value)) {
      selectedId.value = null
      detail.value = null
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '放行批次列表读取失败'
  }
}

async function loadDetail(entryId: number) {
  const response = await request(`${ENDPOINT}/${entryId}`)
  if (!response.ok) throw new Error('放行批次明细读取失败')
  detail.value = await response.json()
}

async function selectRow(row: Row) {
  selectedId.value = row.id
  try {
    await loadDetail(row.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '放行批次明细读取失败'
  }
}

async function refreshAfterAction(entryId: number) {
  await reload()
  await loadDetail(entryId)
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  message.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '放行动作未生效')
    message.value = payload.message
    selectedId.value = row.id
    await refreshAfterAction(row.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '放行动作未生效'
  }
}

async function writeBatch() {
  if (!detail.value) return
  errorMessage.value = ''
  message.value = ''
  try {
    const response = await request(`/api/sink_writer/releases/${detail.value.id}/write`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '批次落盘未生效')
    message.value = payload.message
    await refreshAfterAction(detail.value.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批次落盘未生效'
  }
}

function openSamples() {
  if (!detail.value) return
  sampleValues.value = {}
  for (const item of detail.value['检查视图']?.['检查项'] ?? []) {
    const value = item['样本值']
    sampleValues.value[String(item['监控对象'])] = value === null || value === undefined ? '' : String(value)
  }
  errorMessage.value = ''
  showSamples.value = true
}

async function submitSamples() {
  if (!detail.value) return
  const samples: Record<string, number | null> = {}
  for (const [monitor, value] of Object.entries(sampleValues.value)) {
    if (value === '') continue
    const parsed = Number(value)
    if (Number.isNaN(parsed)) {
      errorMessage.value = `监控对象 ${monitor} 的样本必须是数字`
      return
    }
    samples[monitor] = parsed
  }
  try {
    const response = await request(`${ENDPOINT}/${detail.value.id}/samples`, {
      method: 'POST',
      body: JSON.stringify({ samples }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '样本修正失败')
    message.value = payload.message
    showSamples.value = false
    await refreshAfterAction(detail.value.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '样本修正失败'
  }
}


function openCreate() {
  createForm.value = {
    批次编号: '', 指标批次: '', 说明: '',
    检查项: [blankCheck()], 报告项: [blankReport()],
  }
  errorMessage.value = ''
  showCreate.value = true
}

function addCheck() {
  createForm.value['检查项'].push(blankCheck())
}

function addReport() {
  createForm.value['报告项'].push(blankReport())
}

function toNumberOrNull(value: string): number | null {
  if (value === '') return null
  const parsed = Number(value)
  return Number.isNaN(parsed) ? null : parsed
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const payload = {
      批次编号: createForm.value['批次编号'].trim(),
      指标批次: createForm.value['指标批次'].trim(),
      说明: createForm.value['说明'].trim(),
      检查项: createForm.value['检查项'].map((item) => ({
        监控对象: item['监控对象'].trim(),
        检查项: item['检查项'].trim() || '检查项',
        阈值上限: toNumberOrNull(item['阈值上限']),
        阈值下限: toNumberOrNull(item['阈值下限']),
        样本值: toNumberOrNull(item['样本值']),
      })),
      报告项: createForm.value['报告项'].map((item) => ({
        槽位编号: item['槽位编号'].trim(),
        指标编号: item['指标编号'].trim(),
        指标名称: item['指标名称'].trim(),
        指标值: toNumberOrNull(item['指标值']),
        监控对象: item['监控对象'].trim(),
      })),
    }
    const response = await request(ENDPOINT, {
      method: 'POST', body: JSON.stringify(payload),
    })
    const result = await response.json()
    if (!response.ok || !result.ok) throw new Error(result.message || '登记失败')
    showCreate.value = false
    message.value = result.message
    await reload()
    const created = rows.value.find((row) => row['批次编号'] === payload['批次编号'])
    if (created) {
      selectedId.value = created.id
      await loadDetail(created.id)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
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
    link.download = 'quality_release.csv'
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.release-table tr.selected td { background: #eff6ff; }
.status-pill { padding: 1px 8px; border-radius: 10px; background: #e2e8f0; font-size: 12px; }
.status-pill[data-status='已放行'] { background: #dcfce7; color: #166534; }
.status-pill[data-status='拒绝放行'] { background: #fee2e2; color: #991b1b; }
.status-pill[data-status='缺少样本'] { background: #fef3c7; color: #92400e; }
.status-pill[data-status='检查中断'] { background: #ffe4e6; color: #9f1239; }
.gap-cell { max-width: 260px; font-size: 12px; color: #475569; }
.release-detail { margin-top: 16px; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.release-detail-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.release-detail h4 { margin: 16px 0 8px; font-size: 14px; }
.release-summary { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; margin-top: 8px; }
.release-gap { font-size: 13px; color: #475569; margin: 8px 0; }
.warn-text { color: #b45309; }
.release-history { margin-top: 12px; font-size: 13px; color: #475569; }
.foot-message { color: #166534; }
.create-release h4 { margin: 16px 0 8px; font-size: 13px; }
.create-row { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)) auto; gap: 6px; margin-bottom: 6px; }
.create-row input { border: 1px solid var(--border); border-radius: 6px; padding: 6px; font-size: 12px; }
</style>

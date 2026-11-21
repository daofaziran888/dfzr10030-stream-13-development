import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

type ModuleCase = {
  key: string
  fields: string[]
  actions: string[]
  actionTargets: string[]
  shape: string
}

const modules: ModuleCase[] = [
  {
    "key": "source_binding",
    "fields": [
      "源端编号",
      "源端类型",
      "连接地址",
      "认证凭证",
      "心跳间隔",
      "重连策略",
      "并发分区",
      "绑定状态"
    ],
    "actions": [
      "发起绑定",
      "断开连接",
      "重新绑定"
    ],
    "actionTargets": [
      "连接中",
      "在线",
      "已断开"
    ],
    "shape": "crud-table"
  },
  {
    "key": "cdc_task",
    "fields": [
      "任务编号",
      "源数据库",
      "监控表",
      "操作类型",
      "起始位点",
      "当前位点",
      "延迟毫秒",
      "异常计数"
    ],
    "actions": [
      "启动捕获",
      "暂停任务",
      "续接位点"
    ],
    "actionTargets": [
      "捕获中",
      "已暂停",
      "异常中断"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "stream_transform",
    "fields": [
      "算子编号",
      "输入流",
      "输出流",
      "转换类型",
      "并行实例",
      "背压阈值",
      "状态大小",
      "算子耗时"
    ],
    "actions": [
      "部署算子",
      "降级算子",
      "停止算子"
    ],
    "actionTargets": [
      "运行中",
      "已降级",
      "已停止"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "window_agg",
    "fields": [
      "窗口编号",
      "聚合指标",
      "窗口类型",
      "窗口长度",
      "滑动步长",
      "迟到阈值",
      "发射频率",
      "状态过期"
    ],
    "actions": [
      "启效窗口",
      "暂停窗口",
      "废弃窗口"
    ],
    "actionTargets": [
      "生效中",
      "已暂停",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "state_store",
    "fields": [
      "状态编号",
      "关联算子",
      "存储后端",
      "分区数量",
      "状态大小",
      "过期策略",
      "快照周期",
      "最后快照"
    ],
    "actions": [
      "初始化状态",
      "触发快照",
      "清理状态"
    ],
    "actionTargets": [
      "运行中",
      "快照中",
      "已清理"
    ],
    "shape": "crud-table"
  },
  {
    "key": "rule_engine",
    "fields": [
      "规则编号",
      "规则条件",
      "触发动作",
      "优先级",
      "生效范围",
      "冷却秒数",
      "命中次数",
      "最后触发"
    ],
    "actions": [
      "启用规则",
      "暂停规则",
      "归档规则"
    ],
    "actionTargets": [
      "已启用",
      "已暂停",
      "已归档"
    ],
    "shape": "crud-table"
  },
  {
    "key": "watermark_mgr",
    "fields": [
      "水位编号",
      "关联流",
      "水位类型",
      "当前水位",
      "允许迟到",
      "空闲超时",
      "水位间隔",
      "最后更新"
    ],
    "actions": [
      "初始化水位",
      "标记过期",
      "强制推进"
    ],
    "actionTargets": [
      "推进中",
      "已过期",
      "待初始化"
    ],
    "shape": "crud-table"
  },
  {
    "key": "sink_writer",
    "fields": [
      "槽位编号",
      "输出类型",
      "目标地址",
      "写入模式",
      "批次大小",
      "刷新间隔",
      "压缩算法",
      "分区策略"
    ],
    "actions": [
      "启动写入",
      "暂停写入",
      "标记失败"
    ],
    "actionTargets": [
      "写入中",
      "已暂停",
      "写入失败"
    ],
    "shape": "crud-table"
  },
  {
    "key": "backpressure",
    "fields": [
      "策略编号",
      "关联算子",
      "队列上限",
      "扩容阈值",
      "降级动作",
      "恢复阈值",
      "触发次数",
      "当前状态"
    ],
    "actions": [
      "启用监控",
      "手动降级",
      "确认恢复"
    ],
    "actionTargets": [
      "监控中",
      "已触发",
      "已恢复"
    ],
    "shape": "crud-table"
  },
  {
    "key": "checkpoint",
    "fields": [
      "检查点编号",
      "关联流水线",
      "位点时间",
      "状态大小",
      "触发方式",
      "存活轮数",
      "恢复耗时",
      "创建时间"
    ],
    "actions": [
      "触发检查",
      "标记可用",
      "标记过期"
    ],
    "actionTargets": [
      "可用",
      "已过期",
      "创建中"
    ],
    "shape": "crud-table"
  },
  {
    "key": "data_quality",
    "fields": [
      "规则编号",
      "关联流",
      "检查项",
      "上限阈值",
      "下限阈值",
      "告警级别",
      "统计窗口",
      "连续异常"
    ],
    "actions": [
      "启用规则",
      "关闭规则",
      "确认告警"
    ],
    "actionTargets": [
      "运行中",
      "已告警",
      "已关闭"
    ],
    "shape": "crud-table"
  },
  {
    "key": "schema_evolve",
    "fields": [
      "变更编号",
      "关联流",
      "变更类型",
      "新增字段",
      "删除字段",
      "兼容级别",
      "生效版本",
      "回滚标记"
    ],
    "actions": [
      "执行变更",
      "标记生效",
      "回滚变更"
    ],
    "actionTargets": [
      "待执行",
      "已生效",
      "已回滚"
    ],
    "shape": "crud-table"
  },
  {
    "key": "pipeline_orch",
    "fields": [
      "管道编号",
      "管道名称",
      "节点列表",
      "依赖拓扑",
      "并行度",
      "恢复策略",
      "超时分钟",
      "运行批次"
    ],
    "actions": [
      "部署管道",
      "启动运行",
      "停止管道"
    ],
    "actionTargets": [
      "部署中",
      "运行中",
      "已停止"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "dedup_mgr",
    "fields": [
      "策略编号",
      "关联流",
      "去重键",
      "去重窗口",
      "保留策略",
      "状态上限",
      "命中次数",
      "误杀率"
    ],
    "actions": [
      "启用去重",
      "停用去重",
      "清理状态"
    ],
    "actionTargets": [
      "运行中",
      "已停用",
      "容量告警"
    ],
    "shape": "crud-table"
  },
  {
    "key": "metric_calc",
    "fields": [
      "指标编号",
      "指标名称",
      "计算公式",
      "更新频率",
      "维度组合",
      "精度模式",
      "缓存窗口",
      "最后计算"
    ],
    "actions": [
      "发布指标",
      "暂停计算",
      "标记异常"
    ],
    "actionTargets": [
      "计算中",
      "可用",
      "计算异常"
    ],
    "shape": "crud-table"
  },
  {
    "key": "event_router",
    "fields": [
      "规则编号",
      "事件类型",
      "匹配条件",
      "目标管道",
      "优先级",
      "分区键",
      "重试上限",
      "DLQ策略"
    ],
    "actions": [
      "启用路由",
      "停用路由",
      "归档规则"
    ],
    "actionTargets": [
      "路由中",
      "已停用",
      "已被拒"
    ],
    "shape": "crud-table"
  },
  {
    "key": "replay_batch",
    "fields": [
      "任务编号",
      "数据源",
      "起始时间",
      "截止时间",
      "回放倍速",
      "并行分区",
      "当前位点",
      "跳过策略"
    ],
    "actions": [
      "启动回放",
      "暂停回放",
      "继续回放"
    ],
    "actionTargets": [
      "回放中",
      "已完成",
      "部分跳过"
    ],
    "shape": "crud-table"
  },
  {
    "key": "grp_partition",
    "fields": [
      "策略编号",
      "关联流",
      "分区键",
      "分区数量",
      "分区算法",
      "热点检测",
      "再平衡触发",
      "左右迁移"
    ],
    "actions": [
      "启效策略",
      "启动再平衡",
      "停用策略"
    ],
    "actionTargets": [
      "已生效",
      "再平衡中",
      "已停用"
    ],
    "shape": "crud-table"
  }
]
const repoKind = 'fullstack'
const crudModules = modules.filter(m => m.shape === 'crud-table')
const dagModules = modules.filter(m => m.shape === 'dag-graph')
const timelineModules = modules.filter(m => m.shape === 'job-timeline')
const analysisModules = modules.filter(m => m.shape === 'analysis-dashboard')

function parseCsv(text: string): string[][] {
  const records: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const input = text.replace(/^\uFEFF/, '')
  for (let index = 0; index < input.length; index++) {
    const char = input[index]
    if (quoted) {
      if (char === '"' && input[index + 1] === '"') { cell += '"'; index++ }
      else if (char === '"') { quoted = false }
      else { cell += char }
    } else if (char === '"' && cell === '') { quoted = true }
    else if (char === ',') { row.push(cell); cell = '' }
    else if (char === '\n') {
      row.push(cell.replace(/\r$/, ''))
      if (row.some(v => v !== '')) records.push(row)
      row = []; cell = ''
    } else { cell += char }
  }
  row.push(cell.replace(/\r$/, ''))
  if (row.some(v => v !== '')) records.push(row)
  return records
}

test('CRUD模块：筛选、导出、登记、动作、指标全链路', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (crudModules.length === 0) { test.skip(); return }

  for (const mod of crudModules) {
    await page.goto(`/${mod.key}`)
    await page.waitForTimeout(3000)
    const bodyRows = page.locator('tbody tr[data-testid^="row-"]')
    await expect(bodyRows).toHaveCount(3)
    const firstValue = await bodyRows.nth(0).locator('td').nth(0).innerText()

    await page.getByTestId(`filter-${mod.fields[0]}`).fill(firstValue)
    await page.getByTestId('query').click()
    await expect(bodyRows).toHaveCount(1)
    await page.getByTestId('reset').click()
    await expect(bodyRows).toHaveCount(3)

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    const createdValues = mod.fields.map((f, i) => `验收-${mod.key}-${i+1}`)
    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.entries()) {
      await page.getByTestId(`create-${field}`).fill(createdValues[i])
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
    await expect(bodyRows).toHaveCount(4)

    const createdRow = page.locator('tbody tr').filter({ hasText: createdValues[0] })
    for (const [i, action] of mod.actions.entries()) {
      await createdRow.getByRole('button', { name: action, exact: true }).click()
      await expect(createdRow).toHaveAttribute('data-status', mod.actionTargets[i])
    }
  }

  expect(browserErrors).toEqual([])
})

test('DAG拓扑模块：节点渲染、详情、动作、导出', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (dagModules.length === 0) { test.skip(); return }

  for (const mod of dagModules) {
    await page.goto(`/${mod.key}`)
    await page.waitForTimeout(3000)
    await expect(page.locator('svg.dag-svg')).toBeVisible()
    const nodes = page.locator('g.dag-node')
    const count = await nodes.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await nodes.first().click()
    await expect(page.getByTestId('dag-detail')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('时间线模块：甘特条渲染、日期筛选、日志查看、登记', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (timelineModules.length === 0) { test.skip(); return }

  for (const mod of timelineModules) {
    await page.goto(`/${mod.key}`)
    await expect(page.locator('.timeline-bar').first()).toBeVisible({ timeout: 10000 })
    const bars = page.locator('.timeline-bar')
    const count = await bars.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await bars.first().click()
    await expect(page.getByTestId('timeline-log')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('分析看板模块：KPI卡片、运行分析、图表渲染', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (analysisModules.length === 0) { test.skip(); return }

  for (const mod of analysisModules) {
    await page.goto(`/${mod.key}`)
    await expect(page.getByTestId('kpi-card').first()).toBeVisible({ timeout: 10000 })
    const kpiCards = page.getByTestId('kpi-card')
    const kpiCount = await kpiCards.count()
    expect(kpiCount).toBeGreaterThanOrEqual(2)
    await expect(kpiCards.first().locator('strong')).toBeVisible()

    await page.getByTestId('run-analysis').click()
    await expect(page.locator('.analysis-bar').first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('.data-table tbody tr').first()).toBeVisible({ timeout: 5000 })
  }

  expect(browserErrors).toEqual([])
})

test('概览汇总', async ({ page }) => {
  test.setTimeout(300_000)
  await page.goto('/')
  await expect(page.locator('.stat-value').nth(1)).toBeVisible()
  // 验证概览页加载正常即可，不硬编码精确计数（取决于各模块 E2E 登记成功数）
})

test('质量审核放行：三组样本的槽位入账解释与重跑补齐', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400) browserErrors.push(`${r.status()} ${r.url()}`) })

  // 落盘依赖输出槽位实际状态：先只放开 SINK-0002，用来验证“部分入账”。
  const slotActions = async (slots: number[], action: string) => {
    for (const slot of slots) {
      await page.request.post(`/api/sink_writer/${slot}/actions`, { data: { action } })
    }
  }
  await slotActions([1, 2, 3], '暂停写入')
  await slotActions([2], '启动写入')

  await page.goto('/quality_release')
  // 三个基线批次就是验收对象；登记动作放在最后，不影响前面的计数断言。
  await expect(page.locator('tbody tr[data-testid^="row-"]')).toHaveCount(3)

  const row = (id: number) => page.getByTestId(`row-${id}`)
  const checkVerdict = (monitor: string) => page.getByTestId(`check-${monitor}`)
  const reportStatus = (slot: string) => page.getByTestId(`report-${slot}`)

  // --- 通过组：先部分入账，补齐槽位后重跑只写未入账范围 ---
  await row(1).getByTestId('action-1-开始检查').click()
  await expect(row(1)).toHaveAttribute('data-status', '检查中')
  await row(1).getByTestId('action-1-检查一项').click()
  await expect(checkVerdict('stream_transform')).toHaveAttribute('data-verdict', '通过')
  await expect(checkVerdict('cdc_task')).toHaveAttribute('data-verdict', '未检查')
  await expect(page.getByTestId('release-gap')).toContainText('第 1 轮只完成 1/3')
  await row(1).getByTestId('action-1-完成检查').click()
  await expect(row(1)).toHaveAttribute('data-status', '已放行')
  await expect(checkVerdict('sink_writer')).toHaveAttribute('data-verdict', '通过')

  await page.getByTestId('write-batch').click()
  await expect(reportStatus('SINK-0002')).toHaveAttribute('data-write-status', '已入账')
  await expect(reportStatus('SINK-0001')).toHaveAttribute('data-write-status', '未入账')
  await expect(row(1)).toContainText('1 / 2')
  await expect(reportStatus('SINK-0001')).toContainText('需要先启动写入')

  await slotActions([1, 3], '启动写入')
  await page.getByTestId('write-batch').click()
  for (const slot of ['SINK-0001', 'SINK-0002', 'SINK-0003']) {
    await expect(reportStatus(slot)).toHaveAttribute('data-write-status', '已入账')
  }
  await expect(page.getByTestId('release-detail')).toContainText('3/3 个报告项已入账')

  // --- 超阈值组：一个对象超阈值即阻断同批，已通过对象也不得入账 ---
  await row(2).getByTestId('action-2-开始检查').click()
  await row(2).getByTestId('action-2-完成检查').click()
  await expect(row(2)).toHaveAttribute('data-status', '拒绝放行')
  await expect(checkVerdict('stream_transform')).toHaveAttribute('data-verdict', '超阈值')
  await expect(checkVerdict('cdc_task')).toHaveAttribute('data-verdict', '通过')
  await expect(reportStatus('SINK-0002')).toHaveAttribute('data-write-status', '待写入')
  await expect(reportStatus('SINK-0002')).toContainText('同批仍有对象超阈值')
  await expect(page.locator('.release-summary')).toContainText('准时出数')
  await page.getByTestId('write-batch').click()
  await expect(page.locator('.error-text')).toContainText('不能落盘')

  // --- 缺样本组：缺测与超阈值分开表达 ---
  await row(3).getByTestId('action-3-开始检查').click()
  await row(3).getByTestId('action-3-完成检查').click()
  await expect(row(3)).toHaveAttribute('data-status', '缺少样本')
  await expect(checkVerdict('dedup_mgr')).toHaveAttribute('data-verdict', '缺少样本')
  await expect(page.getByTestId('release-gap')).toContainText('dedup_mgr')

  // --- 中断后重试：不得借用上一轮合格结论 ---
  await row(2).getByTestId('action-2-重试检查').click()
  await expect(checkVerdict('stream_transform')).toHaveAttribute('data-verdict', '未检查')
  await row(2).getByTestId('action-2-检查一项').click()
  await row(2).getByTestId('action-2-中断检查').click()
  await expect(row(2)).toHaveAttribute('data-status', '检查中断')
  await expect(page.getByTestId('release-gap')).toContainText('缺少 cdc_task、sink_writer')

  // 修正数据后补齐未通过范围，再落盘；修正会让旧轮次结论整体失效。
  await page.getByTestId('open-samples').click()
  await expect(page.getByTestId('sample-modal')).toBeVisible()
  await page.getByTestId('sample-stream_transform').fill('1200')
  await page.getByTestId('submit-samples').click()
  await expect(page.getByTestId('sample-modal')).toHaveCount(0)
  await expect(row(2)).toHaveAttribute('data-status', '待检查')
  await expect(checkVerdict('stream_transform')).toHaveAttribute('data-verdict', '未检查')

  await row(2).getByTestId('action-2-开始检查').click()
  await row(2).getByTestId('action-2-完成检查').click()
  await expect(row(2)).toHaveAttribute('data-status', '已放行')
  await page.getByTestId('write-batch').click()
  for (const slot of ['SINK-0001', 'SINK-0002', 'SINK-0003']) {
    await expect(reportStatus(slot)).toHaveAttribute('data-write-status', '已入账')
  }

  await page.getByTestId('reset').click()
  await expect(page.locator('tbody tr[data-testid^="row-"]')).toHaveCount(3)

  // --- 登记新的放行批次：报告项必须绑定到本批检查项 ---
  const newCode = `REL-E2E-${Date.now()}`
  await page.getByTestId('open-create').click()
  await expect(page.getByTestId('create-modal')).toBeVisible()
  await page.getByTestId('create-批次编号').fill(newCode)
  await page.getByTestId('create-指标批次').fill('MB-E2E')
  await page.getByTestId('create-check-monitor-0').fill('stream_transform')
  await page.getByTestId('create-check-name-0').fill('处理延迟')
  await page.getByTestId('create-check-high-0').fill('5000')
  await page.getByTestId('create-check-low-0').fill('0')
  await page.getByTestId('create-check-sample-0').fill('300')
  await page.getByTestId('create-report-slot-0').fill('SINK-0001')
  await page.getByTestId('create-report-metric-0').fill('METR-E2E')
  await page.getByTestId('create-report-monitor-0').fill('stream_transform')
  await page.getByTestId('submit-create').click()
  await expect(page.getByTestId('create-modal')).toHaveCount(0)
  await expect(
    page.locator('tbody tr[data-testid^="row-"]').filter({ hasText: newCode }),
  ).toHaveCount(1)
  await expect(page.getByTestId('release-detail')).toContainText(newCode)

  // --- 质检扫描页也能看到同一口径的发布视图 ---
  await page.goto('/data_quality')
  await expect(page.getByTestId('publish-view')).toBeVisible()
  await expect(page.getByTestId('publish-row-REL-20261121-01')).toHaveAttribute('data-releasable', 'true')
  await expect(page.getByTestId('publish-row-REL-20261121-02')).toHaveAttribute('data-releasable', 'true')
  await expect(page.getByTestId('publish-row-REL-20261121-03')).toHaveAttribute('data-releasable', 'false')
  await expect(page.getByTestId('publish-row-REL-20261121-03')).toContainText('缺测')

  expect(browserErrors).toEqual([])
})

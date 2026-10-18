import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type {
  CellInfo,
  ExecutionLog,
  ExportFiles,
  ModelConfig,
  OutlineAudit,
  PageId,
  PipelineSnapshot,
  ReportSection,
  SheetInfo,
} from '../types'
import { qualityState } from '../utils/report'
import { requestJson } from '../utils/http'

export const pages: { id: PageId; title: string; description: string }[] = [
  {
    id: 'overview',
    title: '工作台',
    description: '从数据接入到报告交付，查看本次评估工作的全貌。',
  },
  {
    id: 'data',
    title: '数据管理',
    description: '集中导入高校报表，查看已解析的工作表与指标字段。',
  },
  {
    id: 'generation',
    title: '报告生成',
    description: '确认评估学校，跟踪章节撰写与质量核验进度。',
  },
  {
    id: 'reader',
    title: '报告阅读',
    description: '按章节阅读生成内容，查看数据来源并下载成果文件。',
  },
  { id: 'settings', title: '服务设置', description: '配置本次运行使用的模型服务与生成引擎。' },
]

export const stageDefinitions = [
  { id: 1, name: '大纲规划', description: '根据已入库数据组织章节' },
  { id: 2, name: '数据检索', description: '提取章节依据与来源' },
  { id: 3, name: '章节撰写', description: '逐节生成报告正文' },
  { id: 4, name: '自动核验', description: '自动检查引用与内容逻辑' },
  { id: 5, name: '报告汇编', description: '生成 Word 与 Excel' },
]

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

function emptySection(item: Partial<ReportSection>): ReportSection {
  return {
    ...item,
    id: item.id || '',
    chapter_title: item.chapter_title || '',
    section_title: item.section_title || '',
    objective: item.objective || '',
    status: 'pending',
    content: '',
    audit: null,
  }
}

export function useWorkspace() {
  const activePage = ref<PageId>('overview')
  const schoolName = ref('')
  const detectedSchool = ref('')
  const schoolMetadata = ref<Record<string, string>>({})
  const sheets = ref<SheetInfo[]>([])
  const totalCells = ref(0)
  const sections = ref<ReportSection[]>([])
  const exportFiles = ref<ExportFiles>({})
  const outlineAudit = ref<OutlineAudit | null>(null)
  const reportDataChanged = ref(false)
  const taskState = ref<'idle' | 'running' | 'observing' | 'completed' | 'interrupted'>('idle')
  const currentStage = ref(0)
  const currentSectionId = ref('')
  const currentActivity = ref('')
  const connection = ref<'connecting' | 'online' | 'offline'>('connecting')
  const tablesError = ref('')
  const pipelineError = ref('')
  const configError = ref('')
  const configLoading = ref(false)
  const hasApiKey = ref(false)
  const lastSyncedAt = ref('')
  const refreshing = ref(false)
  const loadingExample = ref(false)
  const uploading = ref(false)
  const scanning = ref(false)
  const deletingSheet = ref('')
  const clearingData = ref(false)
  const savingConfig = ref(false)
  const executionLogs = ref<ExecutionLog[]>([])
  const folderDialog = ref(false)
  const scanForm = reactive({ directoryPath: '', recursive: true, clearExisting: false })
  const modelConfig = reactive<ModelConfig>({
    clearApiKey: false,
    apiKey: '',
    baseUrl: 'https://api.deepseek.com',
    model: 'deepseek-chat',
    agentMode: 'pi_agent',
  })
  const configSaved = ref(false)
  const selectedSectionId = ref('')
  const sectionDrawer = ref(false)
  const readerSectionId = ref('')
  const selectedSheet = ref<SheetInfo | null>(null)
  const sheetDrawer = ref(false)
  const sourceDrawer = ref(false)
  const sourceLoading = ref(false)
  const sourceError = ref('')
  const sourceCell = ref<CellInfo | null>(null)
  const cellCache = new Map<string, CellInfo>()
  let sourceRequest = 0
  let eventSource: EventSource | null = null
  let pollTimer: ReturnType<typeof setInterval> | undefined
  let statusInFlight = false
  let disposed = false

  const isBusy = computed(() => taskState.value === 'running' || taskState.value === 'observing')
  const dataBusy = computed(
    () =>
      uploading.value ||
      scanning.value ||
      loadingExample.value ||
      deletingSheet.value !== '' ||
      clearingData.value,
  )
  const generatedSections = computed(() =>
    sections.value.filter((section) => Boolean(section.content)),
  )
  const completedSections = computed(() =>
    sections.value.filter((section) => Boolean(section.audit)),
  )
  const fileCount = computed(() => new Set(sheets.value.map((sheet) => sheet.file_name)).size)
  const wordCount = computed(() =>
    sections.value.reduce((sum, section) => sum + section.content.length, 0),
  )
  const selectedSection = computed(
    () => sections.value.find((section) => section.id === selectedSectionId.value) || null,
  )
  const currentPage = computed(() => pages.find((page) => page.id === activePage.value)!)
  const requestError = computed(() =>
    [tablesError.value, pipelineError.value, configError.value].filter(Boolean).join('；'),
  )
  const progress = computed(() => {
    if (taskState.value === 'completed') return 100
    if (!currentStage.value) return 0
    if (currentStage.value === 5) return 95
    return Math.min(
      90,
      Math.round(
        10 +
          (sections.value.length
            ? (completedSections.value.length / sections.value.length) * 80
            : 0),
      ),
    )
  })
  const taskLabel = computed(
    () =>
      ({
        idle: '尚未开始',
        running: '正在生成',
        observing: '后台状态待确认',
        completed: '生成完成',
        interrupted: '连接已中断',
      })[taskState.value],
  )
  const dataTopics = computed(() => {
    const sourceText = sheets.value
      .map((sheet) => `${sheet.file_name} ${sheet.sheet_name}`)
      .join(' ')
    return [
      { name: '学校概况与办学定位', found: /概况|办学|1[-_]1/.test(sourceText) },
      { name: '组织机构与教学单位', found: /机构|党政|单位|1[-_]2|1[-_]3/.test(sourceText) },
      { name: '本科专业与大类培养', found: /专业|1[-_]4/.test(sourceText) },
      { name: '学科建设与学位授权', found: /学科|学位|博士|硕士|4[-_]1/.test(sourceText) },
      { name: '一流本科专业建设', found: /一流|优势|4[-_]3/.test(sourceText) },
    ]
  })

  function addLog(message: string, level: ExecutionLog['level'] = 'info') {
    executionLogs.value.push({
      time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      message,
      level,
    })
    if (executionLogs.value.length > 150) executionLogs.value.shift()
  }

  function navigate(page: PageId) {
    activePage.value = page
    if (window.location.hash !== `#/${page}`) window.location.hash = `/${page}`
  }

  function syncPage() {
    const page = window.location.hash.replace(/^#\/?/, '') as PageId
    activePage.value = pages.some((item) => item.id === page) ? page : 'overview'
  }

  async function fetchTables() {
    try {
      const data = await requestJson<{
        catalog: SheetInfo[]
        total_cells: number
        school_name?: string
        school_metadata?: Record<string, string>
      }>('/api/tables', { signal: AbortSignal.timeout(15000) })
      const previousSchool = detectedSchool.value
      sheets.value = data.catalog || []
      totalCells.value = data.total_cells || 0
      detectedSchool.value = data.school_name || ''
      schoolMetadata.value = data.school_metadata || {}
      if (!schoolName.value || schoolName.value === previousSchool)
        schoolName.value = data.school_name || ''
      tablesError.value = ''
      connection.value = 'online'
      return true
    } catch (error) {
      tablesError.value = `读取数据目录失败：${errorText(error)}`
      connection.value = 'offline'
      return false
    }
  }

  function applySnapshot(data: PipelineSnapshot) {
    reportDataChanged.value = Boolean(data.data_changed)
    if (!schoolName.value && data.school_name && !data.data_changed)
      schoolName.value = data.school_name
    outlineAudit.value = data.outline_audit || null
    const previous = new Map(sections.value.map((section) => [section.id, section]))
    const plan = (data.sections_plan || []).map(
      (item) => previous.get(item.id || '') || emptySection(item),
    )
    const merged = plan.length ? plan : [...sections.value]
    for (const result of data.generated_sections || []) {
      let section = merged.find((item) => item.id === result.id)
      if (!section) {
        section = emptySection({ id: result.id, section_title: result.title })
        merged.push(section)
      }
      section.content = result.content || ''
      section.audit = { audit_res: result.audit, jev_res: result.jev || {}, passed: result.passed }
      section.status = result.passed ? 'audited' : 'warning'
    }
    sections.value = merged
    // The backend retains the previous run's exports until the next run finishes.
    // Only treat them as current when its stage is the final assembly stage.
    if (data.current_stage === 5 && (data.export_files?.docx_url || data.export_files?.xlsx_url)) {
      exportFiles.value = data.export_files
      if (taskState.value !== 'running') taskState.value = 'completed'
      currentStage.value = 5
    } else if (taskState.value !== 'running') {
      currentStage.value = data.current_stage || 0
      if (data.current_stage > 0) {
        taskState.value = data.is_running === false ? 'interrupted' : 'observing'
        if (data.is_running === false) currentActivity.value = '上次生成未完成，可重新生成报告'
      }
    }
  }

  async function fetchStatus() {
    if (statusInFlight) return false
    statusInFlight = true
    try {
      const data = await requestJson<PipelineSnapshot>('/api/pipeline/status', {
        signal: AbortSignal.timeout(15000),
      })
      if (!disposed) applySnapshot(data)
      pipelineError.value = ''
      return true
    } catch (error) {
      pipelineError.value = `读取任务状态失败：${errorText(error)}`
      return false
    } finally {
      statusInFlight = false
    }
  }

  async function refreshAll() {
    if (refreshing.value) return
    refreshing.value = true
    try {
      const results = await Promise.all([fetchTables(), fetchStatus(), fetchConfig()])
      if (results.every(Boolean))
        lastSyncedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    } finally {
      refreshing.value = false
    }
  }

  async function fetchConfig() {
    configLoading.value = true
    try {
      const data = await requestJson<{
        has_api_key: boolean
        base_url: string
        model: string
        agent_mode: ModelConfig['agentMode']
      }>('/api/pipeline/config', { signal: AbortSignal.timeout(15000) })
      if (disposed) return false
      modelConfig.baseUrl = data.base_url
      modelConfig.model = data.model
      modelConfig.agentMode = data.agent_mode
      modelConfig.clearApiKey = false
      hasApiKey.value = data.has_api_key
      configError.value = ''
      return true
    } catch (error) {
      if (!disposed) configError.value = `读取账号配置失败：${errorText(error)}`
      return false
    } finally {
      configLoading.value = false
    }
  }

  async function confirm(message: string, title: string) {
    try {
      await ElMessageBox.confirm(message, title, {
        confirmButtonText: '确认继续',
        cancelButtonText: '取消',
        type: 'warning',
      })
      return true
    } catch {
      return false
    }
  }

  async function refreshDataViews() {
    cellCache.clear()
    sourceRequest++
    sourceDrawer.value = false
    sourceCell.value = null
    sheetDrawer.value = false
    selectedSheet.value = null
    const results = await Promise.all([fetchTables(), fetchStatus()])
    return results.every(Boolean)
  }

  async function removeData(sheet?: SheetInfo) {
    if (dataBusy.value || isBusy.value) return
    const title = sheet ? '删除工作表' : '清空全部入库数据'
    const message = sheet
      ? `确定删除“${sheet.file_name} / ${sheet.sheet_name}”吗？该工作表及其入库单元格将被永久移除。同一文件中的其他工作表保留。已有报告保留，数据变化后需重新生成。`
      : `确定清空当前账号的 ${sheets.value.length} 个工作表、${totalCells.value.toLocaleString()} 个单元格吗？此操作不可撤销。账号、模型配置和已有报告保留；入库数据及上传副本将被移除，本地导入目录中的原文件保留。`
    if (!(await confirm(message, title)) || dataBusy.value || isBusy.value) return
    if (sheet) deletingSheet.value = sheet.table_name
    else clearingData.value = true
    try {
      const result = await requestJson<{ message: string; file_cleanup_warning?: boolean }>(
        sheet ? `/api/tables/${encodeURIComponent(sheet.table_name)}` : '/api/tables',
        { method: 'DELETE' },
      )
      const refreshed = await refreshDataViews()
      addLog(result.message, 'success')
      ElMessage.success(result.message)
      if (!refreshed) ElMessage.warning('删除已完成，但状态刷新失败，请点击“刷新状态”')
      if (result.file_cleanup_warning)
        ElMessage.warning('入库数据已删除，部分上传副本因文件占用未能清理')
    } catch (error) {
      addLog(`${title}失败：${errorText(error)}`, 'error')
      ElMessage.error(`${title}失败：${errorText(error)}`)
    } finally {
      deletingSheet.value = ''
      clearingData.value = false
    }
  }

  function deleteSheet(sheet: SheetInfo) {
    return removeData(sheet)
  }

  function clearAllData() {
    return removeData()
  }

  async function loadExample() {
    if (dataBusy.value || isBusy.value) return
    if (
      totalCells.value &&
      !(await confirm(
        '载入示例会清空当前已入库数据，并替换为项目内置报表。是否继续？',
        '载入示例数据',
      ))
    )
      return
    loadingExample.value = true
    addLog('开始载入内置示例报表')
    try {
      const result = await requestJson<{ message: string }>('/api/load_example_data', {
        method: 'POST',
      })
      if (!(await refreshDataViews())) throw new Error('示例已载入，但状态刷新失败，请刷新状态')
      addLog(result.message || '示例数据载入完成', 'success')
      ElMessage.success('示例数据已载入')
    } catch (error) {
      addLog(errorText(error), 'error')
      ElMessage.error(`载入失败：${errorText(error)}`)
    } finally {
      loadingExample.value = false
    }
  }

  async function uploadFiles(files: File[]) {
    if (!files.length || isBusy.value || dataBusy.value) return
    if (files.some((file) => !/\.xlsx?$/i.test(file.name))) {
      ElMessage.warning('请选择 .xls 或 .xlsx 格式的 Excel 文件')
      return
    }
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    uploading.value = true
    addLog(`开始上传并解析 ${files.length} 个 Excel 文件`)
    try {
      const result = await requestJson<{ message: string }>('/api/upload', {
        method: 'POST',
        body: form,
      })
      if (!(await refreshDataViews())) throw new Error('文件已上传，但状态刷新失败，请刷新状态')
      ElMessage.success(result.message || '上传完成')
      addLog(result.message || '上传完成', 'success')
      return true
    } catch (error) {
      ElMessage.error(`上传失败：${errorText(error)}`)
      addLog(`上传失败：${errorText(error)}`, 'error')
      return false
    } finally {
      uploading.value = false
    }
  }

  async function scanDirectory() {
    if (!scanForm.directoryPath.trim() || isBusy.value || dataBusy.value) return
    if (
      scanForm.clearExisting &&
      !(await confirm('此操作将清空当前数据，再导入指定目录中的报表。是否继续？', '替换已入库数据'))
    )
      return
    scanning.value = true
    addLog(`开始导入本地目录：${scanForm.directoryPath.trim()}`)
    try {
      const result = await requestJson<{ message: string }>('/api/scan_directory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          directory_path: scanForm.directoryPath.trim(),
          recursive: scanForm.recursive,
          clear_existing: scanForm.clearExisting,
        }),
      })
      if (!(await refreshDataViews())) throw new Error('目录已导入，但状态刷新失败，请刷新状态')
      addLog(result.message || '目录导入完成', 'success')
      ElMessage.success(result.message || '目录导入完成')
      folderDialog.value = false
    } catch (error) {
      addLog(`目录导入失败：${errorText(error)}`, 'error')
      ElMessage.error(errorText(error))
    } finally {
      scanning.value = false
    }
  }

  async function saveConfig() {
    if (isBusy.value || savingConfig.value) return
    const { baseUrl, model, apiKey, agentMode } = modelConfig
    try {
      const url = new URL(baseUrl)
      if (!['https:', 'http:'].includes(url.protocol) || !model.trim()) throw new Error()
    } catch {
      ElMessage.warning('请填写有效的 HTTP(S) 服务地址和模型名称')
      return
    }
    savingConfig.value = true
    try {
      const result = await requestJson<{ has_api_key: boolean }>('/api/pipeline/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: apiKey.trim(),
          clear_api_key: modelConfig.clearApiKey,
          base_url: baseUrl.trim(),
          model: model.trim(),
          agent_mode: agentMode,
        }),
      })
      configSaved.value = true
      hasApiKey.value = result.has_api_key
      modelConfig.clearApiKey = false
      modelConfig.apiKey = ''
      ElMessage.success('模型配置已保存到当前账号')
      addLog('当前账号的模型服务配置已保存', 'success')
    } catch (error) {
      ElMessage.error(`保存失败：${errorText(error)}`)
    } finally {
      savingConfig.value = false
    }
  }

  async function finishPipeline(files: ExportFiles) {
    eventSource?.close()
    eventSource = null
    exportFiles.value = files
    taskState.value = 'completed'
    currentActivity.value = ''
    currentSectionId.value = ''
    await fetchStatus()
    addLog('报告已汇编完成，可阅读或下载', 'success')
    ElMessage.success('本次报告生成已结束，可阅读或下载')
  }

  async function startPipeline() {
    if (isBusy.value || dataBusy.value || !totalCells.value) return
    if (!schoolName.value.trim()) {
      ElMessage.warning('请先填写评估学校名称')
      navigate('generation')
      return
    }
    if (
      sections.value.some((section) => section.content) &&
      !(await confirm('重新生成将替换本次报告内容及同名导出文件。是否继续？', '重新生成报告'))
    )
      return
    try {
      await requestJson('/api/health', { signal: AbortSignal.timeout(15000) })
    } catch (error) {
      ElMessage.error(`后端服务不可用：${errorText(error)}`)
      return
    }
    eventSource?.close()
    taskState.value = 'running'
    currentStage.value = 1
    currentSectionId.value = ''
    currentActivity.value = '正在规划报告大纲'
    outlineAudit.value = null
    reportDataChanged.value = false
    exportFiles.value = {}
    sections.value = []
    pipelineError.value = ''
    executionLogs.value = []
    addLog(`开始为 ${schoolName.value.trim()} 生成报告`)
    navigate('generation')
    eventSource = new EventSource(
      `/api/pipeline/stream?school_name=${encodeURIComponent(schoolName.value.trim())}`,
    )
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'error') throw new Error(data.message || '报告生成失败')
        if (data.type === 'stage_update') {
          currentStage.value = data.stage_id
          if (
            data.stage_id === 1 &&
            data.status === 'completed' &&
            Array.isArray(data.data?.outline)
          ) {
            sections.value = data.data.outline.map(emptySection)
            outlineAudit.value = data.data.jev_audit || null
            currentActivity.value = '大纲已生成，准备检索章节数据'
            addLog(`大纲规划完成，共 ${sections.value.length} 个小节`, 'success')
          }
          if (data.stage_id === 5) currentActivity.value = '正在汇编报告与对账表'
          if (data.data?.export_files) void finishPipeline(data.data.export_files)
        } else if (data.type === 'section_stage') {
          currentSectionId.value = data.section_id
          const section = sections.value.find((item) => item.id === data.section_id)
          if (!section) return
          const phase = data.stage as ReportSection['status']
          const names: Record<string, string> = {
            retrieving: '正在检索章节数据',
            retrieved: '章节数据已就绪',
            writing: '正在撰写章节',
            auditing: '正在核验章节',
            refining: '正在根据质检结果修订',
            audited: '章节核验完成',
          }
          currentActivity.value = names[phase] || '正在生成报告'
          if (phase === 'retrieving' || phase === 'retrieved') currentStage.value = 2
          else if (phase === 'writing' || phase === 'refining') currentStage.value = 3
          else if (phase === 'auditing' || phase === 'audited') currentStage.value = 4
          if (phase === 'refining') {
            section.content = ''
            addLog(`${section.section_title} 初次核验未通过，正在修订`, 'warning')
          }
          if (phase === 'audited') {
            section.audit = data.audit
            section.status = data.audit?.passed ? 'audited' : 'warning'
            const passed = qualityState(section) === 'passed'
            addLog(
              `${section.section_title}：${passed ? '质检通过' : '核验异常'}`,
              passed ? 'success' : 'warning',
            )
          } else {
            section.status = phase
          }
          if (typeof data.points_count === 'number') section.points_count = data.points_count
        } else if (data.type === 'section_reset') {
          const section = sections.value.find((item) => item.id === data.section_id)
          if (section) section.content = ''
          addLog(data.message || '检测到模型工具调用标记泄漏，已丢弃本轮输出', 'warning')
        } else if (data.type === 'section_chunk') {
          const section = sections.value.find((item) => item.id === data.section_id)
          if (section) section.content += data.chunk || ''
        }
      } catch (error) {
        interruptStream(`生成事件异常：${errorText(error)}`)
      }
    }
    eventSource.onerror = () =>
      interruptStream('生成连接已断开。已接收的内容仍保留，请刷新状态并查看后端日志。')
  }

  function interruptStream(message: string) {
    eventSource?.close()
    eventSource = null
    taskState.value = 'interrupted'
    currentActivity.value = ''
    pipelineError.value = message
    addLog(message, 'error')
    ElMessage.error(message)
  }

  async function getCell(id: string) {
    if (!/^cell_[a-zA-Z0-9_]+$/.test(id)) throw new Error('无效的数据来源标识')
    const cached = cellCache.get(id)
    if (cached) return cached
    const result = await requestJson<{ cell: CellInfo }>(`/api/cell/${encodeURIComponent(id)}`, {
      signal: AbortSignal.timeout(15000),
    })
    cellCache.set(id, result.cell)
    return result.cell
  }

  async function showSource(id: string) {
    const requestId = ++sourceRequest
    sourceDrawer.value = true
    sourceLoading.value = true
    sourceError.value = ''
    sourceCell.value = null
    try {
      const cell = await getCell(id)
      if (requestId === sourceRequest) sourceCell.value = cell
    } catch (error) {
      if (requestId === sourceRequest) sourceError.value = errorText(error)
    } finally {
      if (requestId === sourceRequest) sourceLoading.value = false
    }
  }

  function showSection(id: string) {
    selectedSectionId.value = id
    sectionDrawer.value = true
  }
  function showSheet(sheet: SheetInfo) {
    selectedSheet.value = sheet
    sheetDrawer.value = true
  }
  function readSection(id: string) {
    readerSectionId.value = id
    sectionDrawer.value = false
    navigate('reader')
  }

  function download(kind: 'docx' | 'xlsx') {
    const path = exportFiles.value[`${kind}_url`]
    if (!path) return
    const url = new URL(path, window.location.origin)
    if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/exports/')) {
      ElMessage.error('服务器返回的下载地址无效')
      return
    }
    const anchor = document.createElement('a')
    anchor.href = url.href
    anchor.download = ''
    anchor.click()
  }

  onMounted(() => {
    syncPage()
    window.addEventListener('hashchange', syncPage)
    void refreshAll()
    pollTimer = setInterval(() => {
      if (taskState.value === 'observing') void fetchStatus()
    }, 5000)
  })
  onBeforeUnmount(() => {
    disposed = true
    eventSource?.close()
    if (pollTimer) clearInterval(pollTimer)
    window.removeEventListener('hashchange', syncPage)
  })

  return reactive({
    activePage,
    currentPage,
    schoolName,
    detectedSchool,
    schoolMetadata,
    sheets,
    totalCells,
    sections,
    exportFiles,
    outlineAudit,
    reportDataChanged,
    taskState,
    taskLabel,
    isBusy,
    dataBusy,
    currentStage,
    currentSectionId,
    currentActivity,
    connection,
    requestError,
    lastSyncedAt,
    refreshing,
    loadingExample,
    uploading,
    scanning,
    deletingSheet,
    clearingData,
    savingConfig,
    executionLogs,
    folderDialog,
    scanForm,
    modelConfig,
    configSaved,
    hasApiKey,
    configLoading,
    selectedSection,
    sectionDrawer,
    readerSectionId,
    selectedSheet,
    sheetDrawer,
    sourceDrawer,
    sourceLoading,
    sourceError,
    sourceCell,
    generatedSections,
    completedSections,
    fileCount,
    wordCount,
    progress,
    dataTopics,
    navigate,
    refreshAll,
    loadExample,
    uploadFiles,
    scanDirectory,
    deleteSheet,
    clearAllData,
    saveConfig,
    startPipeline,
    showSource,
    getCell,
    showSection,
    showSheet,
    readSection,
    download,
  })
}

export type Workspace = ReturnType<typeof useWorkspace>

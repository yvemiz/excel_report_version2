<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Document, Download, Search, Link } from '@element-plus/icons-vue'
import type { Workspace } from '../composables/useWorkspace'
import type { CellInfo } from '../types'
import { renderReportMarkdown, sectionAnchor, sectionStatus } from '../utils/report'
const { workspace: w } = defineProps<{ workspace: Workspace }>()
const query = ref('')
const container = ref<HTMLElement>()
const anchor = ref<HTMLElement>()
const preview = ref<CellInfo | null>(null)
const sourceError = ref('')
const loading = ref(false)
const visible = ref(false)
let sourceRequest = 0
let hideTimer: ReturnType<typeof setTimeout> | undefined
let diagramTimer: ReturnType<typeof setTimeout> | undefined
let active = true
let rendering = false
let needsRender = false
const content = computed(() =>
  w.generatedSections.map((section) => ({
    ...section,
    html: renderReportMarkdown(section.content, [section.chapter_title, section.section_title]),
  })),
)
const directory = computed(() =>
  w.sections.filter((section) =>
    `${section.chapter_title} ${section.section_title}`.includes(query.value.trim()),
  ),
)

function scrollToSection(id: string) {
  w.readerSectionId = id
  nextTick(() =>
    document
      .getElementById(sectionAnchor(id))
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
  )
}

async function showPreview(event: MouseEvent | FocusEvent) {
  const target = (event.target as HTMLElement).closest<HTMLElement>('.lake-citation')
  if (!target) {
    hidePreview()
    return
  }
  keepPreview()
  if (anchor.value === target && visible.value) return
  const id = target.dataset.cellId
  if (!id) return
  const requestId = ++sourceRequest
  anchor.value = target
  visible.value = true
  preview.value = null
  sourceError.value = ''
  loading.value = true
  try {
    const cell = await w.getCell(id)
    if (sourceRequest === requestId) preview.value = cell
  } catch (error) {
    if (sourceRequest === requestId)
      sourceError.value = error instanceof Error ? error.message : '来源读取失败'
  } finally {
    if (sourceRequest === requestId) loading.value = false
  }
}
function keepPreview() {
  if (hideTimer) clearTimeout(hideTimer)
}
function hidePreview() {
  keepPreview()
  hideTimer = setTimeout(() => {
    visible.value = false
    sourceRequest++
  }, 180)
}
function openSource(event: MouseEvent | KeyboardEvent) {
  const target = (event.target as HTMLElement).closest<HTMLElement>('.lake-citation')
  if (target?.dataset.cellId) {
    visible.value = false
    void w.showSource(target.dataset.cellId)
  }
}

// Mermaid is loaded only when a report contains a diagram. Never interpret unfinished streams.
async function renderDiagrams() {
  if (rendering) {
    needsRender = true
    return
  }
  const blocks = container.value?.querySelectorAll<HTMLElement>('pre code.language-mermaid')
  if (!blocks?.length || w.isBusy) return
  rendering = true
  try {
    const { default: mermaid } = await import('mermaid')
    if (!active) return
    mermaid.initialize({
      startOnLoad: false,
      suppressErrorRendering: true,
      securityLevel: 'strict',
      htmlLabels: false,
      theme: 'neutral',
    })
    for (const [index, block] of Array.from(blocks).entries()) {
      const parent = block.parentElement
      if (!parent || !parent.isConnected || parent.dataset.rendered) continue
      try {
        const { svg } = await mermaid.render(
          `report-diagram-${Date.now()}-${index}`,
          block.textContent || '',
        )
        if (active && parent.isConnected) {
          const { default: DOMPurify } = await import('dompurify')
          parent.innerHTML = DOMPurify.sanitize(svg, {
            USE_PROFILES: { svg: true, svgFilters: true },
          })
          parent.dataset.rendered = 'true'
        }
      } catch {
        /* Keep the original diagram source readable when syntax is invalid. */
      }
    }
  } finally {
    rendering = false
    if (needsRender && active) {
      needsRender = false
      void renderDiagrams()
    }
  }
}
watch(
  [content, () => w.isBusy],
  () => {
    if (diagramTimer) clearTimeout(diagramTimer)
    diagramTimer = setTimeout(() => {
      void nextTick(renderDiagrams)
    }, 250)
  },
  { immediate: true, flush: 'post' },
)
watch(
  () => w.readerSectionId,
  (id) => {
    if (id) scrollToSection(id)
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  active = false
  sourceRequest++
  if (hideTimer) clearTimeout(hideTimer)
  if (diagramTimer) clearTimeout(diagramTimer)
})
</script>

<template>
  <div class="page-stack reader-page">
    <el-card shadow="never" class="reader-toolbar"
      ><div class="card-heading">
        <div>
          <strong>{{ w.schoolName || '高校' }} · {{ w.activeDatasetName }}</strong>
          <div class="card-subtitle">
            {{ w.generatedSections.length }} 个小节 ·
            {{ w.wordCount.toLocaleString() }} 字符<template v-if="w.isBusy"> · 正在更新</template>
            <template v-if="w.activeReportVersionId"> · 报告版本 {{ w.activeReportVersionId.slice(-6) }}</template>
          </div>
        </div>
        <el-space wrap
          ><el-button
            :icon="Document"
            :disabled="!w.exportFiles.docx_url"
            @click="w.download('docx')"
            >下载 Word</el-button
          ><el-button
            :icon="Download"
            :disabled="!w.exportFiles.xlsx_url"
            @click="w.download('xlsx')"
            >下载对账表</el-button
          ></el-space
        >
      </div></el-card
    >
    <el-card v-if="!content.length" shadow="never"
      ><el-empty :image-size="110" description="还没有报告正文，生成后可在这里按章节阅读"
        ><el-button type="primary" @click="w.navigate('generation')"
          >前往报告生成</el-button
        ></el-empty
      ></el-card
    >
    <div v-else class="reader-layout">
      <el-card shadow="never" class="reader-directory"
        ><template #header>报告目录</template
        ><el-input
          v-model="query"
          :prefix-icon="Search"
          clearable
          placeholder="查找章节"
        /><el-scrollbar max-height="calc(100vh - 320px)"
          ><el-menu :default-active="w.readerSectionId" @select="scrollToSection"
            ><el-menu-item
              v-for="section in directory"
              :key="section.id"
              :index="section.id"
              :disabled="!section.content"
              ><div>
                <div class="directory-chapter">{{ section.chapter_title }}</div>
                <span>{{ section.section_title }}</span>
              </div></el-menu-item
            ></el-menu
          ></el-scrollbar
        ></el-card
      >
      <el-card shadow="never" class="report-paper-card"
        ><div
          ref="container"
          class="report-paper"
          @mouseover="showPreview"
          @mouseleave="hidePreview"
          @focusin="showPreview"
          @focusout="hidePreview"
          @click="openSource"
          @keydown.enter="openSource"
        >
          <div class="report-cover">
            <div class="eyebrow">本科教育教学质量评估</div>
            <h1>{{ w.schoolName || '高校' }}<br />教育教学质量发展检验报告</h1>
            <p>基于 {{ w.activeDatasetName }} 生成 · {{ w.generatedSections.length }} 个小节</p>
            <el-tag type="info" effect="plain">{{
              w.isBusy ? '生成中的报告' : '已生成报告'
            }}</el-tag>
          </div>
          <article
            v-for="section in content"
            :id="sectionAnchor(section.id)"
            :key="section.id"
            class="report-article"
          >
            <div class="report-section-header">
              <div>
                <div class="report-chapter-label">{{ section.chapter_title }}</div>
                <h2>{{ section.section_title }}</h2>
              </div>
              <el-tag size="small" :type="sectionStatus(section).type">{{
                sectionStatus(section).label
              }}</el-tag>
            </div>
            <div class="report-markdown" v-html="section.html" />
          </article></div
      ></el-card>
    </div>
    <el-popover
      :visible="visible"
      :virtual-ref="anchor"
      virtual-triggering
      placement="top-start"
      :width="370"
      popper-class="source-popover"
      ><div @mouseenter="keepPreview" @mouseleave="hidePreview">
        <div class="source-popover-heading">
          <el-icon><Link /></el-icon><strong>原始数据来源</strong>
        </div>
        <el-skeleton v-if="loading" :rows="3" animated /><el-alert
          v-else-if="sourceError"
          :title="sourceError"
          type="warning"
          :closable="false"
        /><template v-else-if="preview"
          ><el-descriptions :column="1" size="small"
            ><el-descriptions-item label="来源文件">{{ preview.file_name }}</el-descriptions-item
            ><el-descriptions-item label="单元格"
              >{{ preview.sheet_name }}!{{ preview.cell_ref }}</el-descriptions-item
            ><el-descriptions-item label="指标">{{ preview.metric_path }}</el-descriptions-item
            ><el-descriptions-item label="原始值">{{
              preview.raw_value
            }}</el-descriptions-item></el-descriptions
          ><el-text type="info" size="small">展示该引用对应的原始数据来源。</el-text></template
        >
      </div></el-popover
    >
  </div>
</template>

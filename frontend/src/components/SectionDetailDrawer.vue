<script setup lang="ts">
import { computed } from 'vue'
import { Reading } from '@element-plus/icons-vue'
import type { Workspace } from '../composables/useWorkspace'
import {
  citationSummary,
  judgeProvider,
  qualityState,
  renderReportMarkdown,
  sectionStatus,
} from '../utils/report'
const { workspace: w } = defineProps<{ workspace: Workspace }>()
const section = computed(() => w.selectedSection)
const audit = computed(() => section.value?.audit)
const excerpt = computed(() =>
  section.value
    ? renderReportMarkdown(section.value.content.slice(0, 1800), [
        section.value.chapter_title,
        section.value.section_title,
      ])
    : '',
)
</script>

<template>
  <el-drawer
    v-model="w.sectionDrawer"
    title="章节详情"
    size="min(760px, 100vw)"
    class="section-detail-drawer"
    destroy-on-close
  >
    <template v-if="section">
      <div class="detail-title">
        <el-text type="info">{{ section.chapter_title }}</el-text>
        <h2>{{ section.section_title }}</h2>
        <el-tag :type="sectionStatus(section).type">{{ sectionStatus(section).label }}</el-tag>
      </div>
      <el-descriptions :column="1" border class="detail-descriptions"
        ><el-descriptions-item label="章节目标">{{
          section.objective || '未提供'
        }}</el-descriptions-item
        ><el-descriptions-item label="来源文件">{{
          section.file_name || section.bound_files?.join('、') || '未提供'
        }}</el-descriptions-item
        ><el-descriptions-item label="引用核验">{{
          audit ? citationSummary(section) : '尚未核验'
        }}</el-descriptions-item
        ><el-descriptions-item label="内容评审"
          >{{ judgeProvider(audit?.jev_res.provider)
          }}<template v-if="audit?.jev_res.logic_score != null">
            · {{ (audit.jev_res.logic_score * 100).toFixed(0) }} 分</template
          ></el-descriptions-item
        ></el-descriptions
      >
      <el-alert
        v-if="audit && qualityState(section) === 'warning'"
        title="自动核验存在异常"
        :description="
          audit.jev_res.rejection_reason ||
          (!audit.audit_res.total_citations
            ? '未提取到逐条引用核验记录，无法确认数据依据是否充分。'
            : `${audit.audit_res.mismatch_count} 条引用与原始单元格不一致。`)
        "
        type="warning"
        show-icon
        :closable="false"
      />
      <el-alert
        v-else-if="audit"
        title="接口返回的综合质检已通过"
        description="可继续查看逐条引用及原始来源。"
        type="success"
        show-icon
        :closable="false"
      />
      <el-alert
        v-else
        title="该小节尚未完成核验"
        description="生成过程中，检查结果会在核验结束后显示。"
        type="info"
        show-icon
        :closable="false"
      />
      <h3 class="detail-section-heading">数据来源佐证</h3>
      <el-table
        :data="audit?.audit_res.citations || []"
        border
        :max-height="350"
        empty-text="暂无逐条引用记录"
        :row-class-name="({ row }: any) => (row.is_verified ? '' : 'warning-citation-row')"
      >
        <el-table-column type="index" label="序号" width="54" />
        <el-table-column prop="cited_text" label="报告引用" min-width="140" show-overflow-tooltip />
        <el-table-column prop="raw_value" label="原始值" min-width="130" show-overflow-tooltip />
        <el-table-column label="Excel 来源" min-width="160"
          ><template #default="{ row }"
            ><div>
              {{ row.sheet_name || '未找到来源' }}{{ row.cell_ref ? `!${row.cell_ref}` : '' }}
            </div>
            <el-button v-if="row.cell_id" link type="primary" @click="w.showSource(row.cell_id)"
              >查看原始位置</el-button
            ></template
          ></el-table-column
        >
        <el-table-column label="结果" width="95"
          ><template #default="{ row }"
            ><el-tag size="small" :type="row.is_verified ? 'success' : 'warning'">{{
              row.is_verified ? '匹配' : '不匹配'
            }}</el-tag></template
          ></el-table-column
        >
      </el-table>
      <h3 class="detail-section-heading">报告原文片段</h3>
      <el-scrollbar max-height="340px"
        ><div v-if="excerpt" class="report-markdown detail-excerpt" v-html="excerpt" />
        <el-empty v-else :image-size="60" description="暂无正文"
      /></el-scrollbar>
      <div v-if="section.content.length > 1800" class="helper-text">
        此处展示正文片段，可进入报告阅读查看完整小节。
      </div>
    </template>
    <template #footer
      ><el-space
        ><el-button @click="w.sectionDrawer = false">关闭</el-button
        ><el-button
          type="primary"
          :icon="Reading"
          :disabled="!section?.content"
          @click="section && w.readSection(section.id)"
          >阅读完整章节</el-button
        ></el-space
      ></template
    >
  </el-drawer>
</template>

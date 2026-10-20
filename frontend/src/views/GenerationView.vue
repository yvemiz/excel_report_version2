<script setup lang="ts">
import { DocumentAdd, Reading } from '@element-plus/icons-vue'
import { stageDefinitions } from '../composables/useWorkspace'
import type { Workspace } from '../composables/useWorkspace'
import type { ReportSection } from '../types'
import { citationSummary, qualityState, sectionStatus } from '../utils/report'
const { workspace: w } = defineProps<{ workspace: Workspace }>()

function formatTime(value?: number | null) {
  return value ? new Date(value * 1000).toLocaleString('zh-CN', { hour12: false }) : '—'
}

function importStatusType(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'warning'
}

function importStatusLabel(status: string) {
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  return '进行中'
}
</script>

<template>
  <div class="page-stack generation-workspace">
    <el-alert
      v-if="w.taskState === 'observing'"
      title="发现后端保存的未完成任务"
      description="正在定时读取状态。现有接口无法确认任务是否仍在执行；若长期不更新，请检查后端日志。"
      type="warning"
      show-icon
      :closable="false"
    />
    <el-alert
      v-if="w.isLegacyDataset"
      title="历史报告批次只读"
      description="已有历史报告内容受保护：不能修改入库数据、重新生成或重试小节。如需继续工作，请先在数据管理页新建评估批次。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="w.isDemoDataset"
      title="当前为示例批次"
      description="基于示例数据生成的 Word、Excel 和阅读页都会标注为“示例报告”，不得作为正式评估材料。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-card shadow="never" class="generation-setup-card"
      ><template #header
        ><div class="card-heading">
          <span>本次报告</span
          ><el-space><el-tag v-if="w.isDemoDataset" type="warning">示例数据</el-tag
            ><el-tag :type="w.taskTagType">{{ w.taskTagLabel }}</el-tag></el-space>
        </div></template
      >
      <el-row :gutter="32" align="middle">
        <el-col :xs="24" :lg="13"
          ><el-form label-position="top"
            ><el-form-item label="评估学校名称"
              ><el-input
                :model-value="w.schoolName || '请先在服务设置中填写学校名称'"
                disabled /></el-form-item
          ></el-form>
          <div class="helper-text">
            当前批次：{{ w.activeDatasetName }}
            <template v-if="w.detectedSchool"> · 数据识别学校：{{ w.detectedSchool }}</template>
          </div></el-col
        >
        <el-col :xs="24" :lg="11"
          ><div class="generation-actions">
            <el-button
              size="large"
              type="primary"
              :icon="DocumentAdd"
              :loading="w.isBusy"
              :disabled="!w.totalCells || w.dataBusy || w.connection !== 'online' || w.isLegacyDataset"
              @click="w.startPipeline"
              >{{
                w.isLegacyDataset
                  ? '历史批次只读'
                  : w.isBusy
                    ? '正在规划 / 生成'
                    : w.taskState === 'outline_ready'
                      ? '确认大纲并生成'
                      : w.generatedSections.length
                        ? '重新生成报告'
                        : '生成大纲'
              }}</el-button
            >
            <el-button
              v-if="w.taskState === 'outline_ready'"
              :disabled="w.isBusy"
              @click="w.planOutline"
              >重新规划大纲</el-button
            >
            <div class="helper-text">
              依据 {{ w.sheets.length }} 个工作表生成 ·
              {{ w.totalCells.toLocaleString() }} 个数据单元格
            </div>
          </div></el-col
        >
      </el-row>
      <el-alert
        v-if="!w.totalCells"
        title="请先在“数据管理”中导入 Excel 报表"
        type="info"
        :closable="false"
        show-icon
      />
    </el-card>
    <el-alert
      v-if="w.taskState === 'outline_ready'"
      title="大纲已生成，等待确认"
      description="请检查章节结构和大纲评语；确认后才会开始检索数据和撰写正文。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-card shadow="never" class="generation-setup-card"
      ><template #header
        ><div class="card-heading">
          <div>
            <span>本次数据清单</span>
            <div class="card-subtitle">
              生成前确认实际读取的文件与数据修订号
            </div>
          </div>
          <el-tag type="info"
            >数据修订 v{{ w.manifest?.current_revision ?? '—' }}</el-tag
          >
        </div></template
      >
      <div class="helper-text" style="margin-bottom: 12px">
        {{ w.manifest?.file_count ?? 0 }} 个文件 ·
        {{ w.manifest?.sheet_count ?? 0 }} 个工作表 ·
        {{ (w.manifest?.cell_count ?? 0).toLocaleString() }} 个单元格
      </div>
      <el-table
        :data="w.manifest?.files || []"
        size="small"
        empty-text="暂无可生成数据"
        max-height="260"
      >
        <el-table-column label="来源文件" prop="file_name" min-width="220" />
        <el-table-column label="存储方式" width="100">
          <template #default="{ row }">
            {{
              row.storage_mode === 'upload'
                ? '上传副本'
                : row.storage_mode === 'scan'
                  ? '本地目录'
                  : row.storage_mode === 'example'
                    ? '内置示例'
                    : '历史数据'
            }}
          </template>
        </el-table-column>
        <el-table-column label="工作表" prop="sheet_count" width="90" align="right" />
        <el-table-column label="单元格" width="110" align="right">
          <template #default="{ row }">{{ row.cell_count.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="导入时间" width="180">
          <template #default="{ row }">{{ formatTime(row.imported_at) }}</template>
        </el-table-column>
      </el-table>
      <el-collapse v-if="w.manifest?.recent_imports?.length" style="margin-top: 12px">
        <el-collapse-item title="最近导入记录">
          <el-table :data="w.manifest.recent_imports" size="small">
            <el-table-column label="时间" width="180">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="方式" prop="kind" width="90" />
            <el-table-column label="文件" prop="file_count" width="70" align="right" />
            <el-table-column label="小节数" prop="sheet_count" width="80" align="right" />
            <el-table-column label="修订号" width="110">
              <template #default="{ row }">
                v{{ row.revision_before }} → v{{ row.revision_after ?? '—' }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="importStatusType(row.status)" size="small">
                  {{ importStatusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="180">
              <template #default="{ row }">{{ row.error || '—' }}</template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-card>
    <el-card shadow="never" class="generation-progress-card"
      ><template #header
        ><div class="card-heading">
          <span>生成进度</span
          ><el-text type="info"
            >完成核验 {{ w.completedSections.length }} / {{ w.sections.length }} 个小节</el-text
          >
        </div></template
      >
      <el-steps
        :active="w.taskState === 'completed' ? 5 : Math.max(-1, w.currentStage - 1)"
        finish-status="success"
        align-center
        class="pipeline-steps"
        ><el-step
          v-for="stage in stageDefinitions"
          :key="stage.id"
          :title="stage.name"
          :description="stage.description"
      /></el-steps>
      <div class="progress-block">
        <div class="task-progress-label">
          <span>{{
            w.taskSummaryText
          }}</span
          ><strong>{{ w.progress }}%</strong>
        </div>
        <el-progress
          :percentage="w.progress"
          :show-text="false"
          :stroke-width="8"
          :status="
            w.taskState === 'completed'
              ? (w.qualityNeedsAttention ? 'warning' : 'success')
              : w.taskState === 'interrupted'
                ? 'exception'
                : undefined
          "
        />
      </div>
      <div class="helper-text">
        检索、撰写、核验按小节依次循环执行；进度按已完成核验的小节计算。
      </div>
      <el-alert
        v-if="w.taskState === 'completed' && w.qualityNeedsAttention"
        title="报告存在需处理项"
        :description="w.qualityDescription"
        type="warning"
        :closable="false"
        show-icon
        class="connection-alert"
      />
      <el-alert
        v-if="w.outlineAudit"
        :type="w.outlineAudit.is_approved ? 'success' : 'warning'"
        :title="`大纲检查：${w.outlineAudit.is_approved ? '通过' : '需要关注'}${w.outlineAudit.structure_score == null ? '' : ` · ${(w.outlineAudit.structure_score * 100).toFixed(0)} 分`}`"
        :description="w.outlineAudit.critique || '未提供详细评语'"
        :closable="false"
        show-icon
        class="outline-alert"
      />
    </el-card>
    <el-card shadow="never"
      ><template #header
        ><div class="card-heading">
          <span>章节任务</span
          ><el-button :icon="Reading" @click="w.navigate('reader')">阅读报告</el-button>
        </div></template
      >
      <el-table
        :data="w.sections"
        row-key="id"
        :row-class-name="({ row }: any) => (row.id === w.currentSectionId ? 'active-task-row' : '')"
        empty-text="生成开始后，报告大纲与小节任务将显示在这里"
      >
        <el-table-column label="章节 / 小节" min-width="300"
          ><template #default="{ row }"
            ><div class="table-title">{{ row.section_title }}</div>
            <div class="table-caption">{{ row.chapter_title }}</div></template
          ></el-table-column
        >
        <el-table-column label="字数" width="90" align="right"
          ><template #default="{ row }">{{
            row.content.length.toLocaleString()
          }}</template></el-table-column
        >
        <el-table-column label="引用核验" width="130"
          ><template #default="{ row }">{{
            row.audit ? citationSummary(row as ReportSection) : '尚未核验'
          }}</template></el-table-column
        >
        <el-table-column label="状态" width="130"
          ><template #default="{ row }"
            ><el-tag :type="sectionStatus(row as ReportSection).type">{{
              sectionStatus(row as ReportSection).label
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="操作" width="230" fixed="right"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="w.showSection(row.id)">详情</el-button
            ><el-button link type="primary" :disabled="!row.content" @click="w.readSection(row.id)"
              >阅读</el-button
            ><el-popconfirm
              v-if="!w.isLegacyDataset && row.audit && qualityState(row as ReportSection) === 'warning'"
              width="280"
              title="重试会新建报告版本并重新调用模型，只重写这一小节，是否继续？"
              confirm-button-text="重试"
              cancel-button-text="取消"
              @confirm="w.retrySection(row.id)"
              ><template #reference
                ><el-button link type="danger" :disabled="w.isBusy || w.connection !== 'online'"
                  >重试本节</el-button
                ></template
              ></el-popconfirm
            ></template
          ></el-table-column
        >
      </el-table>
    </el-card>
    <el-card shadow="never" class="log-card"
      ><template #header
        ><div class="card-heading">
          <span>执行记录</span><el-text type="info">显示当前页面接收到的最近记录</el-text>
        </div></template
      ><el-empty
        v-if="!w.executionLogs.length"
        :image-size="60"
        description="暂无执行记录"
      /><el-scrollbar v-else max-height="280px"
        ><el-timeline
          ><el-timeline-item
            v-for="(log, index) in [...w.executionLogs].reverse()"
            :key="`${log.time}-${index}`"
            :timestamp="log.time"
            :type="
              log.level === 'error'
                ? 'danger'
                : log.level === 'success'
                  ? 'success'
                  : log.level === 'warning'
                    ? 'warning'
                    : 'primary'
            "
            >{{ log.message }}</el-timeline-item
          ></el-timeline
        ></el-scrollbar
      ></el-card
    >
  </div>
</template>

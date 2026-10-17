<script setup lang="ts">
import { DocumentAdd, Reading } from '@element-plus/icons-vue'
import { stageDefinitions } from '../composables/useWorkspace'
import type { Workspace } from '../composables/useWorkspace'
import type { ReportSection } from '../types'
import { citationSummary, sectionStatus } from '../utils/report'
const { workspace: w } = defineProps<{ workspace: Workspace }>()
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
    <el-card shadow="never" class="generation-setup-card"
      ><template #header
        ><div class="card-heading">
          <span>本次报告</span
          ><el-tag
            :type="
              w.taskState === 'completed'
                ? 'success'
                : w.taskState === 'interrupted'
                  ? 'danger'
                  : 'info'
            "
            >{{ w.taskLabel }}</el-tag
          >
        </div></template
      >
      <el-row :gutter="32" align="middle">
        <el-col :xs="24" :lg="13"
          ><el-form label-position="top"
            ><el-form-item label="评估学校名称"
              ><el-input
                v-model="w.schoolName"
                placeholder="填写本次报告的学校名称"
                maxlength="100"
                :disabled="w.isBusy"
                clearable /></el-form-item
          ></el-form>
          <div class="helper-text">
            {{
              w.detectedSchool
                ? `从数据中识别：${w.detectedSchool}`
                : '导入学校概况表后，可自动识别学校名称。'
            }}
          </div></el-col
        >
        <el-col :xs="24" :lg="11"
          ><div class="generation-actions">
            <el-button
              size="large"
              type="primary"
              :icon="DocumentAdd"
              :loading="w.isBusy"
              :disabled="!w.totalCells || w.dataBusy || w.connection !== 'online'"
              @click="w.startPipeline"
              >{{
                w.isBusy
                  ? '正在跟踪任务'
                  : w.generatedSections.length
                    ? '重新生成报告'
                    : '开始生成报告'
              }}</el-button
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
            w.currentActivity ||
            (w.taskState === 'completed' ? '报告汇编已结束，可阅读或下载' : '等待开始生成')
          }}</span
          ><strong>{{ w.progress }}%</strong>
        </div>
        <el-progress
          :percentage="w.progress"
          :show-text="false"
          :stroke-width="8"
          :status="
            w.taskState === 'completed'
              ? 'success'
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
        <el-table-column label="操作" width="150" fixed="right"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="w.showSection(row.id)">详情</el-button
            ><el-button link type="primary" :disabled="!row.content" @click="w.readSection(row.id)"
              >阅读</el-button
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

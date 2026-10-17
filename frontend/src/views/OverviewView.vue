<script setup lang="ts">
import {
  ArrowRight,
  Collection,
  Document,
  FolderOpened,
  CircleCheck,
  UploadFilled,
  DataAnalysis,
} from '@element-plus/icons-vue'
import type { Workspace } from '../composables/useWorkspace'
import type { ReportSection } from '../types'
import { citationSummary, sectionStatus } from '../utils/report'
const { workspace: w } = defineProps<{ workspace: Workspace }>()
</script>

<template>
  <div class="page-stack">
    <el-card shadow="never" class="welcome-card">
      <div class="welcome-content">
        <div class="eyebrow">高校教育教学质量评估</div>
        <h2>{{ w.schoolName || '让每一份报告，都有数据依据' }}</h2>
        <p>汇集 Excel 报表，生成评估报告，逐章核验数据与结论。</p>
        <el-space wrap>
          <el-button type="primary" :icon="Document" @click="w.navigate('generation')"
            >进入报告生成</el-button
          >
          <el-button :icon="FolderOpened" @click="w.navigate('data')">管理数据</el-button>
        </el-space>
      </div>
      <div class="welcome-symbol" aria-hidden="true">
        <el-icon :size="88"><DataAnalysis /></el-icon>
      </div>
    </el-card>

    <el-row :gutter="18" class="stat-grid">
      <el-col :xs="12" :md="8"
        ><el-card shadow="never" class="stat-card"
          ><div class="stat-icon blue">
            <el-icon><FolderOpened /></el-icon>
          </div>
          <el-statistic title="已入库工作表" :value="w.sheets.length" />
          <div class="stat-foot">来自 {{ w.fileCount }} 个 Excel 文件</div></el-card
        ></el-col
      >
      <el-col :xs="12" :md="8"
        ><el-card shadow="never" class="stat-card"
          ><div class="stat-icon teal">
            <el-icon><Collection /></el-icon>
          </div>
          <el-statistic title="数据单元格" :value="w.totalCells" />
          <div class="stat-foot">保留原始位置与指标路径</div></el-card
        ></el-col
      >
      <el-col :xs="12" :md="8"
        ><el-card shadow="never" class="stat-card"
          ><div class="stat-icon purple">
            <el-icon><Document /></el-icon>
          </div>
          <el-statistic title="已生成小节" :value="w.generatedSections.length"
            ><template #suffix
              ><span class="stat-suffix">/ {{ w.sections.length }}</span></template
            ></el-statistic
          >
          <div class="stat-foot">{{ w.taskLabel }}</div></el-card
        ></el-col
      >
    </el-row>

    <el-row :gutter="20">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="stretch-card">
          <template #header
            ><div class="card-heading">
              <span>本次报告任务</span
              ><el-tag :type="w.taskState === 'completed' ? 'success' : 'info'" effect="light">{{
                w.taskLabel
              }}</el-tag>
            </div></template
          >
          <div v-if="w.currentStage || w.sections.length" class="task-overview">
            <div class="task-progress-label">
              <span>{{
                w.currentActivity ||
                (w.taskState === 'completed'
                  ? '报告已汇编，可阅读与下载'
                  : '正在读取后端保存的任务状态')
              }}</span
              ><strong>{{ w.progress }}%</strong>
            </div>
            <el-progress :percentage="w.progress" :stroke-width="8" :show-text="false" />
            <div class="task-meta">
              <span>完成核验 {{ w.completedSections.length }} / {{ w.sections.length }} 个小节</span
              ><el-button link type="primary" @click="w.navigate('generation')"
                >查看任务<el-icon class="el-icon--right"><ArrowRight /></el-icon
              ></el-button>
            </div>
          </div>
          <el-empty
            v-else
            :image-size="82"
            :description="
              w.totalCells
                ? '数据已就绪，可以开始生成本次报告'
                : '还没有报告任务，先导入本次评估的数据'
            "
            ><el-button
              type="primary"
              plain
              @click="w.navigate(w.totalCells ? 'generation' : 'data')"
              >{{ w.totalCells ? '开始生成报告' : '导入 Excel 报表' }}</el-button
            ></el-empty
          >
          <el-table v-if="w.sections.length" :data="w.sections.slice(0, 4)" class="compact-table">
            <el-table-column label="报告小节" min-width="220"
              ><template #default="{ row }"
                ><div class="table-title">{{ row.section_title }}</div>
                <div class="table-caption">{{ row.chapter_title }}</div></template
              ></el-table-column
            >
            <el-table-column label="引用核验" min-width="110"
              ><template #default="{ row }">{{
                row.audit ? citationSummary(row as ReportSection) : '尚未核验'
              }}</template></el-table-column
            >
            <el-table-column label="状态" width="120"
              ><template #default="{ row }"
                ><el-tag :type="sectionStatus(row as ReportSection).type" effect="light">{{
                  sectionStatus(row as ReportSection).label
                }}</el-tag></template
              ></el-table-column
            >
            <el-table-column width="72" label="详情"
              ><template #default="{ row }"
                ><el-button link type="primary" @click="w.showSection(row.id)"
                  >查看</el-button
                ></template
              ></el-table-column
            >
          </el-table>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="stretch-card guide-card"
          ><template #header
            ><div class="card-heading">
              <span>开始本次评估</span><el-tag type="info" size="small">操作指引</el-tag>
            </div></template
          >
          <el-steps
            direction="vertical"
            :active="w.totalCells ? (w.sections.length ? 2 : 1) : 0"
            :space="100"
          >
            <el-step
              title="导入原始报表"
              description="上传 Excel，或导入本机报表目录"
              :icon="UploadFilled"
            />
            <el-step
              title="生成与核验"
              description="确认学校，查看每个章节的生成结果"
              :icon="Document"
            />
            <el-step title="报告交付" description="阅读并下载报告与对账表" :icon="CircleCheck" />
          </el-steps>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never"
      ><template #header
        ><div class="card-heading">
          <span>数据准备情况</span
          ><el-button link type="primary" @click="w.navigate('data')"
            >查看数据目录<el-icon class="el-icon--right"><ArrowRight /></el-icon
          ></el-button></div
      ></template>
      <div class="topic-grid">
        <div v-for="topic in w.dataTopics" :key="topic.name" class="topic-item">
          <el-icon :class="topic.found ? 'text-success' : 'text-muted'"><CircleCheck /></el-icon
          ><span>{{ topic.name }}</span
          ><el-tag size="small" :type="topic.found ? 'success' : 'info'">{{
            topic.found ? '发现相关报表' : '暂未发现'
          }}</el-tag>
        </div>
      </div>
      <div class="helper-text">根据文件名和工作表名称辅助匹配，仅用于提示数据准备情况。</div>
    </el-card>
  </div>
</template>

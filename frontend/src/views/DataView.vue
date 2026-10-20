<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadUserFile } from 'element-plus'
import {
  UploadFilled,
  FolderOpened,
  Search,
  Refresh,
  Document,
  Delete,
  Plus,
} from '@element-plus/icons-vue'
import type { Workspace } from '../composables/useWorkspace'
import type { SheetInfo } from '../types'
const { workspace: w } = defineProps<{ workspace: Workspace }>()
const files = ref<UploadUserFile[]>([])
const query = ref('')
const page = ref(1)
const pageSize = ref(10)
const filtered = computed(() =>
  w.sheets.filter((sheet) =>
    `${sheet.file_name} ${sheet.sheet_name}`
      .toLowerCase()
      .includes(query.value.trim().toLowerCase()),
  ),
)
const paginated = computed(() =>
  filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value),
)
watch([query, pageSize, () => w.sheets.length], () => {
  page.value = 1
})
function validateFile(file: UploadFile) {
  if (!/\.xlsx?$/i.test(file.name)) {
    files.value = files.value.filter((item) => item.uid !== file.uid)
    ElMessage.warning('仅支持 .xls 和 .xlsx 文件')
  }
}
async function submitFiles() {
  const raw = files.value.flatMap((file) => (file.raw ? [file.raw] : []))
  if (await w.uploadFiles(raw)) files.value = []
}
</script>

<template>
  <div class="page-stack">
    <el-alert
      v-if="w.isLegacyDataset"
      title="历史报告批次只读"
      description="为保护已有历史报告，不能修改或清空该轮次数据。请新建评估轮次后再继续导入。"
      type="warning"
      show-icon
      :closable="false"
    />
    <el-alert
      v-if="w.isBusy"
      title="当前有报告任务，任务结束后可调整数据，避免生成依据发生变化。"
      type="info"
      show-icon
      :closable="false"
    />
    <el-card shadow="never">
      <template #header
        ><div class="card-heading">
          <div>
            <span>导入 Excel 报表</span>
            <div class="card-subtitle">支持多文件选择与拖拽，保留工作表、指标路径和单元格位置</div>
          </div>
          <el-tag type="info">.xls / .xlsx</el-tag>
        </div></template
      >
      <el-row :gutter="24">
        <el-col :xs="24" :lg="16">
          <el-upload
            v-model:file-list="files"
            drag
            multiple
            :auto-upload="false"
            accept=".xls,.xlsx"
            :on-change="validateFile"
            :disabled="w.isBusy || w.dataBusy || w.isLegacyDataset"
            class="excel-uploader"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">将 Excel 文件拖到这里，或<em>点击选择文件</em></div>
            <template #tip
              ><div class="el-upload__tip">
                选择后点击“上传并解析”，文件会进入当前评估轮次；同一轮次内同名文件会被拒绝，请新建评估轮次或先删除旧文件。
              </div></template
            >
          </el-upload>
          <el-space wrap class="upload-actions"
            ><el-button
              type="primary"
              :icon="UploadFilled"
              :loading="w.uploading"
              :disabled="!files.length || w.isBusy || w.isLegacyDataset || (w.dataBusy && !w.uploading)"
              @click="submitFiles"
              >上传并解析{{ files.length ? `（${files.length} 个文件）` : '' }}</el-button
            ><el-button
              v-if="files.length"
              :icon="Delete"
              :disabled="w.dataBusy"
              @click="files = []"
              >清空选择</el-button
            ></el-space
          >
        </el-col>
        <el-col :xs="24" :lg="8"
          ><div class="import-alternatives">
            <h3>更多导入方式</h3>
            <p>大量报表存放在本机时，可直接指定文件夹。</p>
            <el-button
              :icon="FolderOpened"
              :disabled="w.isBusy || w.dataBusy || w.isLegacyDataset"
              @click="w.folderDialog = true"
              >导入本地目录</el-button
            ><el-divider />
            <p>首次体验可使用项目内置的高校示例报表。</p>
            <el-button
              :icon="Document"
              :loading="w.loadingExample"
              :disabled="w.isBusy || (w.dataBusy && !w.loadingExample)"
              @click="w.loadExample"
              >载入示例数据</el-button
            >
            <el-divider />
            <p>需要保留同一学校不同年度或评估批次时，可新建评估轮次；不会切换学校。</p>
            <el-button :icon="Plus" @click="w.datasetDialog = true">新建评估轮次</el-button>
          </div></el-col
        >
      </el-row>
    </el-card>
    <el-card shadow="never">
      <template #header
        ><div class="card-heading">
          <div>
            <span>当前评估轮次数据目录</span>
            <div class="card-subtitle">
              {{ w.activeDatasetName }} · {{ w.fileCount }} 个文件 · {{ w.sheets.length }} 个工作表 ·
              {{ w.totalCells.toLocaleString() }} 个数据单元格 · 修订号 v{{ w.manifest?.current_revision ?? '—' }}
            </div>
          </div>
          <el-space wrap>
            <el-button type="primary" :icon="Plus" @click="w.datasetDialog = true"
              >新建评估轮次</el-button
            >
            <el-button :icon="Refresh" :loading="w.refreshing" @click="w.refreshAll"
              >刷新</el-button
            >
            <el-button
              type="danger"
              plain
              :icon="Delete"
              :loading="w.clearingData"
              :disabled="
                w.isBusy ||
                w.isLegacyDataset ||
                (w.dataBusy && !w.clearingData) ||
                (!w.sheets.length && !w.totalCells)
              "
              @click="w.clearAllData"
              >清空当前批次</el-button
            >
          </el-space>
        </div></template
      >
      <div class="table-toolbar">
        <el-input
          v-model="query"
          :prefix-icon="Search"
          clearable
          placeholder="搜索文件名或工作表"
          class="search-input"
        /><el-text type="info">共 {{ filtered.length }} 个工作表</el-text>
      </div>
      <el-table
        :data="paginated"
        stripe
        row-key="table_name"
        :empty-text="w.requestError ? '数据读取失败，请刷新重试' : '暂无数据，请先导入 Excel 报表'"
      >
        <el-table-column
          type="index"
          width="52"
          label="序号"
          :index="(index: number) => (page - 1) * pageSize + index + 1"
        />
        <el-table-column label="工作表 / 来源文件" min-width="280"
          ><template #default="{ row }"
            ><div class="table-title">{{ row.sheet_name }}</div>
            <div class="table-caption">{{ row.file_name }}</div></template
          ></el-table-column
        >
        <el-table-column label="数据行数" prop="row_count" width="115" sortable align="right" />
        <el-table-column label="指标字段" width="110" align="right"
          ><template #default="{ row }">{{
            (row.columns || row.headers || []).length
          }}</template></el-table-column
        >
        <el-table-column label="单元格数" width="120" align="right"
          ><template #default="{ row }">{{
            row.cells_count == null ? '未提供' : row.cells_count.toLocaleString()
          }}</template></el-table-column
        >
        <el-table-column label="状态" width="110"
          ><template #default
            ><el-tag type="success" effect="light">已入库</el-tag></template
          ></el-table-column
        >
        <el-table-column label="操作" width="195" fixed="right"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="w.showSheet(row as SheetInfo)"
              >查看字段</el-button
            ><el-button
              link
              type="danger"
              :loading="w.deletingSheet === row.table_name"
              :disabled="w.isBusy || w.dataBusy || w.isLegacyDataset"
              :aria-label="`删除工作表 ${row.sheet_name}`"
              @click="w.deleteSheet(row as SheetInfo)"
              >删除</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <div class="pagination-row">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, prev, pager, next, sizes"
          :total="filtered.length"
        />
      </div>
    </el-card>
    <el-card shadow="never">
      <template #header
        ><div class="card-heading">
          <div>
            <span>最近导入记录</span>
            <div class="card-subtitle">
              失败导入不会改变修订号或当前数据；可在此核对失败原因
            </div>
          </div>
        </div></template
      >
      <el-table
        :data="w.manifest?.recent_imports || []"
        size="small"
        empty-text="当前批次还没有导入记录"
      >
        <el-table-column label="时间" width="180">
          <template #default="{ row }">
            {{
              row.created_at
                ? new Date(row.created_at * 1000).toLocaleString('zh-CN', { hour12: false })
                : '—'
            }}
          </template>
        </el-table-column>
        <el-table-column label="方式" prop="kind" width="100" />
        <el-table-column label="文件" prop="file_count" width="80" align="right" />
        <el-table-column label="工作表" prop="sheet_count" width="90" align="right" />
        <el-table-column label="单元格" prop="cell_count" width="100" align="right" />
        <el-table-column label="修订号" width="120">
          <template #default="{ row }">
            v{{ row.revision_before }} → v{{ row.revision_after ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag
              :type="
                row.status === 'completed'
                  ? 'success'
                  : row.status === 'failed'
                    ? 'danger'
                    : 'warning'
              "
              size="small"
              >{{
                row.status === 'completed' ? '已完成' : row.status === 'failed' ? '失败' : '进行中'
              }}</el-tag
            >
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="220">
          <template #default="{ row }">{{ row.error || '—' }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

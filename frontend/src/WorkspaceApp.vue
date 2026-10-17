<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  School,
  HomeFilled,
  FolderOpened,
  DocumentAdd,
  Reading,
  Setting,
  Fold,
  Expand,
  Refresh,
  ArrowRight,
  Connection,
  UserFilled,
  ArrowDown,
  SwitchButton,
} from '@element-plus/icons-vue'
import { pages, useWorkspace } from './composables/useWorkspace'
import type { PageId, AuthUser } from './types'
import SectionDetailDrawer from './components/SectionDetailDrawer.vue'
const w = useWorkspace()
defineProps<{ user: AuthUser; loggingOut: boolean }>()
const emit = defineEmits<{ logout: [] }>()
const collapsed = ref(false)
const mobile = ref(window.innerWidth < 768)
const mobileMenu = ref(false)
const icons = {
  overview: HomeFilled,
  data: FolderOpened,
  generation: DocumentAdd,
  reader: Reading,
  settings: Setting,
}
const views = {
  overview: defineAsyncComponent(() => import('./views/OverviewView.vue')),
  data: defineAsyncComponent(() => import('./views/DataView.vue')),
  generation: defineAsyncComponent(() => import('./views/GenerationView.vue')),
  reader: defineAsyncComponent(() => import('./components/ReportReader.vue')),
  settings: defineAsyncComponent(() => import('./views/SettingsView.vue')),
}
const connectionText = computed(
  () => ({ connecting: '连接中', online: '服务已连接', offline: '服务连接异常' })[w.connection],
)
const sheetFields = computed(() =>
  (w.selectedSheet?.columns || w.selectedSheet?.headers || []).map((name, index) => ({
    index: index + 1,
    name,
  })),
)
function selectPage(page: string) {
  w.navigate(page as PageId)
  mobileMenu.value = false
}
function resize() {
  mobile.value = window.innerWidth < 768
}
onMounted(() => window.addEventListener('resize', resize))
onBeforeUnmount(() => window.removeEventListener('resize', resize))
</script>

<template>
  <el-container class="app-shell">
    <el-aside
      v-if="!mobile"
      :width="collapsed ? '76px' : '320px'"
      class="sidebar"
      :class="{ 'is-collapsed': collapsed }"
    >
      <div class="brand">
        <div class="brand-icon">
          <el-icon :size="27"><School /></el-icon>
        </div>
        <div v-if="!collapsed" class="brand-text">
          <strong>高校发展检验报告</strong><span>教育教学质量评估平台</span>
        </div>
      </div>
      <div v-if="!collapsed" class="nav-label">工作空间</div>
      <el-menu
        :default-active="w.activePage"
        :collapse="collapsed"
        :collapse-transition="false"
        background-color="transparent"
        text-color="#bbccde"
        active-text-color="#ffffff"
        class="side-menu"
        @select="selectPage"
        ><el-menu-item v-for="page in pages" :key="page.id" :index="page.id"
          ><el-icon><component :is="icons[page.id]" /></el-icon
          ><template #title
            ><span>{{ page.title }}</span></template
          ></el-menu-item
        ></el-menu
      >
      <div class="sidebar-footer">
        <el-icon :size="18"><Connection /></el-icon>
        <div v-if="!collapsed"><strong>个人工作空间</strong><span>数据与报告独立保存</span></div>
      </div>
    </el-aside>
    <el-container class="workspace-shell">
      <el-header class="app-header" height="72px"
        ><div class="header-left">
          <el-button
            text
            circle
            :icon="mobile || collapsed ? Expand : Fold"
            aria-label="展开或收起导航"
            @click="mobile ? (mobileMenu = true) : (collapsed = !collapsed)"
          /><el-breadcrumb separator="/"
            ><el-breadcrumb-item>评估工作空间</el-breadcrumb-item
            ><el-breadcrumb-item>{{ w.currentPage.title }}</el-breadcrumb-item></el-breadcrumb
          >
        </div>
        <el-space :size="16" class="header-right"
          ><el-button
            class="school-header-button"
            :icon="School"
            text
            @click="w.navigate('generation')"
            >{{ w.schoolName || '设置评估学校'
            }}<el-icon class="el-icon--right"><ArrowRight /></el-icon></el-button
          ><el-tag
            class="connection-tag"
            :type="
              w.connection === 'online' ? 'success' : w.connection === 'offline' ? 'danger' : 'info'
            "
            effect="plain"
            ><span class="status-dot" />{{ connectionText }}</el-tag
          ><el-divider direction="vertical" /><el-tooltip content="服务设置" placement="bottom"
            ><el-button
              circle
              text
              :icon="Setting"
              aria-label="服务设置"
              @click="w.navigate('settings')"
          /></el-tooltip>
          <el-dropdown trigger="click" @command="emit('logout')">
            <el-button text class="account-menu" :loading="loggingOut" :disabled="loggingOut">
              <el-icon><UserFilled /></el-icon>
              <span class="account-name" :title="user.display_name">{{ user.display_name }}</span>
              <el-icon><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>账号：{{ user.username }}</el-dropdown-item>
                <el-dropdown-item command="logout" :icon="SwitchButton">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </el-space></el-header
      >
      <el-main class="main-content"
        ><div class="content-width">
          <div class="page-heading">
            <div>
              <h1>{{ w.currentPage.title }}</h1>
              <p>{{ w.currentPage.description }}</p>
            </div>
            <div class="page-sync">
              <el-text v-if="w.lastSyncedAt" type="info" size="small"
                >同步于 {{ w.lastSyncedAt }}</el-text
              ><el-button :icon="Refresh" :loading="w.refreshing" @click="w.refreshAll"
                >刷新状态</el-button
              >
            </div>
          </div>
          <el-alert
            v-if="w.requestError"
            title="部分服务状态未能读取"
            :description="w.requestError"
            type="error"
            :closable="false"
            show-icon
            class="connection-alert"
          />
          <el-alert
            v-if="w.reportDataChanged"
            title="入库数据已变化，请重新生成报告"
            description="当前显示的是上次生成的报告与核验结果，尚未反映本次数据调整；已删除数据的来源明细将无法查看。"
            type="warning"
            :closable="false"
            show-icon
            class="connection-alert"
          />
          <component :is="views[w.activePage]" :workspace="w" />
          <footer class="workspace-footer">
            <span>高校发展检验报告智能生成系统</span><span>以原始数据为依据</span>
          </footer>
        </div></el-main
      >
    </el-container>
  </el-container>
  <el-drawer
    v-model="mobileMenu"
    title="工作空间导航"
    direction="ltr"
    size="260px"
    class="mobile-navigation"
    ><el-menu :default-active="w.activePage" @select="selectPage"
      ><el-menu-item v-for="page in pages" :key="page.id" :index="page.id"
        ><el-icon><component :is="icons[page.id]" /></el-icon
        ><span>{{ page.title }}</span></el-menu-item
      ></el-menu
    ></el-drawer
  >
  <el-dialog
    v-model="w.folderDialog"
    title="导入本地报表目录"
    width="min(560px, calc(100vw - 32px))"
    :close-on-click-modal="!w.scanning"
    :close-on-press-escape="!w.scanning"
    :show-close="!w.scanning"
  >
    <el-alert
      title="使用运行后端服务的计算机上的路径"
      description="支持读取目录中的 .xls 与 .xlsx 文件。默认追加数据，同名工作表可能更新已有内容。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-form
      label-position="top"
      class="folder-form"
      :disabled="w.scanning"
      @submit.prevent="w.scanDirectory"
      ><el-form-item label="报表文件夹绝对路径"
        ><el-input
          v-model="w.scanForm.directoryPath"
          placeholder="例如 D:\报表资料\本次评估"
          clearable /></el-form-item
      ><el-form-item
        ><el-checkbox v-model="w.scanForm.recursive">包含子文件夹</el-checkbox
        ><el-checkbox v-model="w.scanForm.clearExisting"
          >替换当前已入库数据</el-checkbox
        ></el-form-item
      ></el-form
    ><el-alert
      v-if="w.scanForm.clearExisting"
      title="替换模式将先清空当前数据，再解析目录文件。"
      type="warning"
      show-icon
      :closable="false"
    />
    <template #footer
      ><el-button :disabled="w.scanning" @click="w.folderDialog = false">取消</el-button
      ><el-button
        type="primary"
        :loading="w.scanning"
        :disabled="!w.scanForm.directoryPath.trim()"
        @click="w.scanDirectory"
        >{{ w.scanning ? '正在解析目录' : '开始导入' }}</el-button
      ></template
    >
  </el-dialog>
  <el-drawer v-model="w.sheetDrawer" title="工作表详情" size="min(600px, 100vw)" destroy-on-close
    ><template v-if="w.selectedSheet"
      ><div class="detail-title">
        <h2>{{ w.selectedSheet.sheet_name }}</h2>
        <el-tag type="success">已入库</el-tag>
      </div>
      <el-descriptions :column="1" border
        ><el-descriptions-item label="来源文件">{{
          w.selectedSheet.file_name
        }}</el-descriptions-item
        ><el-descriptions-item label="数据行数">{{
          w.selectedSheet.row_count
        }}</el-descriptions-item
        ><el-descriptions-item label="字段数量">{{
          sheetFields.length
        }}</el-descriptions-item></el-descriptions
      >
      <h3 class="detail-section-heading">已解析的指标字段</h3>
      <el-table :data="sheetFields" border
        ><el-table-column prop="index" label="序号" width="65" /><el-table-column
          prop="name"
          label="指标路径 / 字段名称"
          min-width="260"
      /></el-table>
      <div class="helper-text">
        目录接口提供工作表结构；此处展示字段名称，非原始数据预览。
      </div></template
    ><template #footer
      ><el-button @click="w.sheetDrawer = false">关闭</el-button></template
    ></el-drawer
  >
  <SectionDetailDrawer :workspace="w" />
  <el-drawer v-model="w.sourceDrawer" title="原始数据来源" size="min(540px, 100vw)" append-to-body
    ><el-skeleton v-if="w.sourceLoading" :rows="6" animated /><el-alert
      v-else-if="w.sourceError"
      :title="w.sourceError"
      type="error"
      show-icon
      :closable="false"
    /><template v-else-if="w.sourceCell"
      ><el-alert
        title="以下信息来自原始单元格记录"
        description="原始值与报告引用是否一致，请结合章节核验结果判断。"
        type="info"
        show-icon
        :closable="false"
      /><el-descriptions :column="1" border class="source-detail"
        ><el-descriptions-item label="来源文件">{{ w.sourceCell.file_name }}</el-descriptions-item
        ><el-descriptions-item label="工作表">{{ w.sourceCell.sheet_name }}</el-descriptions-item
        ><el-descriptions-item label="物理坐标"
          ><el-tag>{{ w.sourceCell.cell_ref }}</el-tag></el-descriptions-item
        ><el-descriptions-item label="指标路径">{{ w.sourceCell.metric_path }}</el-descriptions-item
        ><el-descriptions-item label="原始值">{{
          w.sourceCell.raw_value
        }}</el-descriptions-item></el-descriptions
      ></template
    ><template #footer
      ><el-button type="primary" @click="w.sourceDrawer = false">关闭</el-button></template
    ></el-drawer
  >
</template>

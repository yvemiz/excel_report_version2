<script setup lang="ts">
import { Check, Key, Connection } from '@element-plus/icons-vue'
import type { Workspace } from '../composables/useWorkspace'
const { workspace: w } = defineProps<{ workspace: Workspace }>()
</script>

<template>
  <div class="page-stack settings-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-heading">
          <span>学校信息</span>
          <el-tag type="info" effect="plain">单学校实例</el-tag>
        </div>
      </template>
      <el-form
        label-position="top"
        :disabled="w.schoolSaving || Boolean(w.schoolProfile.school_name)"
        @submit.prevent="w.saveSchoolProfile"
      >
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <el-form-item label="学校名称">
              <el-input v-model="w.schoolProfile.school_name" maxlength="120" placeholder="例如 海南师范大学" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="学校代码（可选）">
              <el-input v-model="w.schoolProfile.school_code" maxlength="40" placeholder="例如 10512" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="helper-text">
          <template v-if="w.schoolProfile.school_name">
            当前部署仅服务 {{ w.schoolProfile.school_name }}，学校信息已锁定；报告生成页只读使用该名称。
          </template>
          <template v-else>
            首次保存后学校信息将锁定；导入数据中的学校名称只用于一致性校验。
          </template>
        </div>
        <el-button
          v-if="!w.schoolProfile.school_name"
          type="primary"
          :icon="Check"
          :loading="w.schoolSaving"
          native-type="submit"
        >保存学校信息</el-button>
      </el-form>
    </el-card>
    <el-alert
      title="当前账号的模型配置"
      description="配置随账号保存，重启后继续有效。API Key 加密保存在本机，页面仅显示是否已配置，不回显密钥原文。"
      type="info"
      show-icon
      :closable="false"
    />
    <el-row :gutter="24"
      ><el-col :xs="24" :lg="12"
        ><el-card shadow="never"
          ><template #header
            ><div class="card-heading">
              <span>大模型服务</span
              ><el-tag :type="w.hasApiKey ? 'success' : 'info'">{{
                w.hasApiKey ? '已保存 API Key' : '使用本地规则'
              }}</el-tag>
            </div></template
          >
          <el-form
            label-position="top"
            :disabled="w.isBusy || w.savingConfig || w.configLoading"
            @submit.prevent="w.saveConfig"
          >
            <el-form-item label="API Key"
              ><el-input
                v-model="w.modelConfig.apiKey"
                :disabled="w.modelConfig.clearApiKey"
                type="password"
                show-password
                autocomplete="off"
                :placeholder="
                  w.hasApiKey ? '已保存密钥，留空保持原配置' : '填写服务商提供的 API Key'
                "
                :prefix-icon="Key"
              />
              <div class="helper-text">
                填写新密钥可替换已保存的密钥；留空将保留原值。密钥不会写入浏览器本地存储。
              </div></el-form-item
            >
            <el-form-item>
              <el-checkbox v-model="w.modelConfig.clearApiKey"
                >停用并清除已保存的 API Key，使用本地规则</el-checkbox
              >
            </el-form-item>
            <el-form-item label="API Base URL"
              ><el-input
                v-model="w.modelConfig.baseUrl"
                :prefix-icon="Connection"
                placeholder="https://api.deepseek.com"
              />
              <div class="helper-text">
                填写兼容 Chat Completions 接口的服务根地址。
              </div></el-form-item
            >
            <el-form-item label="模型名称"
              ><el-input v-model="w.modelConfig.model" placeholder="deepseek-chat" />
              <div class="helper-text">
                默认使用 deepseek-chat，请确保服务端支持填写的模型。
              </div></el-form-item
            >
            <el-divider content-position="left">生成引擎</el-divider>
            <el-form-item label="选择执行方式"
              ><el-radio-group v-model="w.modelConfig.agentMode" class="engine-options"
                ><el-radio value="pi_agent" border>Pi-Agent 侧车（Node.js）</el-radio
                ><el-radio value="python_native" border>Python 原生</el-radio></el-radio-group
              >
              <div class="helper-text">
                Pi-Agent 模式通过 Node.js 子进程执行章节任务；Python 模式由后端直接执行。
              </div></el-form-item
            >
            <el-button type="primary" :icon="Check" :loading="w.savingConfig" native-type="submit"
              >保存并应用配置</el-button
            >
          </el-form>
        </el-card></el-col
      ><el-col :xs="24" :lg="12"
        ><el-card shadow="never" class="settings-notes"
          ><template #header>使用说明</template>
          <h3>配置大模型服务后</h3>
          <p>模型用于生成报告大纲、撰写章节和内容评审。Excel 的解析和数据入库由本地程序完成。</p>
          <el-divider />
          <h3>使用本地规则时</h3>
          <p>
            可根据已有规则生成报告并核对部分数据，无法替代完整的语义判断。请特别留意质量核验页中的评审方式。
          </p>
          <el-divider />
          <h3>任务执行期间</h3>
          <p>请等待本次任务结束后修改配置，以保持同一报告的生成条件一致。</p></el-card
        ></el-col
      ></el-row
    >
  </div>
</template>

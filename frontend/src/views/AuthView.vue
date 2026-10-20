<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { User, Lock, Right } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { AuthSubmission } from '../types'

defineProps<{ busy: boolean; error: string }>()
const emit = defineEmits<{ submit: [form: AuthSubmission]; clearError: [] }>()
const mode = ref<'login' | 'register'>('login')
const form = reactive({ username: '', displayName: '', password: '', confirmation: '' })
const formRef = ref<FormInstance>()
const isRegister = computed(() => mode.value === 'register')
const rules = computed<FormRules>(() => ({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]{3,32}$/, message: '使用3至32位字母、数字或下划线', trigger: 'blur' },
  ],
  displayName: [{ max: 40, message: '姓名最多40个字符', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    {
      min: isRegister.value ? 12 : 1,
      max: 128,
      message: isRegister.value ? '密码长度需为12至128个字符' : '密码最多128个字符',
      trigger: 'blur',
    },
  ],
  confirmation: [
    {
      validator: (_rule, value, callback) =>
        callback(value === form.password && value ? undefined : new Error('两次输入的密码不一致')),
      trigger: 'blur',
    },
  ],
}))
watch(mode, () => {
  form.password = ''
  form.confirmation = ''
  formRef.value?.clearValidate()
  emit('clearError')
})
async function submit() {
  if (!(await formRef.value?.validate().catch(() => false))) return
  emit('submit', {
    mode: mode.value,
    username: form.username.trim(),
    displayName: form.displayName.trim(),
    password: form.password,
  })
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-form-area">
      <el-card shadow="never" class="auth-card">
        <h2>{{ isRegister ? '创建你的账号' : '登录工作空间' }}</h2>
        <p class="auth-description">
          {{
            isRegister
              ? '注册后拥有独立的表格、报告和模型配置。'
              : '使用你的账号，继续本次评估工作。'
          }}
        </p>
        <el-tabs v-model="mode" stretch class="auth-tabs">
          <el-tab-pane label="账号登录" name="login" />
          <el-tab-pane label="注册账号" name="register" />
        </el-tabs>
        <el-alert
          v-if="error"
          :title="error"
          type="error"
          :closable="false"
          show-icon
          class="auth-error"
        />
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          :disabled="busy"
          @submit.prevent="submit"
        >
          <el-form-item v-if="isRegister" label="姓名或称呼（选填）" prop="displayName">
            <el-input
              v-model="form.displayName"
              size="large"
              maxlength="40"
              autocomplete="name"
              placeholder="例如：张老师"
            />
          </el-form-item>
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              size="large"
              :prefix-icon="User"
              maxlength="32"
              autocomplete="username"
              placeholder="3至32位字母、数字或下划线"
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              size="large"
              :prefix-icon="Lock"
              type="password"
              show-password
              maxlength="128"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
              :placeholder="isRegister ? '设置至少12个字符的密码' : '请输入密码'"
            />
          </el-form-item>
          <el-form-item v-if="isRegister" label="确认密码" prop="confirmation">
            <el-input
              v-model="form.confirmation"
              size="large"
              :prefix-icon="Lock"
              type="password"
              show-password
              maxlength="128"
              autocomplete="new-password"
              placeholder="再次输入密码"
            />
          </el-form-item>
          <el-button
            type="primary"
            size="large"
            native-type="submit"
            :loading="busy"
            :icon="Right"
            class="auth-submit"
            >{{ isRegister ? '注册并进入工作空间' : '登录' }}</el-button
          >
        </el-form>
        <p class="auth-note">登录状态保留7天；在公用电脑上使用后，请主动退出登录。</p>
      </el-card>
      <div class="auth-page-footer">高校教育教学质量评估 · 个人工作空间</div>
    </section>
  </main>
</template>

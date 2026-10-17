<script setup lang="ts">
import WorkspaceApp from './WorkspaceApp.vue'
import AuthView from './views/AuthView.vue'
import { useAuth } from './composables/useAuth'

const auth = useAuth()
</script>

<template>
  <div v-if="auth.checking" class="auth-loading" aria-live="polite">
    <el-card shadow="never">
      <h2>正在进入评估工作空间</h2>
      <el-skeleton :rows="3" animated />
    </el-card>
  </div>
  <WorkspaceApp
    v-else-if="auth.user"
    :key="auth.user.id"
    :user="auth.user"
    :logging-out="auth.busy"
    @logout="auth.logout"
  />
  <AuthView
    v-else
    :busy="auth.busy"
    :error="auth.error"
    @submit="auth.submit"
    @clear-error="auth.error = ''"
  />
</template>

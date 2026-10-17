import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { AuthUser, AuthSubmission } from '../types'
import { ApiError, requestJson } from '../utils/http'

export function useAuth() {
  const user = ref<AuthUser | null>(null)
  const checking = ref(true)
  const busy = ref(false)
  const error = ref('')
  const channel =
    typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('excel-report-auth') : null
  let active = true

  async function restore() {
    checking.value = true
    try {
      const result = await requestJson<{ user: AuthUser }>('/api/auth/me', {
        signal: AbortSignal.timeout(15000),
      })
      if (active) user.value = result.user
    } catch (cause) {
      if (!active) return
      user.value = null
      if (!(cause instanceof ApiError && cause.status === 401))
        error.value = '无法连接服务，请确认后端已启动后重试登录'
    } finally {
      if (active) checking.value = false
    }
  }

  async function submit(form: AuthSubmission) {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
      const result = await requestJson<{ user: AuthUser }>(`/api/auth/${form.mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: form.username,
          password: form.password,
          display_name: form.displayName,
        }),
        signal: AbortSignal.timeout(20000),
      })
      user.value = result.user
      channel?.postMessage('changed')
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '登录失败，请重试'
    } finally {
      busy.value = false
    }
  }

  async function logout() {
    if (busy.value) return
    busy.value = true
    try {
      await requestJson('/api/auth/logout', { method: 'POST', signal: AbortSignal.timeout(15000) })
      user.value = null
      error.value = ''
      channel?.postMessage('changed')
    } catch {
      ElMessage.error('退出失败，请检查服务连接后重试')
    } finally {
      busy.value = false
    }
  }

  function expired() {
    user.value = null
    error.value = '登录状态已过期，请重新登录'
    channel?.postMessage('changed')
  }
  onMounted(() => {
    window.addEventListener('session-expired', expired)
    if (channel) channel.onmessage = () => void restore()
    void restore()
  })
  onBeforeUnmount(() => {
    active = false
    channel?.close()
    window.removeEventListener('session-expired', expired)
  })
  return reactive({ user, checking, busy, error, submit, logout })
}

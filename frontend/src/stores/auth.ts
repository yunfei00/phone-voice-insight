import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { changePassword, getCurrentUser, login as loginApi, logout as logoutApi } from '@/api'
import { AUTH_TOKEN_STORAGE_KEY } from '@/config/auth'
import type { LoginPayload, UserAccount } from '@/types/api'

function storedToken(): string {
  try {
    return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(storedToken())
  const user = ref<UserAccount | null>(null)
  const initialized = ref(false)
  const loading = ref(false)
  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  const isAdmin = computed(() => user.value?.role === 'ADMIN')
  const canWrite = computed(() => ['ADMIN', 'ANALYST'].includes(user.value?.role || ''))

  function saveToken(value: string): void {
    token.value = value
    try {
      if (value) window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, value)
      else window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
    } catch {
      // The in-memory session still works if browser storage is unavailable.
    }
  }

  function clearSession(): void {
    user.value = null
    saveToken('')
  }

  async function initialize(): Promise<void> {
    if (initialized.value) return
    if (token.value) {
      try {
        user.value = await getCurrentUser()
      } catch {
        clearSession()
      }
    }
    initialized.value = true
  }

  async function login(payload: LoginPayload): Promise<void> {
    loading.value = true
    try {
      const response = await loginApi(payload)
      saveToken(response.token)
      user.value = response.user
      initialized.value = true
    } finally {
      loading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      if (token.value) await logoutApi()
    } finally {
      clearSession()
    }
  }

  async function updatePassword(oldPassword: string, newPassword: string): Promise<void> {
    const response = await changePassword({
      old_password: oldPassword,
      new_password: newPassword,
    })
    saveToken(response.token)
  }

  return {
    token,
    user,
    initialized,
    loading,
    isAuthenticated,
    isAdmin,
    canWrite,
    initialize,
    login,
    logout,
    updatePassword,
    clearSession,
  }
})

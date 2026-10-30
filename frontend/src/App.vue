<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { sendPresenceHeartbeat } from '@/api'

const auth = useAuthStore()
let heartbeatTimer: number | undefined
async function heartbeat(): Promise<void> {
  if (!auth.isAuthenticated || document.visibilityState !== 'visible') return
  try {
    await sendPresenceHeartbeat()
  } catch {
    /* retry at next interval */
  }
}
function onVisibility(): void {
  if (document.visibilityState === 'visible') void heartbeat()
}
onMounted(() => {
  void heartbeat()
  heartbeatTimer = window.setInterval(() => {
    void heartbeat()
  }, 60_000)
  document.addEventListener('visibilitychange', onVisibility)
})
watch(
  () => auth.isAuthenticated,
  (active) => {
    if (active) void heartbeat()
  },
)
onBeforeUnmount(() => {
  window.clearInterval(heartbeatTimer)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <RouterView />
</template>

<script setup lang="ts">
import {
  CircleCheck,
  Cpu,
  DataAnalysis,
  Document,
  Expand,
  Fold,
  Iphone,
  List,
  Monitor,
} from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const SIDEBAR_STORAGE_KEY = 'pvi.sidebar.collapsed'
const DESKTOP_SIDEBAR_WIDTH = 220
const COLLAPSED_SIDEBAR_WIDTH = 64

function initialSidebarCollapsed() {
  if (typeof window === 'undefined') return false
  try {
    const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY)
    if (stored === 'true') return true
    if (stored === 'false') return false
  } catch {
    // Storage can be disabled; viewport remains a safe one-time fallback.
  }
  return window.innerWidth < 1200
}

const route = useRoute()
const mobileMenuOpen = ref(false)
const sidebarCollapsed = ref(initialSidebarCollapsed())
const phaseLabel = computed(() =>
  route.path.startsWith('/analysis') ? 'Phase 5 · AI结构化分析' : 'Phase 4 · 数据治理与样本扩容',
)
const navigationItems = [
  { path: '/dashboard', label: '数据总览', icon: Monitor },
  { path: '/products', label: '手机产品', icon: Iphone },
  { path: '/collection-tasks', label: '采集任务', icon: List },
  { path: '/reviews', label: '原始反馈', icon: Document },
  { path: '/data-quality', label: '数据质量', icon: CircleCheck },
  { path: '/analysis', label: 'AI分析', icon: DataAnalysis },
  { path: '/system', label: '系统状态', icon: Cpu },
]
const activePath = computed(
  () =>
    navigationItems.find(
      (item) => route.path === item.path || route.path.startsWith(`${item.path}/`),
    )?.path || route.path,
)
const sidebarWidth = computed(() =>
  sidebarCollapsed.value ? COLLAPSED_SIDEBAR_WIDTH : DESKTOP_SIDEBAR_WIDTH,
)

watch(sidebarCollapsed, (collapsed) => {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed))
  } catch {
    // Keep the interaction working when storage is unavailable.
  }
})
</script>

<template>
  <div class="app-shell" :style="{ '--sidebar-width': `${sidebarWidth}px` }">
    <aside class="sidebar" :class="{ open: mobileMenuOpen, collapsed: sidebarCollapsed }">
      <div class="brand">
        <span class="brand-mark">PVI</span>
        <div v-if="!sidebarCollapsed" class="brand-copy">
          <strong>Phone Voice Insight</strong>
          <small>荣耀俱乐部公开评论洞察</small>
        </div>
      </div>
      <el-menu
        :default-active="activePath"
        :collapse="sidebarCollapsed"
        :collapse-transition="true"
        router
        class="nav-menu"
      >
        <el-menu-item v-for="item in navigationItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label }}</template>
        </el-menu-item>
      </el-menu>
    </aside>
    <main class="main">
      <header class="topbar">
        <el-button class="menu-button" text @click="mobileMenuOpen = !mobileMenuOpen"
          >菜单</el-button
        >
        <el-tooltip :content="sidebarCollapsed ? '展开菜单' : '收起菜单'" placement="right">
          <el-button
            class="collapse-button"
            text
            circle
            :aria-label="sidebarCollapsed ? '展开菜单' : '收起菜单'"
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            <el-icon><Expand v-if="sidebarCollapsed" /><Fold v-else /></el-icon>
          </el-button>
        </el-tooltip>
        <span>{{ phaseLabel }}</span>
      </header>
      <section class="content" @click="mobileMenuOpen = false">
        <RouterView />
      </section>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  width: 100%;
  min-height: 100vh;
  display: flex;
  overflow-x: clip;
}

.sidebar {
  position: sticky;
  top: 0;
  z-index: 20;
  width: var(--sidebar-width);
  height: 100vh;
  flex: 0 0 var(--sidebar-width);
  padding: 20px 14px;
  color: #e5e7eb;
  background: #121a2d;
  transition:
    width 0.2s ease,
    flex-basis 0.2s ease,
    padding 0.2s ease;
}

.sidebar.collapsed {
  padding-right: 4px;
  padding-left: 4px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 8px 24px;
}

.sidebar.collapsed .brand {
  justify-content: center;
  padding-right: 0;
  padding-left: 0;
}

.sidebar.collapsed .brand-mark {
  width: 44px;
  height: 44px;
}

.brand-mark {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  color: #fff;
  font-weight: 800;
  background: #3b82f6;
  border-radius: 12px;
}

.brand strong,
.brand small {
  display: block;
}

.brand strong {
  font-size: 14px;
}

.brand small {
  margin-top: 4px;
  color: #9ca3af;
  font-size: 11px;
}

.nav-menu {
  width: 100%;
  border: 0;
  background: transparent;
}

.nav-menu :deep(.el-menu-item) {
  margin: 4px 0;
  color: #b8c0d1;
  border-radius: 8px;
}

.nav-menu :deep(.el-menu-item:hover),
.nav-menu :deep(.el-menu-item.is-active) {
  color: #fff;
  background: #25314d;
}

.nav-menu.el-menu--collapse :deep(.el-menu-item) {
  width: 44px;
  height: 40px;
  justify-content: center;
  padding: 0 !important;
  margin: 4px auto;
}

.nav-menu.el-menu--collapse :deep(.el-menu-item .el-icon) {
  margin: 0;
}

.nav-menu.el-menu--collapse :deep(.el-menu-tooltip__trigger) {
  justify-content: center;
  padding: 0 !important;
}

.main {
  min-width: 0;
  flex: 1 1 auto;
}

.topbar {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  color: #6b7280;
  background: #fff;
  border-bottom: 1px solid #e7eaf0;
}

.menu-button {
  display: none;
}

.collapse-button {
  display: inline-flex;
}

.content {
  padding: 28px;
}

@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    flex-basis: auto;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .main {
    width: 100%;
    flex-basis: 100%;
  }

  .topbar {
    justify-content: space-between;
    padding: 0 16px;
  }

  .menu-button {
    display: inline-flex;
  }

  .collapse-button {
    display: none;
  }

  .content {
    padding: 18px 14px;
  }
}
</style>

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
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const mobileMenuOpen = ref(false)
const sidebarCollapsed = ref(false)
const activePath = computed(() => route.path)
const phaseLabel = computed(() =>
  route.path === '/analysis' ? 'Phase 5 · AI结构化分析' : 'Phase 4 · 数据治理与样本扩容',
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
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ open: mobileMenuOpen, collapsed: sidebarCollapsed }">
      <div class="brand">
        <span class="brand-mark">PVI</span>
        <div v-show="!sidebarCollapsed" class="brand-copy">
          <strong>Phone Voice Insight</strong>
          <small>荣耀俱乐部公开讨论洞察</small>
        </div>
      </div>
      <el-menu
        :default-active="activePath"
        :collapse="sidebarCollapsed"
        :collapse-transition="false"
        router
        class="nav-menu"
      >
        <el-menu-item v-for="item in navigationItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>{{ item.label }}
        </el-menu-item>
      </el-menu>
    </aside>
    <main class="main" :class="{ expanded: sidebarCollapsed }">
      <header class="topbar">
        <el-button class="menu-button" text @click="mobileMenuOpen = !mobileMenuOpen"
          >菜单</el-button
        >
        <el-button
          class="collapse-button"
          text
          :aria-label="sidebarCollapsed ? '展开左侧菜单' : '折叠左侧菜单'"
          @click="sidebarCollapsed = !sidebarCollapsed"
        >
          <el-icon><Expand v-if="sidebarCollapsed" /><Fold v-else /></el-icon>
          {{ sidebarCollapsed ? '展开' : '折叠' }}
        </el-button>
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
  min-height: 100vh;
  display: flex;
}

.sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 20;
  width: 250px;
  padding: 20px 14px;
  color: #e5e7eb;
  background: #121a2d;
  transition:
    width 0.2s ease,
    padding 0.2s ease;
  overflow: hidden;
}

.sidebar.collapsed {
  width: 72px;
  padding-right: 8px;
  padding-left: 8px;
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
  width: 40px;
  height: 40px;
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

.main {
  width: calc(100% - 250px);
  margin-left: 250px;
  transition:
    width 0.2s ease,
    margin-left 0.2s ease;
}

.main.expanded {
  width: calc(100% - 72px);
  margin-left: 72px;
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
    width: 250px;
    padding: 20px 14px;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .sidebar.collapsed .brand {
    justify-content: flex-start;
  }

  .sidebar.collapsed .brand-copy {
    display: block !important;
  }

  .main {
    width: 100%;
    margin-left: 0;
  }

  .main.expanded {
    width: 100%;
    margin-left: 0;
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

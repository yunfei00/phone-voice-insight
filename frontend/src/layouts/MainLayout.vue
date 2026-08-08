<script setup lang="ts">
import {
  CircleCheck,
  Cpu,
  DataAnalysis,
  Document,
  Iphone,
  List,
  Monitor,
} from '@element-plus/icons-vue'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const mobileMenuOpen = ref(false)
const activePath = computed(() => route.path)
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ open: mobileMenuOpen }">
      <div class="brand">
        <span class="brand-mark">PVI</span>
        <div>
          <strong>Phone Voice Insight</strong>
          <small>荣耀俱乐部公开讨论洞察</small>
        </div>
      </div>
      <el-menu :default-active="activePath" router class="nav-menu">
        <el-menu-item index="/dashboard"
          ><el-icon><Monitor /></el-icon>数据总览</el-menu-item
        >
        <el-menu-item index="/products"
          ><el-icon><Iphone /></el-icon>手机产品</el-menu-item
        >
        <el-menu-item index="/collection-tasks"
          ><el-icon><List /></el-icon>采集任务</el-menu-item
        >
        <el-menu-item index="/reviews"
          ><el-icon><Document /></el-icon>原始反馈</el-menu-item
        >
        <el-menu-item index="/data-quality"
          ><el-icon><CircleCheck /></el-icon>数据质量</el-menu-item
        >
        <el-menu-item index="/analysis"
          ><el-icon><DataAnalysis /></el-icon>AI 分析（后续）</el-menu-item
        >
        <el-menu-item index="/system"
          ><el-icon><Cpu /></el-icon>系统状态</el-menu-item
        >
      </el-menu>
    </aside>
    <main class="main">
      <header class="topbar">
        <el-button class="menu-button" text @click="mobileMenuOpen = !mobileMenuOpen"
          >菜单</el-button
        >
        <span>Phase 4 · 数据治理与样本扩容</span>
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
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 8px 24px;
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
}

.topbar {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 28px;
  color: #6b7280;
  background: #fff;
  border-bottom: 1px solid #e7eaf0;
}

.menu-button {
  display: none;
}

.content {
  padding: 28px;
}

@media (max-width: 768px) {
  .sidebar {
    transform: translateX(-100%);
    transition: transform 0.2s ease;
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .main {
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

  .content {
    padding: 18px 14px;
  }
}
</style>

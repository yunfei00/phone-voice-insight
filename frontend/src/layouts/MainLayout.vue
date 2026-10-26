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
  UserFilled,
} from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { CURRENT_PHASE_LABEL } from '@/config/project'
import { useAuthStore } from '@/stores/auth'

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
const router = useRouter()
const auth = useAuthStore()
const mobileMenuOpen = ref(false)
const sidebarCollapsed = ref(initialSidebarCollapsed())
const baseNavigationItems = [
  { path: '/dashboard', label: '数据总览', icon: Monitor },
  { path: '/products', label: '手机产品', icon: Iphone },
  { path: '/collection-tasks', label: '采集任务', icon: List },
  { path: '/reviews', label: '原始反馈', icon: Document },
  { path: '/data-quality', label: '数据质量', icon: CircleCheck },
  { path: '/analysis', label: 'AI分析', icon: DataAnalysis },
  { path: '/system', label: '系统状态', icon: Cpu },
]
const navigationItems = computed(() => [
  ...baseNavigationItems,
  ...(auth.isAdmin ? [{ path: '/users', label: '用户管理', icon: UserFilled }] : []),
])
const activePath = computed(
  () =>
    navigationItems.value.find(
      (item) => route.path === item.path || route.path.startsWith(`${item.path}/`),
    )?.path || route.path,
)
const sidebarWidth = computed(() =>
  sidebarCollapsed.value ? COLLAPSED_SIDEBAR_WIDTH : DESKTOP_SIDEBAR_WIDTH,
)
const passwordDialogVisible = ref(false)
const passwordFormRef = ref<FormInstance>()
const passwordForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const passwordRules: FormRules = {
  oldPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback: (error?: Error) => void) => {
        callback(value === passwordForm.newPassword ? undefined : new Error('两次输入的密码不一致'))
      },
      trigger: 'blur',
    },
  ],
}

async function handleUserCommand(command: string): Promise<void> {
  if (command === 'password') {
    passwordDialogVisible.value = true
    return
  }
  if (command === 'logout') {
    await auth.logout()
    await router.replace('/login')
  }
}

async function submitPassword(): Promise<void> {
  if (!(await passwordFormRef.value?.validate().catch(() => false))) return
  await auth.updatePassword(passwordForm.oldPassword, passwordForm.newPassword)
  passwordDialogVisible.value = false
  passwordForm.oldPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
  ElMessage.success('密码修改成功')
}

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
        <div class="topbar-right">
          <span class="phase-label">{{ CURRENT_PHASE_LABEL }}</span>
          <el-dropdown trigger="click" @command="handleUserCommand">
            <button class="user-trigger" type="button">
              <el-avatar :size="32"
                ><el-icon><UserFilled /></el-icon
              ></el-avatar>
              <span class="user-name">{{ auth.user?.username }}</span>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  {{
                    auth.user?.role === 'ADMIN'
                      ? '管理员'
                      : auth.user?.role === 'ANALYST'
                        ? '分析员'
                        : '只读用户'
                  }}
                </el-dropdown-item>
                <el-dropdown-item command="password" divided>修改密码</el-dropdown-item>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>
      <section class="content" @click="mobileMenuOpen = false">
        <RouterView />
      </section>
    </main>
    <el-dialog v-model="passwordDialogVisible" title="修改密码" width="min(440px, 92vw)">
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-width="90px"
      >
        <el-form-item label="当前密码" prop="oldPassword">
          <el-input v-model="passwordForm.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="passwordForm.newPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="passwordForm.confirmPassword" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitPassword">保存</el-button>
      </template>
    </el-dialog>
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

.topbar-right,
.user-trigger {
  display: flex;
  align-items: center;
}

.topbar-right {
  gap: 20px;
}

.user-trigger {
  gap: 8px;
  padding: 0;
  color: #3f4757;
  font: inherit;
  background: transparent;
  border: 0;
  cursor: pointer;
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

  .phase-label,
  .user-name {
    display: none;
  }
}
</style>

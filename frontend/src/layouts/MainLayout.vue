<script setup lang="ts">
import {
  CircleCheck,
  Cpu,
  DataAnalysis,
  Document,
  Expand,
  Fold,
  Iphone,
  ChatLineSquare,
  ChatDotRound,
  List,
  Monitor,
  TrendCharts,
  Warning,
  Notebook,
  Operation,
  Setting,
  UserFilled,
} from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

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
const projectionMode = computed(() => route.path === '/dashboard' && route.query.fullscreen === '1')
const mobileMenuOpen = ref(false)
const sidebarCollapsed = ref(initialSidebarCollapsed())
const baseNavigationItems = [
  { path: '/dashboard', label: '智能驾驶舱', icon: Monitor },
  { path: '/ai-assistant', label: 'AI智能助手', icon: ChatDotRound },
  { path: '/comparison', label: '产品对比中心', icon: TrendCharts },
  { path: '/issues', label: '用户问题洞察', icon: Warning },
  { path: '/insight-reports', label: 'AI洞察报告', icon: Notebook },
  { path: '/operations', label: '数据运行监控', icon: Operation },
  { path: '/products', label: '手机产品', icon: Iphone },
  { path: '/threads', label: '帖子视图', icon: ChatLineSquare },
  { path: '/reviews', label: '原始数据', icon: Document },
  { path: '/data-quality', label: '数据质量', icon: CircleCheck },
  { path: '/structured-analysis', label: 'AI结构化分析', icon: DataAnalysis },
  { path: '/ai-tasks', label: 'AI任务中心', icon: List, advanced: true },
  { path: '/ai-settings', label: 'AI配置', icon: Setting, advanced: true },
  { path: '/system', label: '系统状态', icon: Cpu, advanced: true },
]
const navigationItems = computed(() => [
  ...baseNavigationItems
    .filter((item) =>
      item.path === '/ai-settings' ? auth.isAdmin : !item.advanced || auth.canWrite,
    )
    .flatMap((item) =>
      item.path === '/products' && auth.isAdmin
        ? [item, { path: '/collection-tasks', label: '采集任务', icon: List }]
        : [item],
    ),
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
  <div
    class="app-shell"
    :class="{ 'projection-shell': projectionMode }"
    :style="{ '--sidebar-width': `${sidebarWidth}px` }"
  >
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
  color: var(--pvi-text);
  background: #081728;
  border-right: 1px solid var(--pvi-border);
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
  background: linear-gradient(135deg, var(--pvi-blue), #2478d3);
  box-shadow: 0 0 22px #35b9f044;
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
  color: var(--pvi-muted);
  font-size: 11px;
}

.nav-menu {
  width: 100%;
  border: 0;
  background: transparent;
}

.nav-menu :deep(.el-menu-item) {
  margin: 4px 0;
  color: var(--pvi-muted);
  border-radius: 8px;
}

.nav-menu :deep(.el-menu-item:hover),
.nav-menu :deep(.el-menu-item.is-active) {
  color: #fff;
  background: #17334e;
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
  background: var(--pvi-bg);
}

.topbar {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  color: var(--pvi-muted);
  background: #0a192aee;
  border-bottom: 1px solid var(--pvi-border);
  backdrop-filter: blur(12px);
}

.menu-button {
  display: none;
}

.collapse-button {
  display: inline-flex;
}

.phase-label {
  margin-right: auto;
  margin-left: 12px;
  color: var(--pvi-muted);
  font-size: 13px;
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
  color: var(--pvi-text);
  font: inherit;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.projection-shell .sidebar,
.projection-shell .topbar {
  display: none;
}

.projection-shell .content {
  padding: 0;
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

  .phase-label {
    margin-right: 8px;
    margin-left: 8px;
    font-size: 12px;
  }

  .content {
    padding: 18px 14px;
  }

  .user-name {
    display: none;
  }
}
</style>

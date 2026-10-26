<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { createUser, deleteUser, getUsers, resetUserPassword, updateUser } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { UserAccount, UserPayload, UserRole } from '@/types/api'

const auth = useAuthStore()
const users = ref<UserAccount[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')
const dialogVisible = ref(false)
const editing = ref<UserAccount | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<UserPayload>({
  username: '',
  email: '',
  first_name: '',
  last_name: '',
  role: 'VIEWER',
  is_active: true,
  password: '',
})
const dialogTitle = computed(() => (editing.value ? '编辑用户' : '新建用户'))
const roleLabels: Record<UserRole, string> = {
  ADMIN: '管理员',
  ANALYST: '分析员',
  VIEWER: '只读用户',
}
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  password: [
    {
      validator: (_rule, value: string, callback: (error?: Error) => void) => {
        if (!editing.value && !value) callback(new Error('创建用户时必须设置密码'))
        else if (value && value.length < 8) callback(new Error('密码至少 8 位'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

async function loadUsers(): Promise<void> {
  loading.value = true
  try {
    const result = await getUsers({
      page: page.value,
      page_size: pageSize.value,
      search: search.value || undefined,
    })
    users.value = result.results
    total.value = result.count
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editing.value = null
  Object.assign(form, {
    username: '',
    email: '',
    first_name: '',
    last_name: '',
    role: 'VIEWER',
    is_active: true,
    password: '',
  })
  dialogVisible.value = true
}

function openEdit(user: UserAccount): void {
  editing.value = user
  Object.assign(form, {
    username: user.username,
    email: user.email,
    first_name: user.first_name,
    last_name: user.last_name,
    role: user.role,
    is_active: user.is_active,
    password: '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate().catch(() => false))) return
  const payload: UserPayload = { ...form }
  if (!payload.password) delete payload.password
  if (editing.value) await updateUser(editing.value.id, payload)
  else await createUser(payload)
  dialogVisible.value = false
  ElMessage.success(editing.value ? '用户已更新' : '用户已创建')
  await loadUsers()
}

async function remove(user: UserAccount): Promise<void> {
  await ElMessageBox.confirm(`确认删除用户“${user.username}”吗？`, '删除用户', { type: 'warning' })
  await deleteUser(user.id)
  ElMessage.success('用户已删除')
  await loadUsers()
}

async function resetPassword(user: UserAccount): Promise<void> {
  const result = await ElMessageBox.prompt(`为“${user.username}”设置新密码`, '重置密码', {
    inputType: 'password',
    inputPattern: /^.{8,}$/,
    inputErrorMessage: '密码至少 8 位',
  })
  await resetUserPassword(user.id, result.value)
  ElMessage.success('密码已重置，该用户需要重新登录')
}

async function toggleActive(user: UserAccount): Promise<void> {
  try {
    await updateUser(user.id, { is_active: user.is_active })
    ElMessage.success(user.is_active ? '用户已启用' : '用户已停用')
  } catch (error) {
    user.is_active = !user.is_active
    throw error
  }
}

onMounted(loadUsers)
</script>

<template>
  <div>
    <header class="page-header">
      <div>
        <h1 class="page-title">用户管理</h1>
        <p class="page-description">管理登录账号、角色和使用权限。</p>
      </div>
      <el-button type="primary" @click="openCreate">新建用户</el-button>
    </header>
    <section class="panel">
      <div class="toolbar">
        <el-input
          v-model="search"
          clearable
          placeholder="搜索用户名、姓名或邮箱"
          @keyup.enter="loadUsers"
        />
        <el-button @click="loadUsers">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="users">
        <el-table-column prop="username" label="用户名" min-width="130" />
        <el-table-column label="姓名" min-width="120">
          <template #default="scope">{{
            [scope.row.last_name, scope.row.first_name].join('') || '-'
          }}</template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="190">
          <template #default="scope">{{ scope.row.email || '-' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="110">
          <template #default="scope"
            ><el-tag>{{ roleLabels[scope.row.role as UserRole] }}</el-tag></template
          >
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              :disabled="scope.row.id === auth.user?.id"
              @change="toggleActive(scope.row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="最后登录" min-width="170">
          <template #default="scope">{{
            scope.row.last_login ? new Date(scope.row.last_login).toLocaleString() : '从未登录'
          }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="openEdit(scope.row)">编辑</el-button>
            <el-button link @click="resetPassword(scope.row)">重置密码</el-button>
            <el-button
              link
              type="danger"
              :disabled="scope.row.id === auth.user?.id"
              @click="remove(scope.row)"
              >删除</el-button
            >
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        class="pagination"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @change="loadUsers"
      />
    </section>
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="min(560px, 94vw)"
      @closed="formRef?.clearValidate()"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="用户名" prop="username"
          ><el-input v-model="form.username"
        /></el-form-item>
        <el-form-item label="姓名">
          <div class="name-fields">
            <el-input v-model="form.last_name" placeholder="姓" /><el-input
              v-model="form.first_name"
              placeholder="名"
            />
          </div>
        </el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" type="email" /></el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option
              v-for="(label, value) in roleLabels"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="editing ? '新密码' : '初始密码'" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="editing ? '不修改请留空' : '至少 8 位'"
          />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.is_active" /></el-form-item>
      </el-form>
      <template #footer
        ><el-button @click="dialogVisible = false">取消</el-button
        ><el-button type="primary" @click="submit">保存</el-button></template
      >
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  max-width: 520px;
  margin-bottom: 18px;
}
.pagination {
  justify-content: flex-end;
  margin-top: 18px;
}
.name-fields {
  width: 100%;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
@media (max-width: 768px) {
  .pagination {
    justify-content: flex-start;
    overflow-x: auto;
  }
}
</style>

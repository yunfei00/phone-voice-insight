<script setup lang="ts">
import { Lock, User } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate().catch(() => false))) return
  await auth.login(form)
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
  await router.replace(redirect)
}
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <div class="login-brand">PVI</div>
      <h1>Phone Voice Insight</h1>
      <p>手机用户口碑洞察平台</p>
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="submit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" autocomplete="username">
            <template #prefix
              ><el-icon><User /></el-icon
            ></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            autocomplete="current-password"
            show-password
          >
            <template #prefix
              ><el-icon><Lock /></el-icon
            ></template>
          </el-input>
        </el-form-item>
        <el-button type="primary" :loading="auth.loading" class="login-button" @click="submit">
          登录
        </el-button>
      </el-form>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: linear-gradient(145deg, #f2f6fc 0%, #e8eef8 55%, #dfe9f6 100%);
}

.login-card {
  width: min(420px, 100%);
  padding: 38px;
  text-align: center;
  background: #fff;
  border-radius: 18px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 20px 60px rgb(30 58 98 / 10%);
}

.login-brand {
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  margin: 0 auto 18px;
  color: #fff;
  font-weight: 800;
  font-size: 20px;
  background: #2459a6;
  border-radius: 15px;
}

h1 {
  margin: 0;
  color: #1d3554;
  font-size: 24px;
}
p {
  margin: 8px 0 28px;
  color: #64748b;
}
.login-button {
  width: 100%;
  background: #2459a6;
  border-color: #2459a6;
}
.login-card :deep(.el-input__wrapper) {
  background: #f8fafc;
  box-shadow: 0 0 0 1px #d8e1ec inset;
}
.login-card :deep(.el-input__inner) {
  color: #1d3554;
}
.login-card :deep(.el-input__inner::placeholder),
.login-card :deep(.el-input__prefix) {
  color: #8493a7;
}
.login-card :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #2459a6 inset;
}
</style>

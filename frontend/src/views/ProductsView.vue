<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getProducts } from '@/api'
import type { Product } from '@/types/api'

const products = ref<Product[]>([])
const loading = ref(false)
const error = ref('')

async function loadProducts(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    products.value = (await getProducts({ page_size: 100 })).results
  } catch {
    error.value = '产品列表加载失败。'
  } finally {
    loading.value = false
  }
}

onMounted(loadProducts)
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">手机产品</h1>
        <p class="page-description">
          维护品牌、产品系列与可选版本；复杂编辑请暂时使用 Django Admin。
        </p>
      </div>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />
    <div class="panel">
      <el-table v-loading="loading" :data="products" empty-text="暂无产品">
        <el-table-column prop="name" label="产品" min-width="170" />
        <el-table-column prop="brand.name" label="品牌" width="120" />
        <el-table-column prop="series" label="系列" width="120" />
        <el-table-column label="版本" min-width="220">
          <template #default="{ row }: { row: Product }">
            <el-tag v-for="variant in row.variants" :key="variant.id" class="variant-tag">
              {{ variant.sku_name }}{{ variant.color ? ` · ${variant.color}` : '' }}
            </el-tag>
            <span v-if="!row.variants.length">未录入</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }: { row: Product }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{
              row.is_active ? '启用' : '停用'
            }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}

.variant-tag {
  margin: 3px 6px 3px 0;
}
</style>

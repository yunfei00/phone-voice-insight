<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getManualQueue, setManualDisposition, type ManualQueueItem } from '@/api'

const rows = ref<ManualQueueItem[]>([])
const loading = ref(false)
const selected = ref<ManualQueueItem | null>(null)
const editorOpen = ref(false)
const annotationText = ref('')
const reason = ref('')
const filter = ref('')
const labels: Record<string, string> = {
  IN_REVIEW: '待标注', SUBMITTED: '待审核', APPROVED: '已审核',
  EXCLUDED: '已排除', DEFERRED: '已暂缓',
}
async function load() {
  loading.value = true
  try {
    rows.value = (await getManualQueue(filter.value || undefined)).results
  } catch {
    ElMessage.error('人工待办加载失败')
  } finally {
    loading.value = false
  }
}
function openEditor(item: ManualQueueItem) {
  selected.value = item
  annotationText.value = Object.keys(item.annotation || {}).length
    ? JSON.stringify(item.annotation, null, 2) : ''
  reason.value = item.reason || '人工标注'
  editorOpen.value = true
}
async function submit() {
  if (!selected.value) return
  try {
    const annotation = JSON.parse(annotationText.value) as Record<string, unknown>
    await setManualDisposition({
      content_id: selected.value.content_id, status: 'SUBMITTED',
      reason: reason.value.trim() || '人工标注', annotation,
    })
    ElMessage.success('提交成功，等待管理员审核')
    editorOpen.value = false
    await load()
  } catch {
    ElMessage.error('提交失败，请核对 JSON、标签和原文证据')
  }
}
async function approve(item: ManualQueueItem) {
  try {
    await ElMessageBox.confirm('请确认标注及原文证据准确，审核后将纳入正式统计。', '审核确认')
    await setManualDisposition({
      content_id: item.content_id, status: 'APPROVED',
      reason: '管理员审核通过', annotation: item.annotation,
    })
    ElMessage.success('审核通过')
    await load()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error('审核失败，请确认管理员权限和标注完整性')
  }
}
onMounted(load)
</script>

<template>
  <section class="manual-page">
    <header>
      <h1>AI 失败人工处理</h1>
      <p>从 AI 任务中心转人工的帖子统一在此处理。人工标注需符合现有 TAXONOMY JSON Schema。</p>
    </header>
    <el-card>
      <div class="toolbar">
        <el-select v-model="filter" placeholder="处理状态" style="width: 180px" @change="load">
          <el-option label="全部" value="" />
          <el-option label="待标注" value="IN_REVIEW" />
          <el-option label="待审核" value="SUBMITTED" />
          <el-option label="已审核" value="APPROVED" />
          <el-option label="已暂缓" value="DEFERRED" />
          <el-option label="已排除" value="EXCLUDED" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" empty-text="暂无人工待办">
        <el-table-column prop="content_id" label="帖子 ID" width="110" />
        <el-table-column prop="product" label="机型" width="140" />
        <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{row}">{{ labels[row.status] || row.status }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="处理原因" min-width="170" show-overflow-tooltip />
        <el-table-column label="操作" width="220">
          <template #default="{row}">
            <el-button v-if="row.status === 'IN_REVIEW' || row.status === 'SUBMITTED'" link type="primary" @click="openEditor(row)">
              {{ row.status === 'SUBMITTED' ? '查看标注' : '开始标注' }}
            </el-button>
            <el-button v-if="row.status === 'SUBMITTED'" link type="success" @click="approve(row)">审核通过</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-dialog v-model="editorOpen" title="人工结构化标注" width="min(900px, 95%)" destroy-on-close>
      <template v-if="selected">
        <p><strong>帖子 #{{ selected.content_id }} · {{ selected.product }}</strong></p>
        <p>{{ selected.title }}</p>
        <el-input :model-value="selected.content" type="textarea" :rows="6" readonly />
        <p class="help">请以原文为依据填写结构化 JSON，证据文本及起止位置必须与上方原文一致。</p>
        <el-input v-model="annotationText" type="textarea" :rows="12" placeholder="粘贴符合 TAXONOMY Schema 的完整 JSON" />
        <el-input v-model="reason" placeholder="处理说明" style="margin-top: 12px" />
      </template>
      <template #footer>
        <el-button @click="editorOpen = false">取消</el-button>
        <el-button type="primary" @click="submit">提交审核</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.manual-page { display: grid; gap: 18px; }
.manual-page h1 { margin: 0; }
.manual-page p, .help { color: var(--el-text-color-secondary); }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
</style>

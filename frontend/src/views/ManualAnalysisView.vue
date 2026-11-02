<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getManualQueue, getTaxonomy, setManualDisposition, type ManualQueueItem } from '@/api'
import type { TaxonomyDefinition } from '@/types/api'

type Choice = { label: string; value: string }
type AspectForm = {
  aspect_code: string; topic_code: string; sentiment: string; intent: string
  issue_type: string; severity: string; phenomenon: string; evidence_text: string
}
const rows = ref<ManualQueueItem[]>([])
const loading = ref(false)
const selected = ref<ManualQueueItem | null>(null)
const editorOpen = ref(false)
const reason = ref('')
const filter = ref('IN_REVIEW')
const taxonomy = ref<TaxonomyDefinition | null>(null)
const overallSentiment = ref('NEGATIVE')
const contentType = ref('COMMUNITY_THREAD')
const relevance = ref('RELEVANT')
const summary = ref('')
const aspects = ref<AspectForm[]>([])
const labels: Record<string, string> = {
  IN_REVIEW: '待标注', SUBMITTED: '待审核', APPROVED: '已审核',
  EXCLUDED: '已排除', DEFERRED: '已暂缓',
}
const sentiments: Choice[] = [
  {label:'正面',value:'POSITIVE'}, {label:'中性',value:'NEUTRAL'},
  {label:'负面',value:'NEGATIVE'}, {label:'正负混合',value:'MIXED'}, {label:'无法判断',value:'UNKNOWN'},
]
const intents: Choice[] = [
  {label:'使用体验',value:'EXPERIENCE'}, {label:'投诉',value:'COMPLAINT'},
  {label:'表扬',value:'PRAISE'}, {label:'咨询',value:'QUESTION'},
  {label:'建议',value:'SUGGESTION'}, {label:'对比',value:'COMPARISON'},
  {label:'购买意向',value:'PURCHASE_INTENT'}, {label:'售后请求',value:'SERVICE_REQUEST'},
  {label:'其他',value:'OTHER'}, {label:'无法判断',value:'UNKNOWN'},
]
const issueTypes: Choice[] = [
  {label:'质量',value:'QUALITY'}, {label:'性能',value:'PERFORMANCE'},
  {label:'易用性',value:'USABILITY'}, {label:'兼容性',value:'COMPATIBILITY'},
  {label:'可靠性',value:'RELIABILITY'}, {label:'隐私',value:'PRIVACY'},
  {label:'服务',value:'SERVICE'}, {label:'价格',value:'PRICE'},
  {label:'需求',value:'REQUIREMENT'}, {label:'其他',value:'OTHER'},
  {label:'无法判断',value:'UNKNOWN'},
]
const severities: Choice[] = [
  {label:'严重',value:'CRITICAL'}, {label:'高',value:'HIGH'},
  {label:'中',value:'MEDIUM'}, {label:'低',value:'LOW'},
  {label:'仅供参考',value:'INFO'}, {label:'无法判断',value:'UNKNOWN'},
]
const contentTypes: Choice[] = [
  {label:'用户评价',value:'USER_REVIEW'}, {label:'社区主帖',value:'COMMUNITY_THREAD'},
  {label:'社区回复',value:'COMMUNITY_REPLY'}, {label:'官方回复',value:'OFFICIAL_REPLY'},
  {label:'物流或服务',value:'LOGISTICS_OR_SERVICE'}, {label:'其他',value:'OTHER'},
]
const relevanceOptions: Choice[] = [
  {label:'相关',value:'RELEVANT'}, {label:'部分相关',value:'PARTIAL'},
  {label:'不相关',value:'IRRELEVANT'}, {label:'无法判断',value:'UNKNOWN'},
]
const domains = computed(() => (taxonomy.value?.domains || []).filter(item => item.enabled))
function topics(code: string) {
  return (domains.value.find(item => item.tag_id === code)?.children || []).filter(item => item.enabled)
}
function newAspect(): AspectForm {
  return {aspect_code:'', topic_code:'', sentiment:'NEGATIVE', intent:'COMPLAINT',
    issue_type:'QUALITY', severity:'MEDIUM', phenomenon:'', evidence_text:''}
}
function setDomain(item: AspectForm, code: string) {
  item.aspect_code = code
  item.topic_code = ''
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
async function openEditor(item: ManualQueueItem) {
  if (!taxonomy.value) {
    try { taxonomy.value = await getTaxonomy() } catch {
      ElMessage.error('标签体系加载失败，请刷新重试')
      return
    }
  }
  selected.value = item
  const saved = item.annotation || {}
  overallSentiment.value = String(saved.overall_sentiment || 'NEGATIVE')
  contentType.value = String(saved.content_type || 'COMMUNITY_THREAD')
  relevance.value = String(saved.relevance || 'RELEVANT')
  summary.value = String(saved.summary || '')
  reason.value = item.reason || '人工复核'
  const existing = Array.isArray(saved.aspects) ? saved.aspects : []
  aspects.value = existing.length
    ? existing.map(value => {
        const row = value as Record<string, unknown>
        return {aspect_code:String(row.aspect_code || ''), topic_code:String(row.topic_code || ''),
          sentiment:String(row.sentiment || 'NEGATIVE'), intent:String(row.intent || 'COMPLAINT'),
          issue_type:String(row.issue_type || 'QUALITY'), severity:String(row.severity || 'MEDIUM'),
          phenomenon:String(row.phenomenon || ''), evidence_text:String(row.evidence_text || '')}
      })
    : [newAspect()]
  editorOpen.value = true
}
function validSourceUrl(url: string | undefined): string {
  if (!url) return ''
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : ''
  } catch { return '' }
}
function evidenceOffset(source: string, evidence: string): number {
  return source.indexOf(evidence)
}
async function submit() {
  const item = selected.value
  if (!item) return
  if (!summary.value.trim()) { ElMessage.warning('请填写内容摘要'); return }
  if (!reason.value.trim()) { ElMessage.warning('请填写处理说明'); return }
  const output = []
  for (const aspect of aspects.value) {
    if (!aspect.aspect_code || !aspect.topic_code) {
      ElMessage.warning('请选择问题分类和具体问题')
      return
    }
    const evidence = aspect.evidence_text
    const start = evidenceOffset(item.content, evidence)
    if (!evidence || start < 0) {
      ElMessage.warning('证据原文必须是帖子中连续出现的一段文字，请直接复制原文')
      return
    }
    output.push({
      business_domains:[aspect.aspect_code], aspect_code:aspect.aspect_code,
      topic_code:aspect.topic_code, sentiment:aspect.sentiment, intent:aspect.intent,
      issue_type:aspect.issue_type, severity:aspect.severity,
      scenario:null, trigger:null, phenomenon:aspect.phenomenon.trim() || null,
      target_product:null, compared_products:[], relation_type:'SELF',
      evidence_text:evidence, evidence_start:start, evidence_end:start+evidence.length,
      confidence:1, review_required:false,
    })
  }
  const annotation = {
    schema_version:'1.0.0', taxonomy_version:'1.0.0',
    overall_sentiment:overallSentiment.value, language:'zh',
    content_type:contentType.value, relevance:relevance.value,
    summary:summary.value.trim(), model_mentions:[], aspects:output,
  }
  try {
    await setManualDisposition({
      content_id:item.content_id, status:'SUBMITTED', reason:reason.value.trim(), annotation,
    })
    ElMessage.success('人工标注已提交，等待管理员审核')
    editorOpen.value = false
    await load()
  } catch {
    ElMessage.error('提交失败：请检查分类和证据，或查看后端返回的校验错误')
  }
}
async function approve(item: ManualQueueItem) {
  try {
    await ElMessageBox.confirm('确认已核对原文与人工标注？审核后将进入正式统计。', '审核确认')
    await setManualDisposition({
      content_id:item.content_id, status:'APPROVED',
      reason:'管理员审核通过', annotation:item.annotation,
    })
    ElMessage.success('审核通过')
    await load()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error('审核失败，请检查管理员权限及标注内容')
  }
}
onMounted(load)
</script>

<template>
  <section class="manual-page">
    <header>
      <h1>AI 失败人工处理</h1>
      <p>在这里处理 AI 多次分析失败的帖子。只需选择分类、填写摘要、复制原文证据，无需编写 JSON。</p>
    </header>
    <el-card>
      <div class="toolbar">
        <el-select v-model="filter" style="width:180px" @change="load">
          <el-option label="待标注" value="IN_REVIEW" />
          <el-option label="待审核" value="SUBMITTED" />
          <el-option label="全部" value="" />
          <el-option label="已审核" value="APPROVED" />
          <el-option label="已暂缓" value="DEFERRED" />
          <el-option label="已排除" value="EXCLUDED" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" empty-text="暂无人工处理记录">
        <el-table-column prop="content_id" label="帖子 ID" width="110" />
        <el-table-column prop="product" label="机型" width="140" />
        <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
        <el-table-column label="原帖" width="110"><template #default="{row}"><el-link v-if="validSourceUrl(row.source_url)" :href="validSourceUrl(row.source_url)" target="_blank" rel="noopener noreferrer" type="primary">查看原帖</el-link><span v-else>暂无链接</span></template></el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{row}">{{ labels[row.status] || row.status }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="处理原因" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="190">
          <template #default="{row}">
            <el-button v-if="row.status === 'IN_REVIEW' || row.status === 'SUBMITTED'" link type="primary" @click="openEditor(row)">
              {{ row.status === 'SUBMITTED' ? '查看或修改' : '开始处理' }}
            </el-button>
            <el-button v-if="row.status === 'SUBMITTED'" link type="success" @click="approve(row)">审核通过</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-dialog v-model="editorOpen" title="人工结构化分析" width="min(980px, 96%)" destroy-on-close>
      <template v-if="selected">
        <h3>一、查看帖子原文</h3>
        <p>帖子 #{{ selected.content_id }} · {{ selected.product }} · {{ selected.title }}</p>
        <p><el-link v-if="validSourceUrl(selected.source_url)" :href="validSourceUrl(selected.source_url)" target="_blank" rel="noopener noreferrer" type="primary">在新窗口打开原始帖子</el-link><span v-else>暂无原帖链接，请以平台已采集的原文为准</span></p>
        <el-input :model-value="selected.content" type="textarea" :rows="5" readonly />
        <h3>二、填写整体判断</h3>
        <el-form label-position="top">
          <el-row :gutter="12">
            <el-col :span="8"><el-form-item label="整体情绪"><el-select v-model="overallSentiment"><el-option v-for="v in sentiments" :key="v.value" :label="v.label" :value="v.value" /></el-select></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="内容类型"><el-select v-model="contentType"><el-option v-for="v in contentTypes" :key="v.value" :label="v.label" :value="v.value" /></el-select></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="与手机产品相关程度"><el-select v-model="relevance"><el-option v-for="v in relevanceOptions" :key="v.value" :label="v.label" :value="v.value" /></el-select></el-form-item></el-col>
          </el-row>
          <el-form-item label="内容摘要（用一句话描述用户反馈）"><el-input v-model="summary" type="textarea" :rows="2" maxlength="500" show-word-limit placeholder="例如：用户反馈使用相机时手机明显发热" /></el-form-item>
        </el-form>
        <h3>三、标注具体问题</h3>
        <p class="hint">每个独立问题填写一条。没有具体问题时，可以删除全部问题条目。</p>
        <el-card v-for="(aspect, index) in aspects" :key="index" class="aspect-card">
          <div class="aspect-head"><strong>问题 {{ index + 1 }}</strong><el-button type="danger" link @click="aspects.splice(index,1)">删除此问题</el-button></div>
          <el-row :gutter="12">
            <el-col :span="12"><el-form-item label="问题大类"><el-select :model-value="aspect.aspect_code" placeholder="请选择大类" @update:model-value="setDomain(aspect, $event)"><el-option v-for="v in domains" :key="v.tag_id" :label="v.name" :value="v.tag_id" /></el-select></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="具体问题"><el-select v-model="aspect.topic_code" placeholder="先选大类"><el-option v-for="v in topics(aspect.aspect_code)" :key="v.tag_id" :label="v.name" :value="v.tag_id" /></el-select></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="问题情绪"><el-select v-model="aspect.sentiment"><el-option v-for="v in sentiments" :key="v.value" :label="v.label" :value="v.value" /></el-select></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="用户意图"><el-select v-model="aspect.intent"><el-option v-for="v in intents" :key="v.value" :label="v.label" :value="v.value" /></el-select></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="严重程度"><el-select v-model="aspect.severity"><el-option v-for="v in severities" :key="v.value" :label="v.label" :value="v.value" /></el-select></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="问题性质"><el-select v-model="aspect.issue_type"><el-option v-for="v in issueTypes" :key="v.value" :label="v.label" :value="v.value" /></el-select></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="问题现象（选填）"><el-input v-model="aspect.phenomenon" placeholder="例如：玩游戏时掉帧" /></el-form-item></el-col>
          </el-row>
          <el-form-item label="原文证据（必填：从上方帖子复制一段原话）">
            <el-input v-model="aspect.evidence_text" type="textarea" :rows="2" placeholder="例如：拍照十分钟后手机背面特别烫" />
            <span v-if="aspect.evidence_text && !selected.content.includes(aspect.evidence_text)" class="error">证据未在原文中找到，请复制原文，不要改写</span>
          </el-form-item>
        </el-card>
        <el-button type="primary" plain @click="aspects.push(newAspect())">+ 添加另一个问题</el-button>
        <h3>四、提交说明</h3>
        <el-input v-model="reason" placeholder="例如：AI 反复输出无效分类，已根据原文人工确认" />
      </template>
      <template #footer>
        <el-button @click="editorOpen=false">取消</el-button>
        <el-button type="primary" @click="submit">提交审核</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.manual-page {display:grid;gap:18px}
.manual-page h1 {margin:0}
.manual-page p,.hint {color:var(--el-text-color-secondary)}
.toolbar {display:flex;gap:12px;margin-bottom:16px}
.aspect-card {margin:12px 0}
.aspect-head {display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.error {color:var(--el-color-danger);font-size:12px}
</style>

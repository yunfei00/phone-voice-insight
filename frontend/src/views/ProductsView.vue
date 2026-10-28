<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { createBrand, createProduct, createSourceTarget, updateSourceTarget, getCollectionTargets, startSmartCollection, getBrands, getProducts, getSources, updateProduct } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Product, DataSource, CollectionTargetState } from '@/types/api'

const auth = useAuthStore()
const products = ref<Product[]>([])
const brands = ref<{id:number; name:string; code:string}[]>([])
const sources = ref<DataSource[]>([])
const states = ref<CollectionTargetState[]>([])
const startingId = ref<number|null>(null)
const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const brandDialog = ref(false)
const targetDialog = ref(false)
const targetId = ref<number|null>(null)
const editingId = ref<number|null>(null)
const form = reactive({ brand_id: undefined as number|undefined, name:'', is_active:true })
const brandForm = reactive({ name:'', code:'' })
const targetForm = reactive({ product:undefined as number|undefined, source:undefined as number|undefined, name:'', target_url:'', external_id:'' })
async function load() {
  loading.value = true
  try {
    const [p,b,s,t] = await Promise.all([getProducts({page_size:100}),getBrands(),getSources({page_size:100}),getCollectionTargets({page_size:100})])
    products.value=p.results; brands.value=b.results; sources.value=s.results; states.value=t.results
  } catch { ElMessage.error('手机或采集来源加载失败') }
  finally { loading.value=false }
}
function openNew() { editingId.value=null; Object.assign(form,{brand_id:brands.value[0]?.id,name:'',is_active:true}); dialog.value=true }
function openEdit(p:Product) { editingId.value=p.id; Object.assign(form,{brand_id:p.brand.id,name:p.name,is_active:p.is_active}); dialog.value=true }
async function save() {
  if (!form.brand_id || !form.name.trim()) { ElMessage.warning('品牌和手机名称必填'); return }
  saving.value=true
  try {
    if(editingId.value) await updateProduct(editingId.value,{name:form.name,is_active:form.is_active})
    else await createProduct({brand_id:form.brand_id,name:form.name})
    ElMessage.success('手机保存成功'); dialog.value=false; await load()
  } catch { ElMessage.error('保存失败，请检查手机名称是否重复') }
  finally { saving.value=false }
}
async function saveBrand() {
  if(!brandForm.name.trim()||!brandForm.code.trim()) return
  saving.value=true
  try { await createBrand({...brandForm}); brandDialog.value=false; ElMessage.success('品牌创建成功'); await load() }
  catch { ElMessage.error('品牌创建失败，编码可能重复') }
  finally { saving.value=false }
}
function openTarget(p:Product) {
  const source = sources.value.find(s=>s.code==='HONOR_CLUB') ?? sources.value[0]
  const existing = source?.targets?.find(t=>t.product===p.id)
  targetId.value = existing?.id ?? null
  Object.assign(targetForm,{
    product:p.id,
    source:source?.id,
    name:existing?.name ?? p.name+' 荣耀俱乐部',
    target_url:existing?.target_url ?? '',
    external_id:existing?.external_id ?? '',
  })
  targetDialog.value=true
}
async function saveTarget() {
  if(!targetForm.product||!targetForm.source||!targetForm.target_url.trim()) { ElMessage.warning('请填写来源及入口网址'); return }
  saving.value=true
  try {
    if(targetId.value) await updateSourceTarget(targetId.value,{target_url:targetForm.target_url,external_id:targetForm.external_id})
    else await createSourceTarget({source:targetForm.source,product:targetForm.product,name:targetForm.name,target_type:'COMMUNITY',target_url:targetForm.target_url,external_id:targetForm.external_id,is_active:true})
    targetDialog.value=false; ElMessage.success('采集入口已保存，可前往采集控制启动'); await load()
  } catch { ElMessage.error('采集入口保存失败，请检查网址或是否存在重复配置') }
  finally { saving.value=false }
}
async function smartStart(p:Product) {
  const target = sources.value.flatMap(s=>s.targets).find(t=>t.product===p.id && t.is_active)
  if(!target) { ElMessage.warning('请先配置采集入口'); return }
  const state = states.value.find(s=>s.source_target===target.id)
  if(!state) { ElMessage.warning('采集状态尚未初始化，请刷新页面'); return }
  startingId.value=p.id
  try {
    const result=await startSmartCollection(state.id)
    ElMessage.success(result.existing ? `已有采集任务 #${result.task_id}，请查看进度` : `已启动${result.task_type==='FULL'?'全量':'增量'}采集任务 #${result.task_id}`)
    await load()
  } catch { ElMessage.error('启动失败，请检查采集入口及后台任务服务') }
  finally { startingId.value=null }
}
onMounted(load)
</script>
<template>
  <div>
    <div class="page-header">
      <div><h1 class="page-title">手机产品</h1><p class="page-description">先添加手机，再配置荣耀俱乐部采集入口，最后前往采集控制启动任务。</p></div>
      <div><el-button @click="load">刷新</el-button><el-button v-if="auth.canWrite" @click="brandDialog=true">新增品牌</el-button><el-button v-if="auth.canWrite" type="primary" @click="openNew">新增手机</el-button></div>
    </div>
    <el-alert title="配置流程：新增手机 → 配置采集入口 → 采集控制 → 原始数据。已有数据不会因新增手机而被删除。" type="info" :closable="false" style="margin-bottom:16px"/>
    <div class="panel"><el-table v-loading="loading" :data="products" empty-text="暂无手机产品">
      <el-table-column prop="name" label="手机" min-width="170"/><el-table-column prop="brand.name" label="品牌" width="130"/>
      <el-table-column label="状态" width="90"><template #default="{row}"><el-tag :type="row.is_active?'success':'info'">{{row.is_active?'启用':'停用'}}</el-tag></template></el-table-column>
      <el-table-column label="操作" min-width="210"><template #default="{row}"><el-button v-if="auth.canWrite" link type="primary" @click="openEdit(row)">编辑</el-button><el-button v-if="auth.canWrite" link type="primary" @click="openTarget(row)">配置采集入口</el-button><el-button v-if="auth.canWrite" link type="success" :loading="startingId===row.id" @click="smartStart(row)">智能采集</el-button></template></el-table-column>
    </el-table></div>
    <el-dialog v-model="dialog" :title="editingId?'编辑手机':'新增手机'" width="min(520px,94vw)"><el-form label-position="top">
      <el-form-item label="品牌"><el-select v-model="form.brand_id" :disabled="Boolean(editingId)" placeholder="选择品牌"><el-option v-for="b in brands" :key="b.id" :label="b.name" :value="b.id"/></el-select></el-form-item>
      <el-form-item label="手机名称"><el-input v-model="form.name" placeholder="如 荣耀 Magic8"/></el-form-item>
      <el-form-item v-if="editingId" label="启用"><el-switch v-model="form.is_active"/></el-form-item>
    </el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template></el-dialog>
    <el-dialog v-model="brandDialog" title="新增品牌" width="min(440px,94vw)"><el-form label-position="top"><el-form-item label="品牌名称"><el-input v-model="brandForm.name"/></el-form-item><el-form-item label="唯一编码"><el-input v-model="brandForm.code" placeholder="如 HONOR"/></el-form-item></el-form><template #footer><el-button @click="brandDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveBrand">保存</el-button></template></el-dialog>
    <el-dialog v-model="targetDialog"  :title="targetId ? '编辑采集入口' : '新增采集入口'" width="min(520px,94vw)"><el-form label-position="top">
      <el-form-item label="数据来源"><el-select v-model="targetForm.source" :disabled="Boolean(targetId)"><el-option v-for="s in sources" :key="s.id" :label="s.name" :value="s.id"/></el-select></el-form-item>

      <el-form-item label="采集网址"><el-input v-model="targetForm.target_url" placeholder="荣耀俱乐部话题或入口地址"/></el-form-item>

      <el-alert title="采集入口需要与来源采集器的配置一致。新入口创建后自动初始化采集状态。" type="warning" :closable="false"/>
    </el-form><template #footer><el-button @click="targetDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveTarget">保存入口</el-button></template></el-dialog>
  </div>
</template>

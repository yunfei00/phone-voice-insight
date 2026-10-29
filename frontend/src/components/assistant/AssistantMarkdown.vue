<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

type Block = { type: 'heading' | 'list' | 'code' | 'paragraph'; text: string }

const blocks = computed<Block[]>(() => {
  const result: Block[] = []
  let codeMode = false
  let code = ''
  for (const raw of props.content.split('\n')) {
    if (raw.trim().startsWith('```')) {
      if (codeMode) result.push({ type: 'code', text: code.trimEnd() })
      codeMode = !codeMode
      code = ''
      continue
    }
    if (codeMode) {
      code += `${raw}\n`
      continue
    }
    if (raw.startsWith('### ')) result.push({ type: 'heading', text: raw.slice(4) })
    else if (raw.startsWith('- ')) result.push({ type: 'list', text: raw.slice(2) })
    else if (raw.trim()) result.push({ type: 'paragraph', text: raw })
  }
  if (code) result.push({ type: 'code', text: code.trimEnd() })
  return result
})
</script>

<template>
  <div class="assistant-markdown">
    <template v-for="(block, index) in blocks" :key="index">
      <h4 v-if="block.type === 'heading'">{{ block.text }}</h4>
      <div v-else-if="block.type === 'list'" class="list-item"><span />{{ block.text }}</div>
      <pre v-else-if="block.type === 'code'"><code>{{ block.text }}</code></pre>
      <p v-else>{{ block.text }}</p>
    </template>
  </div>
</template>

<style scoped>
.assistant-markdown {
  line-height: 1.75;
  overflow-wrap: anywhere;
}
.assistant-markdown h4 {
  margin: 14px 0 6px;
  color: var(--pvi-text-primary, #edf5ff);
  font-size: 14px;
}
.assistant-markdown p {
  margin: 4px 0;
}
.list-item {
  display: flex;
  gap: 8px;
  margin: 4px 0;
}
.list-item span {
  width: 5px;
  height: 5px;
  margin-top: 10px;
  border-radius: 50%;
  background: #42d6c6;
  flex: 0 0 auto;
}
pre {
  overflow: auto;
  padding: 12px;
  border: 1px solid #29435c;
  border-radius: 8px;
  background: #071524;
}
</style>

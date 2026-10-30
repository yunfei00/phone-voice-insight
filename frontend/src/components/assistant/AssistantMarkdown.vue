<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

type InlinePart = { text: string; strong?: boolean; emphasis?: boolean; code?: boolean }
type Block = {
  type: 'heading' | 'list' | 'code' | 'paragraph' | 'table' | 'quote'
  text?: string
  level?: number
  ordered?: boolean
  cells?: string[][]
}

function inlineParts(value: string): InlinePart[] {
  const parts: InlinePart[] = []
  const pattern = /(\*\*([^*]+)\*\*|__([^_]+)__|\*([^*\n]+)\*|\x60([^\x60]+)\x60)/g
  let start = 0
  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > start) parts.push({ text: value.slice(start, index) })
    parts.push({
      text: match[2] || match[3] || match[4] || match[5] || '',
      strong: Boolean(match[2] || match[3]),
      emphasis: Boolean(match[4]),
      code: Boolean(match[5]),
    })
    start = index + match[0].length
  }
  if (start < value.length) parts.push({ text: value.slice(start) })
  return parts
}

function splitCells(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
}

function isSeparator(line: string): boolean {
  const cells = splitCells(line)
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell))
}

const blocks = computed<Block[]>(() => {
  const result: Block[] = []
  const lines = props.content.replace(/\r\n?/g, '\n').split('\n')
  let i = 0
  while (i < lines.length) {
    const line = lines[i] || ''
    const trimmed = line.trim()
    if (!trimmed) { i++; continue }
    if (/^\x60{3}/.test(trimmed)) {
      const code: string[] = []
      i++
      while (i < lines.length && !/^\x60{3}/.test((lines[i] || '').trim())) {
        code.push(lines[i] || '')
        i++
      }
      if (i < lines.length) i++
      result.push({ type: 'code', text: code.join('\n') })
      continue
    }
    const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed)
    if (heading) {
      result.push({ type: 'heading', level: heading[1]!.length, text: heading[2] })
      i++; continue
    }
    if (i + 1 < lines.length && trimmed.includes('|') && isSeparator(lines[i + 1] || '')) {
      const cells = [splitCells(trimmed)]
      i += 2
      while (i < lines.length && (lines[i] || '').trim().includes('|')) {
        cells.push(splitCells(lines[i] || ''))
        i++
      }
      result.push({ type: 'table', cells })
      continue
    }
    const list = /^(?:[-*+]\s+|(\d+)\.\s+)(.+)$/.exec(trimmed)
    if (list) {
      result.push({ type: 'list', text: list[2], ordered: Boolean(list[1]) })
      i++; continue
    }
    if (trimmed.startsWith('> ')) {
      result.push({ type: 'quote', text: trimmed.slice(2) })
      i++; continue
    }
    result.push({ type: 'paragraph', text: trimmed })
    i++
  }
  return result
})
</script>

<template>
  <div class="assistant-markdown">
    <template v-for="(block, index) in blocks" :key="index">
      <h3 v-if="block.type === 'heading'" :class="{ 'sub-heading': (block.level || 1) > 2 }">
        <template v-for="(part, n) in inlineParts(block.text || '')" :key="n"><strong v-if="part.strong">{{ part.text }}</strong><em v-else-if="part.emphasis">{{ part.text }}</em><span v-else>{{ part.text }}</span></template>
      </h3>
      <div v-else-if="block.type === 'table'" class="table-wrap">
        <table>
          <thead><tr><th v-for="(cell, n) in block.cells?.[0] || []" :key="n">{{ cell }}</th></tr></thead>
          <tbody><tr v-for="(row, n) in block.cells?.slice(1) || []" :key="n"><td v-for="(cell, m) in row" :key="m"><template v-for="(part, k) in inlineParts(cell)" :key="k"><strong v-if="part.strong">{{ part.text }}</strong><em v-else-if="part.emphasis">{{ part.text }}</em><span v-else>{{ part.text }}</span></template></td></tr></tbody>
        </table>
      </div>
      <div v-else-if="block.type === 'list'" class="list-item"><span class="bullet" /><span><template v-for="(part, n) in inlineParts(block.text || '')" :key="n"><strong v-if="part.strong">{{ part.text }}</strong><em v-else-if="part.emphasis">{{ part.text }}</em><code v-else-if="part.code">{{ part.text }}</code><span v-else>{{ part.text }}</span></template></span></div>
      <pre v-else-if="block.type === 'code'"><code>{{ block.text }}</code></pre>
      <blockquote v-else-if="block.type === 'quote'">{{ block.text }}</blockquote>
      <p v-else><template v-for="(part, n) in inlineParts(block.text || '')" :key="n"><strong v-if="part.strong">{{ part.text }}</strong><em v-else-if="part.emphasis">{{ part.text }}</em><code v-else-if="part.code">{{ part.text }}</code><span v-else>{{ part.text }}</span></template></p>
    </template>
  </div>
</template>

<style scoped>
.assistant-markdown { line-height: 1.75; overflow-wrap: anywhere; min-width: 0; }
.assistant-markdown h3 { margin: 14px 0 6px; color: #edf5ff; font-size: 16px; }
.assistant-markdown h3.sub-heading { font-size: 14px; }
.assistant-markdown p { margin: 5px 0; }
.list-item { display: flex; gap: 9px; margin: 5px 0; }
.bullet { width: 6px; height: 6px; margin-top: 11px; border-radius: 50%; background: #42d6c6; flex: 0 0 auto; }
.table-wrap { max-width: 100%; overflow-x: auto; margin: 12px 0; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border: 1px solid #35506b; padding: 8px 11px; text-align: left; vertical-align: top; }
th { color: #edf5ff; background: #1a3550; }
tr:nth-child(even) td { background: #0d2135; }
pre { max-width: 100%; overflow: auto; padding: 12px; border: 1px solid #29435c; border-radius: 8px; background: #071524; }
p code, .list-item code { padding: 1px 5px; border-radius: 4px; background: #071524; }
blockquote { margin: 10px 0; padding: 5px 12px; border-left: 3px solid #42d6c6; color: #b3c8dc; }
</style>

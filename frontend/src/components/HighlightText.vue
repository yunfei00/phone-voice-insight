<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ text: string; keyword?: string }>()

const segments = computed(() => {
  const keyword = props.keyword?.trim()
  if (!keyword) return [{ text: props.text, highlighted: false }]
  const lowerText = props.text.toLocaleLowerCase()
  const lowerKeyword = keyword.toLocaleLowerCase()
  const result: Array<{ text: string; highlighted: boolean }> = []
  let cursor = 0
  let index = lowerText.indexOf(lowerKeyword)
  while (index >= 0) {
    if (index > cursor) result.push({ text: props.text.slice(cursor, index), highlighted: false })
    result.push({ text: props.text.slice(index, index + keyword.length), highlighted: true })
    cursor = index + keyword.length
    index = lowerText.indexOf(lowerKeyword, cursor)
  }
  if (cursor < props.text.length)
    result.push({ text: props.text.slice(cursor), highlighted: false })
  return result.length ? result : [{ text: props.text, highlighted: false }]
})
</script>

<template>
  <span
    ><template v-for="(segment, index) in segments" :key="index"
      ><mark v-if="segment.highlighted">{{ segment.text }}</mark
      ><template v-else>{{ segment.text }}</template></template
    ></span
  >
</template>

<style scoped>
mark {
  padding: 0 2px;
  color: inherit;
  background: #fff1a8;
  border-radius: 3px;
}
</style>

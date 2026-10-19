<template>
  <div class="message-content">
    <template v-for="(block, index) in blocks" :key="index">
      <component :is="block.tag" v-if="block.type === 'heading'" class="message-heading">
        <template v-for="(part, partIndex) in block.parts" :key="partIndex">
          <strong v-if="part.strong">{{ part.text }}</strong>
          <span v-else>{{ part.text }}</span>
        </template>
      </component>

      <p v-else-if="block.type === 'paragraph'">
        <template v-for="(part, partIndex) in block.parts" :key="partIndex">
          <strong v-if="part.strong">{{ part.text }}</strong>
          <span v-else>{{ part.text }}</span>
        </template>
      </p>

      <ul v-else-if="block.type === 'ul'">
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
          <template v-for="(part, partIndex) in item" :key="partIndex">
            <strong v-if="part.strong">{{ part.text }}</strong>
            <span v-else>{{ part.text }}</span>
          </template>
        </li>
      </ul>

      <ol v-else>
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
          <template v-for="(part, partIndex) in item" :key="partIndex">
            <strong v-if="part.strong">{{ part.text }}</strong>
            <span v-else>{{ part.text }}</span>
          </template>
        </li>
      </ol>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type InlinePart = {
  text: string
  strong: boolean
}

type MessageBlock =
  | { type: 'heading'; tag: 'h3' | 'h4'; parts: InlinePart[] }
  | { type: 'paragraph'; parts: InlinePart[] }
  | { type: 'ul' | 'ol'; items: InlinePart[][] }

const props = defineProps<{
  content: string
}>()

const blocks = computed(() => parseMessage(props.content))

function parseMessage(content: string): MessageBlock[] {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const parsed: MessageBlock[] = []
  let paragraph: string[] = []
  let listType: 'ul' | 'ol' | null = null
  let listItems: InlinePart[][] = []

  const flushParagraph = () => {
    const text = paragraph.join(' ').trim()
    if (text) parsed.push({ type: 'paragraph', parts: parseInline(text) })
    paragraph = []
  }

  const flushList = () => {
    if (listType && listItems.length) parsed.push({ type: listType, items: listItems })
    listType = null
    listItems = []
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      flushParagraph()
      flushList()
      continue
    }

    const headingMatch = line.match(/^(#{2,4})\s+(.+)$/)
    if (headingMatch) {
      flushParagraph()
      flushList()
      parsed.push({
        type: 'heading',
        tag: headingMatch[1].length <= 3 ? 'h3' : 'h4',
        parts: parseInline(headingMatch[2])
      })
      continue
    }

    const colonHeading = line.match(/^(.{2,18})[:：]$/)
    if (colonHeading) {
      flushParagraph()
      flushList()
      parsed.push({ type: 'heading', tag: 'h4', parts: parseInline(colonHeading[1]) })
      continue
    }

    const unorderedMatch = line.match(/^[-*•]\s+(.+)$/)
    if (unorderedMatch) {
      flushParagraph()
      if (listType !== 'ul') {
        flushList()
        listType = 'ul'
      }
      listItems.push(parseInline(unorderedMatch[1]))
      continue
    }

    const orderedMatch = line.match(/^(?:\d+[.)]|[一二三四五六七八九十]+[、.])\s*(.+)$/)
    if (orderedMatch) {
      flushParagraph()
      if (listType !== 'ol') {
        flushList()
        listType = 'ol'
      }
      listItems.push(parseInline(orderedMatch[1]))
      continue
    }

    flushList()
    paragraph.push(line)
  }

  flushParagraph()
  flushList()
  return parsed.length ? parsed : [{ type: 'paragraph', parts: parseInline(content) }]
}

function parseInline(text: string): InlinePart[] {
  const parts: InlinePart[] = []
  const pattern = /(\*\*([^*]+)\*\*|《([^》]+)》)/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text))) {
    if (match.index > lastIndex) parts.push({ text: text.slice(lastIndex, match.index), strong: false })
    parts.push({ text: match[2] || match[3], strong: true })
    lastIndex = pattern.lastIndex
  }

  if (lastIndex < text.length) parts.push({ text: text.slice(lastIndex), strong: false })
  return parts
}
</script>

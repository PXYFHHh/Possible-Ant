<template>
  <div class="assistant-block">
    <div class="assistant-line" />
    <div class="assistant-body">
      <div class="assistant-header">
        <div class="assistant-avatar">A</div>
        <span class="assistant-name">Assistant</span>
        <span class="assistant-time">{{ formatTime(Date.now()) }}</span>
      </div>

      <div class="assistant-content" v-for="(round, ri) in rounds" :key="ri">
        <ThinkingBlock
          v-if="round.reasoning"
          :content="round.reasoning"
          :typing="round.reasoningTyping"
        />
        <MessageCard
          v-if="round.text"
          :text="round.text"
          role="assistant"
          :class="{ 'is-typing': round.textTyping }"
        />
        <span v-if="round.textTyping" class="inline-cursor">|</span>
        <ToolCallCard
          v-for="(tc, ti) in round.toolCalls"
          :key="ti"
          :name="tc.name"
          :args="tc.args"
          :result="tc.result"
          :done="tc.done"
          @open-chunk="$emit('open-chunk', $event)"
        />
      </div>

      <div v-if="tokenStats" class="token-line">
        输入 {{ tokenStats.input_tokens }} · 输出 {{ tokenStats.output_tokens }} · 合计 {{ tokenStats.input_tokens + tokenStats.output_tokens }} · LLM调用 {{ tokenStats.llm_calls }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { isRagResult, parseRagResult, formatTime } from '@/utils'
import MessageCard from './MessageCard.vue'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCallCard from './ToolCallCard.vue'

const props = defineProps({
  entry: { type: Object, required: true },
  typingRounds: { type: Array, default: () => [] },
})

defineEmits(['open-chunk'])

const rounds = computed(() => {
  const result = []
  let current = { reasoning: '', text: '', toolCalls: [], reasoningTyping: false, textTyping: false }

  for (const seg of props.entry.segments || []) {
    if (seg.type === 'reasoning') {
      if (current.text || current.toolCalls.length) {
        result.push(current)
        current = { reasoning: '', text: '', toolCalls: [], reasoningTyping: false, textTyping: false }
      }
      current.reasoning = (current.reasoning || '') + (seg.content || '')
    } else if (seg.type === 'text') {
      if (current.toolCalls.length) {
        result.push(current)
        current = { reasoning: '', text: '', toolCalls: [], reasoningTyping: false, textTyping: false }
      }
      current.text = (current.text || '') + (seg.content || '')
    } else if (seg.type === 'tool_call') {
      current.toolCalls.push({
        name: seg.name || 'tool',
        args: seg.args || {},
        result: seg.result || '',
        done: !!seg.result,
      })
      result.push(current)
      current = { reasoning: '', text: '', toolCalls: [], reasoningTyping: false, textTyping: false }
    }
  }

  if (current.reasoning || current.text || current.toolCalls.length) {
    result.push(current)
  }

  const typing = props.typingRounds || []
  if (typing.length && result.length) {
    const last = result[result.length - 1]
    const t = typing[typing.length - 1]
    if (t) {
      last.reasoningTyping = t.type === 'reasoning'
      last.textTyping = t.type === 'text'
    }
  }

  return result
})

const tokenStats = computed(() => props.entry.token_stats || null)
</script>

<style scoped>
.assistant-block {
  display: flex;
  gap: 0;
  margin-bottom: 24px;
  animation: fadeInUp 0.4s ease-out both;
  position: relative;
}

.assistant-line {
  width: 2px;
  flex-shrink: 0;
  background: linear-gradient(to bottom, var(--accent), var(--accent-2), transparent);
  border-radius: 1px;
  margin-right: 16px;
}

.assistant-body {
  flex: 1;
  min-width: 0;
}

.assistant-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.assistant-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  display: grid;
  place-items: center;
  font-size: 0.6875rem;
  font-weight: 800;
  color: #fff;
}

.assistant-name {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.assistant-time {
  font-size: 0.6875rem;
  color: var(--text-muted);
  margin-left: auto;
}

.inline-cursor {
  color: var(--accent-light);
  animation: cursor-blink 1s step-end infinite;
  font-weight: 100;
}

.is-typing .msg-content {
  position: relative;
}

.token-line {
  margin-top: 12px;
  font-size: 0.6875rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
  padding: 6px 0;
  border-top: 1px dashed var(--glass-border);
  opacity: 0.6;
}
</style>

<script setup lang="ts">
import { computed, ref } from 'vue'

import { useChatStore } from '@/stores/chat'
import { useConversationStore } from '@/stores/conversation'
import { useTaskStore } from '@/stores/task'

const emit = defineEmits<{
  send: [content: string]
  cancel: []
}>()

const conversationStore = useConversationStore()
const chatStore = useChatStore()
const taskStore = useTaskStore()
const fileInput = ref<HTMLInputElement | null>(null)
const activeConversation = computed(() =>
  conversationStore.items.find(
    (item) => item.conversation_id === conversationStore.activeId,
  ),
)
const canSend = computed(
  () =>
    Boolean(chatStore.draft.trim()) &&
    chatStore.connected &&
    Boolean(conversationStore.activeId) &&
    !chatStore.uploadingAttachment &&
    !taskStore.busy,
)
const composerPlaceholder = computed(() => {
  if (!conversationStore.activeId) return '请先选择会话'
  if (!chatStore.connected) return '正在建立实时连接…'
  if (taskStore.status === 'waiting_input') return '请补充任务所需的信息'
  if (taskStore.busy) return '当前任务执行中，可先取消任务'
  return '输入经营问题，Enter 发送，Shift + Enter 换行'
})

function submit(): void {
  if (canSend.value) emit('send', chatStore.draft)
}

async function selectFiles(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  if (!conversationStore.activeId || !input.files) return
  for (const file of Array.from(input.files)) {
    await chatStore.addComposerAttachment(conversationStore.activeId, file)
  }
  input.value = ''
}

function roleLabel(role: string): string {
  if (role === 'user') return '你'
  if (role === 'tool') return '工具'
  if (role === 'system') return '系统'
  return '分析助手'
}
</script>

<template>
  <main class="chat-panel">
    <header class="chat-heading">
      <div>
        <h1>{{ activeConversation?.title || '经营分析工作台' }}</h1>
        <p>{{ activeConversation ? '会话内容仅当前用户可见' : '从左侧新建或选择一个分析会话' }}</p>
      </div>
      <div class="heading-status">
        <span class="connection-dot" :class="{ connected: chatStore.connected }" />
        <span>{{ chatStore.connected ? '实时连接正常' : chatStore.connecting ? '正在连接' : '连接已断开' }}</span>
        <span v-if="taskStore.status" class="status-pill">{{ taskStore.status }}</span>
      </div>
    </header>

    <section class="message-area" aria-live="polite">
      <div v-if="chatStore.loading" class="empty-state">正在读取会话消息…</div>
      <div v-else-if="!conversationStore.activeId" class="empty-state welcome-state">
        <div class="empty-icon">↗</div>
        <h2>开始一次经营归因分析</h2>
        <p>建立会话后，可以发送经营问题并实时查看任务状态。</p>
      </div>
      <div v-else-if="chatStore.messages.length === 0" class="empty-state">
        <h2>这是一个新会话</h2>
        <p>输入一个经营问题，系统将创建可追踪、可取消的分析任务。</p>
      </div>
      <div v-else class="message-list">
        <article
          v-for="message in chatStore.messages"
          :key="message.message_id"
          class="message"
          :class="[message.role, { pending: message.pending }]"
        >
          <strong>{{ roleLabel(message.role) }}</strong>
          <p>{{ message.content }}</p>
          <ul v-if="message.attachments.length">
            <li v-for="file in message.attachments" :key="file.attachment_id">
              {{ file.file_name }} · {{ file.parse_status }}
            </li>
          </ul>
          <small v-if="message.pending">正在受理…</small>
        </article>
      </div>
    </section>

    <p v-if="chatStore.connectionError" class="composer-error">{{ chatStore.connectionError }}</p>
    <p v-if="taskStore.clarificationQuestion" class="clarification">
      {{ taskStore.clarificationQuestion }}
    </p>
    <footer class="composer">
      <div class="composer-input">
        <ul v-if="chatStore.composerAttachments.length" class="composer-files">
          <li v-for="file in chatStore.composerAttachments" :key="file.attachment_id">
            <span>{{ file.file_name }}</span>
            <button type="button" title="移除附件" @click="chatStore.removeComposerAttachment(file.attachment_id)">×</button>
          </li>
        </ul>
        <textarea
          v-model="chatStore.draft"
          :disabled="!conversationStore.activeId || !chatStore.connected || taskStore.busy"
          :placeholder="composerPlaceholder"
          @keydown.enter.exact.prevent="submit"
        />
        <input
          ref="fileInput"
          class="file-input"
          type="file"
          multiple
          accept=".csv,.json,.jsonl,.parquet,.xlsx,.xls,.txt"
          @change="selectFiles"
        />
        <button
          class="attachment-button"
          type="button"
          :disabled="!conversationStore.activeId || taskStore.busy || taskStore.status === 'waiting_input' || chatStore.uploadingAttachment"
          @click="fileInput?.click()"
        >
          {{ chatStore.uploadingAttachment ? '上传中…' : '添加数据文件' }}
        </button>
      </div>
      <button v-if="taskStore.cancellable" class="cancel-button" type="button" @click="emit('cancel')">
        取消任务
      </button>
      <button type="button" :disabled="!canSend" @click="submit">发送</button>
    </footer>
  </main>
</template>

<style scoped>
.chat-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-width: 0;
  min-height: 0;
  background: #f8fafc;
}

.chat-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 17px 24px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
}

.chat-heading h1 {
  margin: 0;
  font-size: 17px;
}

.chat-heading p {
  margin: 4px 0 0;
  color: #8390a4;
  font-size: 12px;
}

.status-pill {
  padding: 4px 9px;
  color: #4262cc;
  font-size: 11px;
  background: #edf1ff;
  border-radius: 20px;
}

.heading-status {
  display: flex;
  gap: 7px;
  align-items: center;
  color: #7d899b;
  font-size: 11px;
}

.connection-dot {
  width: 7px;
  height: 7px;
  background: #c0c7d2;
  border-radius: 50%;
}

.connection-dot.connected {
  background: #19a974;
}

.message-area {
  padding: 24px;
  overflow: auto;
}

.empty-state {
  display: grid;
  max-width: 460px;
  min-height: 100%;
  margin: auto;
  color: #7a879a;
  text-align: center;
  place-content: center;
}

.empty-state h2 {
  margin: 12px 0 4px;
  color: #26334b;
  font-size: 20px;
}

.empty-state p {
  line-height: 1.7;
}

.empty-icon {
  display: grid;
  width: 52px;
  height: 52px;
  margin: auto;
  color: #fff;
  font-size: 26px;
  background: #4870f5;
  border-radius: 16px;
  place-items: center;
}

.message-list {
  display: grid;
  gap: 18px;
  max-width: 820px;
  margin: 0 auto;
}

.message {
  width: min(80%, 680px);
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e1e7f0;
  border-radius: 14px;
}

.message.user {
  justify-self: end;
  background: #edf2ff;
}

.message.pending {
  opacity: 0.65;
}

.message small {
  color: #8090a8;
}

.message p {
  margin-bottom: 0;
  line-height: 1.7;
  white-space: pre-wrap;
}

.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 10px;
  padding: 14px 20px 18px;
  background: #fff;
  border-top: 1px solid #e2e8f0;
}

.composer-error,
.clarification {
  margin: 0;
  padding: 8px 20px;
  color: #a53b3b;
  font-size: 12px;
  background: #fff4f4;
}

.clarification {
  color: #765b18;
  background: #fff8dc;
}

.cancel-button {
  background: #c24949;
}

.composer textarea {
  width: 100%;
  min-height: 58px;
  padding: 12px;
  resize: none;
  background: #f5f7fa;
  border: 1px solid #dfe5ed;
  border-radius: 10px;
}

.composer-input {
  min-width: 0;
}

.file-input {
  display: none;
}

.attachment-button {
  padding: 5px 0;
  color: #526684;
  font-size: 11px;
  background: transparent;
}

.composer-files {
  display: flex;
  gap: 6px;
  padding: 0;
  margin: 0 0 7px;
  overflow-x: auto;
  list-style: none;
}

.composer-files li {
  display: flex;
  flex: 0 0 auto;
  gap: 5px;
  align-items: center;
  padding: 4px 7px;
  color: #526684;
  font-size: 11px;
  background: #edf2ff;
  border-radius: 6px;
}

.composer-files button {
  padding: 0;
  color: #7d899b;
  background: transparent;
}
</style>

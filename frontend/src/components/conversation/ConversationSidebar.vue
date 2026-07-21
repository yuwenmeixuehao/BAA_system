<script setup lang="ts">
import { useRouter } from 'vue-router'

import { useConversationStore } from '@/stores/conversation'
import type { Conversation } from '@/types/conversation'

const store = useConversationStore()
const router = useRouter()

async function createConversation(): Promise<void> {
  const conversation = await store.create()
  await router.push({ name: 'workbench', params: { conversationId: conversation.conversation_id } })
}

async function openConversation(conversationId: string): Promise<void> {
  await router.push({ name: 'workbench', params: { conversationId } })
}

async function renameConversation(item: Conversation): Promise<void> {
  const title = window.prompt('修改会话名称', item.title)?.trim()
  if (title && title !== item.title) await store.rename(item.conversation_id, title)
}

async function archiveConversation(item: Conversation): Promise<void> {
  await store.archive(item.conversation_id)
}

async function deleteConversation(item: Conversation): Promise<void> {
  if (!window.confirm(`确定删除“${item.title}”吗？`)) return
  await store.remove(item.conversation_id)
  if (store.activeId === null) await router.replace({ name: 'workbench' })
}
</script>

<template>
  <aside class="conversation-sidebar">
    <button class="new-button" type="button" @click="createConversation">＋ 新建分析</button>
    <div class="section-heading">
      <span>会话记录</span>
      <small>{{ store.items.length }}</small>
    </div>
    <div v-if="store.loading" class="sidebar-state">正在加载…</div>
    <div v-else-if="store.items.length === 0" class="sidebar-state">暂无会话，创建一次分析吧。</div>
    <nav v-else class="conversation-list" aria-label="会话记录">
      <button
        v-for="item in store.items"
        :key="item.conversation_id"
        class="conversation-item"
        :class="{ active: store.activeId === item.conversation_id }"
        type="button"
        @click="openConversation(item.conversation_id)"
      >
        <span class="conversation-title">{{ item.title }}</span>
        <small>{{ item.status === 'archived' ? '已归档' : item.status === 'draft' ? '草稿' : '分析中' }}</small>
        <span class="item-actions">
          <span role="button" tabindex="0" title="重命名" @click.stop="renameConversation(item)">编辑</span>
          <span role="button" tabindex="0" title="归档" @click.stop="archiveConversation(item)">归档</span>
          <span role="button" tabindex="0" title="删除" @click.stop="deleteConversation(item)">删除</span>
        </span>
      </button>
    </nav>
  </aside>
</template>

<style scoped>
.conversation-sidebar {
  min-width: 0;
  padding: 16px 12px;
  overflow: auto;
  color: #d6deec;
  background: #202d45;
  border-right: 1px solid #dfe5ee;
}

.new-button {
  width: 100%;
  font-weight: 700;
  background: #4870f5;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  margin: 22px 8px 10px;
  color: #98a8c1;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.sidebar-state {
  padding: 18px 8px;
  color: #94a3b8;
  font-size: 13px;
  line-height: 1.6;
}

.conversation-list {
  display: grid;
  gap: 6px;
}

.conversation-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 5px 8px;
  width: 100%;
  padding: 11px 10px;
  color: #d9e2ef;
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
}

.conversation-item:hover,
.conversation-item.active {
  background: #2b3a56;
  border-color: #40516f;
}

.conversation-title {
  overflow: hidden;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-item small {
  color: #8fa1bc;
}

.item-actions {
  display: flex;
  grid-column: 1 / -1;
  gap: 10px;
  height: 0;
  overflow: hidden;
  color: #aebbd0;
  font-size: 11px;
  opacity: 0;
}

.conversation-item:hover .item-actions,
.conversation-item.active .item-actions {
  height: auto;
  opacity: 1;
}
</style>

import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as conversationApi from '@/api/conversations'
import type { Conversation } from '@/types/conversation'

export const useConversationStore = defineStore('conversation', () => {
  const items = ref<Conversation[]>([])
  const activeId = ref<string | null>(null)
  const loading = ref(false)
  const cursor = ref<string | null>(null)

  async function loadConversations(): Promise<void> {
    loading.value = true
    try {
      const page = await conversationApi.listConversations()
      items.value = page.items
      cursor.value = page.next_cursor
    } finally {
      loading.value = false
    }
  }

  async function create(title?: string): Promise<Conversation> {
    const conversation = await conversationApi.createConversation(title)
    items.value.unshift(conversation)
    return conversation
  }

  async function select(conversationId: string): Promise<void> {
    activeId.value = conversationId
  }

  async function rename(conversationId: string, title: string): Promise<void> {
    replaceItem(await conversationApi.updateConversation(conversationId, { title }))
  }

  async function archive(conversationId: string): Promise<void> {
    replaceItem(
      await conversationApi.updateConversation(conversationId, { status: 'archived' }),
    )
  }

  async function remove(conversationId: string): Promise<void> {
    await conversationApi.deleteConversations([conversationId])
    items.value = items.value.filter((item) => item.conversation_id !== conversationId)
    if (activeId.value === conversationId) {
      activeId.value = null
    }
  }

  function replaceItem(conversation: Conversation): void {
    const index = items.value.findIndex(
      (item) => item.conversation_id === conversation.conversation_id,
    )
    if (index >= 0) items.value[index] = conversation
  }

  return {
    activeId,
    archive,
    create,
    cursor,
    items,
    loadConversations,
    loading,
    remove,
    rename,
    select,
  }
})

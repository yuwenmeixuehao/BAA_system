<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ChatPanel from '@/components/chat/ChatPanel.vue'
import ConversationSidebar from '@/components/conversation/ConversationSidebar.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import StageFiveReportPanel from '@/components/report/StageFiveReportPanel.vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useChatStore } from '@/stores/chat'
import { useConversationStore } from '@/stores/conversation'
import { useTaskStore } from '@/stores/task'

const route = useRoute()
const router = useRouter()
const store = useConversationStore()
const chatStore = useChatStore()
const taskStore = useTaskStore()
const realtime = useWebSocket()
let activationVersion = 0

function routeConversationId(): string | null {
  const value = route.params.conversationId
  return typeof value === 'string' ? value : null
}

async function activateConversation(conversationId: string | null): Promise<void> {
  const version = ++activationVersion
  realtime.disconnect()
  taskStore.reset()
  chatStore.clear()
  if (!conversationId) {
    store.activeId = null
    return
  }
  store.select(conversationId)
  try {
    await chatStore.loadHistory(conversationId)
    if (version === activationVersion) {
      const latestTaskId = [...chatStore.messages]
        .reverse()
        .find((message) => message.task_id)?.task_id
      if (latestTaskId) {
        try {
          await taskStore.load(latestTaskId)
        } catch {
          taskStore.reset()
        }
      }
      await realtime.connect(conversationId)
    }
  } catch {
    if (version === activationVersion) await router.replace({ name: 'workbench' })
  }
}

watch(
  () => route.params.conversationId,
  () => void activateConversation(routeConversationId()),
  { immediate: true },
)

onMounted(async () => {
  await store.loadConversations()
  const conversationId = routeConversationId()
  if (conversationId && !store.items.some((item) => item.conversation_id === conversationId)) {
    await router.replace({ name: 'workbench' })
  }
})

onBeforeUnmount(() => realtime.disconnect())
</script>

<template>
  <div class="workbench-page">
    <AppHeader />
    <div class="workbench-grid">
      <ConversationSidebar />
      <ChatPanel @send="realtime.sendMessage" @cancel="realtime.cancelTask" />
      <StageFiveReportPanel />
    </div>
  </div>
</template>

<style scoped>
.workbench-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  height: 100vh;
  overflow: hidden;
}

.workbench-grid {
  display: grid;
  grid-template-columns: 250px minmax(420px, 1fr) minmax(360px, 440px);
  min-height: 0;
}

@media (max-width: 1000px) {
  .workbench-grid {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .workbench-grid > :last-child {
    display: none;
  }
}

@media (max-width: 680px) {
  .workbench-grid {
    grid-template-columns: 90px minmax(0, 1fr);
  }
}
</style>

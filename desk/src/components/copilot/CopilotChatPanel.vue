<template>
  <aside
    v-if="store.visible"
    class="fixed right-0 top-0 z-20 flex h-screen w-full max-w-[380px] flex-col border-l border-outline-gray-2 bg-surface-base shadow-xl"
    :aria-label="__('TBO Copilot')"
  >
    <header
      class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-2.5"
    >
      <span class="text-lg-medium text-ink-gray-9">{{
        __("TBO Copilot")
      }}</span>
      <Button variant="ghost" :aria-label="__('Close')" @click="store.toggle()">
        <template #icon><LucideX class="size-4" /></template>
      </Button>
    </header>

    <div ref="scroller" class="flex-1 space-y-3 overflow-y-auto px-4 py-3">
      <p v-if="!store.messages.length" class="text-p-sm text-ink-gray-6">
        {{
          __(
            "Ask about a ticket or task, approve a fix waiting for you, ask for a change, or report new work for a customer with a screenshot. Nothing happens until you press Yes."
          )
        }}
      </p>
      <div
        v-for="m in store.messages"
        :key="m.name"
        :class="m.direction === 'In' ? 'flex flex-col items-end' : ''"
      >
        <span
          v-if="m.via === 'Teams'"
          class="mb-0.5 text-xs text-ink-gray-5"
        >
          {{ __("in Teams") }}
        </span>
        <div
          v-if="m.direction === 'In'"
          class="max-w-[85%] whitespace-pre-line rounded-lg bg-surface-gray-3 px-3 py-2 text-base text-ink-gray-9"
        >
          {{ m.text }}
        </div>
        <CopilotCard
          v-else-if="m.card"
          :card="m.card"
          :busy="store.busy"
          @press="(a, values) => store.press(m.name, a.verb, a.data, values)"
        />
        <div v-else class="text-base text-ink-gray-8">{{ m.text }}</div>
      </div>
    </div>

    <footer class="border-t border-outline-gray-2 p-3">
      <div v-if="files.length" class="mb-2 flex flex-wrap gap-1">
        <span
          v-for="f in files"
          :key="f.name"
          class="rounded bg-surface-gray-2 px-2 py-0.5 text-sm text-ink-gray-7"
        >
          {{ f.file_name }}
        </span>
      </div>
      <textarea
        v-model="draft"
        rows="2"
        :placeholder="__('Message TBO Copilot')"
        :aria-label="__('Message TBO Copilot')"
        class="w-full resize-none rounded border-outline-gray-2 text-base"
        @keydown.enter.exact.prevent="send"
      />
      <div class="mt-1.5 flex items-center justify-between">
        <FileUploader
          v-if="store.chat"
          :upload-args="{
            doctype: 'HDS Copilot Chat',
            docname: store.chat,
            private: true,
          }"
          @success="(f) => files.push(f)"
        >
          <template #default="{ openFileSelector, uploading }">
            <Button
              variant="ghost"
              size="sm"
              :loading="uploading"
              :aria-label="__('Attach a screenshot or video')"
              @click="openFileSelector()"
            >
              <template #icon><LucidePaperclip class="size-4" /></template>
            </Button>
          </template>
        </FileUploader>
        <Button
          variant="solid"
          size="sm"
          :loading="store.busy"
          :disabled="!draft.trim() && !files.length"
          @click="send"
        >
          {{ __("Send") }}
        </Button>
      </div>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import CopilotCard from "@/components/copilot/CopilotCard.vue";
import { useCopilotChatStore } from "@/stores/copilotChat";
import { __ } from "@/translation";
import { Button, FileUploader } from "frappe-ui";
import { nextTick, ref, watch } from "vue";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucideX from "~icons/lucide/x";

const store = useCopilotChatStore();
const draft = ref("");
const files = ref<{ name: string; file_name: string }[]>([]);
const scroller = ref<HTMLElement | null>(null);

async function send() {
  if (!draft.value.trim() && !files.value.length) return;
  const text = draft.value;
  const names = files.value.map((f) => f.name);
  draft.value = "";
  files.value = [];
  await store.send(text, names);
}

watch(
  () => store.messages.length,
  async () => {
    await nextTick();
    scroller.value?.scrollTo({ top: scroller.value.scrollHeight });
  }
);
</script>

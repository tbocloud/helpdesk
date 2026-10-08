<template>
  <section class="px-4 pb-4 md:px-10" :aria-labelledby="headingId">
    <h2
      :id="headingId"
      class="mb-3 mt-6 text-base-medium text-ink-gray-9"
      :class="!showHeader && 'sr-only'"
    >
      {{ __("Conversation") }}
    </h2>
    <ol v-if="communications.length" class="flex flex-col gap-3">
      <li v-for="c in communications" :id="c.name" :key="c.name">
        <TicketCommunication
          :content="c.content"
          :date="c.creation"
          :user="c.user"
          :from-support="c.sent_or_received === 'Sent'"
          :is-you="c.sender === authStore.userId"
          :attachments="c.attachments"
        />
      </li>
    </ol>
    <p v-else class="py-6 text-p-sm text-ink-gray-6">
      {{ __("No messages yet. Write below and we'll get back to you.") }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { isElementInViewport } from "@/utils";
import { computed, inject, nextTick, useId, watch } from "vue";
import { useRoute } from "vue-router";
import TicketCommunication from "./TicketCommunication.vue";
import { ITicket } from "./symbols";

interface P {
  focus?: string;
  showHeader?: boolean;
}

const props = withDefaults(defineProps<P>(), {
  focus: "",
  showHeader: true,
});
const route = useRoute();
const ticket = inject(ITicket);
const authStore = useAuthStore();
const headingId = `ticket-conversation-${useId()}`;

const communications = computed(() =>
  [...(ticket.data.communications || [])].sort(
    (a, b) => new Date(a.creation).getTime() - new Date(b.creation).getTime()
  )
);

function scroll(id: string) {
  const e = document.getElementById(id);
  if (e && !isElementInViewport(e)) {
    e.scrollIntoView({ block: "nearest" });
  }
}

watch(
  () => props.focus,
  (id: string) => scroll(id)
);
nextTick(() => {
  const hash = route.hash.slice(1);
  const id = hash || communications.value.slice(-1).pop()?.name;
  if (id) setTimeout(() => scroll(id), 1000);
});
</script>

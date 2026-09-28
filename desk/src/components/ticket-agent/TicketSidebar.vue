<template>
  <Resizer
    class="flex h-full flex-col border-l border-outline-gray-1 bg-surface-base"
    side="right"
  >
    <aside
      class="flex min-h-0 flex-1 flex-col"
      :aria-label="__('Ticket details')"
    >
      <TicketDetailsTab />
    </aside>
  </Resizer>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import Resizer from "../Resizer.vue";
import TicketDetailsTab from "./TicketDetailsTab.vue";
</script>

<template>
  <div class="flex h-screen w-full overflow-hidden bg-surface-sidebar">
    <Sidebar />
    <!-- The page sits on a raised panel inset from the shell; it scrolls on its own. -->
    <main
      class="relative my-2.5 me-2.5 flex min-w-0 flex-1 flex-col overflow-auto rounded-2xl border border-outline-gray-2 bg-surface-base shadow-sm"
    >
      <AppHeader />
      <slot />
    </main>
    <Notifications />
    <CommandPalette />
  </div>
</template>
<script setup>
import { Notifications, CommandPalette } from "@/components";
import AppHeader from "./AppHeader.vue";
import Sidebar from "./Sidebar.vue";
</script>

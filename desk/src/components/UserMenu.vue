<template>
  <Dropdown :options="options">
    <template #default="{ open }">
      <button
        type="button"
        class="flex items-center transition-colors duration-200 ease-in-out"
        :class="
          collapsed
            ? 'mx-auto justify-center rounded-[8px]'
            : [
                'w-full gap-2.5 rounded-[12px] border border-outline-gray-2 p-2.5 text-start shadow-sm',
                open
                  ? 'bg-surface-gray-1'
                  : 'bg-surface-base hover:bg-surface-gray-1',
              ]
        "
        :aria-label="
          collapsed ? __('{0} menu', String(config.brandName || '')) : undefined
        "
      >
        <BrandLogo
          class="!rounded-[8px] !font-bold"
          :class="collapsed ? '!size-8' : '!size-9'"
        />
        <div v-if="!collapsed" class="flex min-w-0 flex-1 flex-col gap-1">
          <div
            class="truncate text-base font-semibold leading-tight text-ink-gray-9"
          >
            {{ config.brandName }}
          </div>
          <div class="truncate text-xs leading-tight text-ink-gray-6">
            {{ authStore.userName }}
          </div>
        </div>
        <LucideChevronsUpDown
          v-if="!collapsed"
          class="size-4 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
      </button>
    </template>
  </Dropdown>
</template>

<script setup lang="ts">
import BrandLogo from "@/components/BrandLogo.vue";
import { useAuthStore } from "@/stores/auth";
import { useConfigStore } from "@/stores/config";
import { useSidebarStore } from "@/stores/sidebar";
import { __ } from "@/translation";
import { Dropdown } from "frappe-ui";
import { computed } from "vue";
import LucideChevronsUpDown from "~icons/lucide/chevrons-up-down";

const config = useConfigStore();

const props = defineProps({
  options: {
    type: Array,
    required: true,
  },
  isCollapsed: {
    type: Boolean,
    default: null,
  },
});

const authStore = useAuthStore();
const sidebarStore = useSidebarStore();

const collapsed = computed(() => props.isCollapsed ?? !sidebarStore.isExpanded);
</script>

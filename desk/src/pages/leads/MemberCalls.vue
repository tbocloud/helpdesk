<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <nav
          class="flex min-w-0 items-center gap-1.5 text-lg-medium"
          :aria-label="__('Breadcrumb')"
        >
          <router-link
            :to="{ name: 'Leads' }"
            class="shrink-0 rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >{{ __("Leads") }}</router-link
          >
          <LucideChevronRight
            class="size-4 shrink-0 text-ink-gray-4"
            aria-hidden="true"
          />
          <router-link
            :to="{ name: 'AssignLeads', query: back }"
            class="shrink-0 rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >{{ __("Assign leads") }}</router-link
          >
          <LucideChevronRight
            class="size-4 shrink-0 text-ink-gray-4"
            aria-hidden="true"
          />
          <h1 class="truncate text-ink-gray-9">
            {{ __("{0}'s calls today", name) }}
          </h1>
        </nav>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <p
          class="flex items-center gap-2 text-p-sm text-ink-gray-7"
          role="note"
        >
          <LucideEye
            class="size-4 shrink-0 text-ink-gray-6"
            aria-hidden="true"
          />
          {{
            __(
              "View only. This is what {0} sees in Today's calls; it updates by itself.",
              name
            )
          }}
        </p>
        <!-- a new person: a new queue, never the last one's -->
        <TodaysCalls :key="user" :member="user" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { computed } from "vue";
import { useRoute } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideEye from "~icons/lucide/eye";
import TodaysCalls from "./TodaysCalls.vue";

const props = defineProps<{ user: string }>();
const route = useRoute();

// the name comes with the link from Assign leads; a bare link shows the email
const name = computed(() => String(route.query.name || props.user));
// back to the department they were looking at
const back = computed(() =>
  route.query.department ? { department: route.query.department } : {}
);
</script>

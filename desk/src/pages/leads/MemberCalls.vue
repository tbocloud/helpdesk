<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex min-w-0 flex-col gap-3">
          <nav
            class="flex min-w-0 items-center gap-1.5 text-sm font-medium"
            :aria-label="__('Breadcrumb')"
          >
            <router-link
              :to="{ name: 'Leads' }"
              class="shrink-0 rounded text-brand-ink hover:text-brand-ink-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >{{ __("Leads") }}</router-link
            >
            <LucideChevronRight
              class="size-3.5 shrink-0 text-ink-gray-4"
              aria-hidden="true"
            />
            <router-link
              :to="{ name: 'AssignLeads', query: back }"
              class="shrink-0 rounded text-brand-ink hover:text-brand-ink-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >{{ __("Assign leads") }}</router-link
            >
            <LucideChevronRight
              class="size-3.5 shrink-0 text-ink-gray-4"
              aria-hidden="true"
            />
            <span class="truncate text-ink-gray-6" aria-current="page">{{
              name
            }}</span>
          </nav>

          <div class="flex min-w-0 items-center gap-4">
            <PersonAvatar
              :name="name"
              size="xl"
              class="hidden sm:inline-flex"
            />
            <div class="flex min-w-0 flex-col gap-1.5">
              <h1
                class="truncate text-lg font-bold text-ink-gray-9 md:text-[26px] md:leading-[1.2] md:tracking-[-0.02em]"
              >
                {{ __("{0}'s calls today", name) }}
              </h1>
              <ul class="flex flex-wrap items-center gap-2 text-xs font-medium">
                <li
                  v-for="department in departments"
                  :key="department"
                  class="rounded-full bg-brand-soft px-2.5 py-1 text-brand-ink"
                >
                  {{ department }}
                </li>
                <li
                  class="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-success"
                >
                  <span
                    class="size-1.5 rounded-full bg-success motion-safe:animate-pulse"
                    aria-hidden="true"
                  />
                  {{ __("Live · updates by itself") }}
                </li>
                <li
                  class="inline-flex items-center gap-1.5 px-1 py-1 text-ink-gray-7"
                >
                  <LucideEye class="size-3.5" aria-hidden="true" />
                  {{ __("View only") }}
                </li>
              </ul>
            </div>
          </div>
          <p class="hidden text-sm text-ink-gray-6 md:block">
            {{ __("This is exactly what {0} sees in Today's calls.", name) }}
          </p>
        </div>
      </template>
      <template #right-header>
        <Button
          size="md"
          variant="outline"
          :label="__('Back to Assign leads')"
          :icon-left="LucideChevronLeft"
          @click="router.push({ name: 'AssignLeads', query: back })"
        />
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <!-- a new person: a new queue, never the last one's -->
        <TodaysCalls ref="calls" :key="user" :member="user" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideEye from "~icons/lucide/eye";
import TodaysCalls from "./TodaysCalls.vue";

const props = defineProps<{ user: string }>();
const route = useRoute();
const router = useRouter();
const calls = ref<InstanceType<typeof TodaysCalls> | null>(null);

// the name comes with the link from Assign leads; a bare link shows the email
const name = computed(() => String(route.query.name || props.user));
// back to the department they were looking at
const back = computed(() =>
  route.query.department ? { department: route.query.department } : {}
);
// the departments they call for today, once their calls have loaded
const departments = computed(() => {
  const shown = calls.value?.shown;
  return [
    ...new Set(
      (shown?.slots ?? [])
        .map((slot) => slot.department)
        .concat(shown?.batch?.department ?? [])
        .filter(Boolean)
    ),
  ];
});
</script>

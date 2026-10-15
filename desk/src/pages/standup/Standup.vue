<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">{{ __("Stand-up") }}</h1>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto overflow-x-hidden">
      <div
        class="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 py-5 md:px-6"
      >
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div class="overflow-x-auto">
            <TabButtons
              :model-value="tab"
              size="md"
              :aria-label="__('Stand-up view')"
              :options="tabs"
              @update:model-value="go({ tab: $event, person: undefined })"
            />
          </div>
          <FormControl
            v-if="tab !== 'history'"
            :model-value="date || today"
            type="date"
            class="w-full sm:w-44"
            :label="__('Day')"
            :max="today"
            @update:model-value="
              go({ date: $event && $event !== today ? $event : undefined })
            "
          />
        </div>
        <p class="text-p-sm text-ink-gray-6">{{ dayLabel(date || today) }}</p>

        <MyStandup v-if="tab === 'mine'" :date="date" />
        <TeamStandup
          v-else-if="tab === 'team'"
          :team="team"
          :date="date"
          @team="go({ team: $event })"
        />
        <StandupHistory v-else :person="person" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { dayjs, FormControl, TabButtons } from "frappe-ui";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import MyStandup from "./components/MyStandup.vue";
import StandupHistory from "./components/StandupHistory.vue";
import TeamStandup from "./components/TeamStandup.vue";
import { dayLabel } from "./standupMeta";

type Tab = "mine" | "team" | "history";

const route = useRoute();
const router = useRouter();
const today = dayjs().format("YYYY-MM-DD");

function query(key: string): string | null {
  const value = route.query[key];
  return typeof value === "string" && value ? value : null;
}

// the URL keeps the view, team, day and person, so a Teams link opens the same page
const team = computed(() => query("team"));
const date = computed(() => query("date"));
const person = computed(() => query("person"));
const tab = computed<Tab>(() => {
  const value = query("tab");
  if (value === "mine" || value === "team" || value === "history") return value;
  return team.value ? "team" : "mine";
});

const tabs = [
  { label: __("My stand-up"), value: "mine" },
  { label: __("Team"), value: "team" },
  { label: __("History"), value: "history" },
];

function go(changes: Record<string, string | undefined>) {
  router.replace({ query: { ...route.query, ...changes } });
}
</script>

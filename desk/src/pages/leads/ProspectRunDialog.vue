<template>
  <Dialog
    :open="open"
    :title="run ? runTitle(run) : __('Prospect run')"
    size="3xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <div class="flex flex-col gap-4">
      <TaskyState
        v-if="detail.error && !run"
        error
        :icon="LucideCircleAlert"
        :title="__('Couldn\'t load the run')"
        :message="
          errorText(detail.error, __('Check your connection and try again.'))
        "
      >
        <Button :label="__('Try again')" @click="detail.reload()" />
      </TaskyState>

      <div
        v-else-if="!run"
        class="h-40 animate-pulse rounded-xl bg-surface-gray-2"
        aria-busy="true"
        :aria-label="__('Loading')"
      />

      <template v-else>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
          <TaskyBadge
            :label="STATUS[run.status].label"
            :tone="STATUS[run.status].tone"
            :icon="STATUS[run.status].icon"
          />
          <p class="text-p-sm text-ink-gray-7">
            {{ run.provider }} · {{ run.department }} ·
            {{
              usd(
                run.status === "Done" || run.actual_cost
                  ? run.actual_cost
                  : run.estimated_cost
              )
            }}
          </p>
          <div class="ml-auto flex flex-wrap items-center gap-3">
            <router-link
              v-if="run.count_created"
              :to="{ name: 'Leads', query: { source: sourceName } }"
              class="rounded text-p-sm text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >{{ __("Open source {0} in Leads", sourceName) }}</router-link
            >
            <DraftFirstMessages
              v-if="run.status === 'Done' && run.count_created"
              :run="run.name"
            />
          </div>
        </div>

        <dl class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div v-for="count in counts" :key="count.label" class="flex flex-col">
            <dt class="text-xs text-ink-gray-5">{{ count.label }}</dt>
            <dd class="font-mono text-xl tabular-nums text-ink-gray-9">
              {{ count.value }}
            </dd>
          </div>
        </dl>

        <p
          v-if="run.status === 'Failed'"
          role="alert"
          class="flex items-start gap-2 rounded-lg border border-outline-gray-2 bg-danger-soft px-3 py-2 text-p-sm text-ink-gray-9"
        >
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0 text-danger"
            aria-hidden="true"
          />
          {{ lastLine }}
        </p>

        <section :aria-label="__('Leads from this run')">
          <h3 class="mb-2 text-base-medium text-ink-gray-9">
            {{ __("Leads from this run") }}
          </h3>
          <p
            v-if="!run.leads.length"
            class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-6 text-center text-p-sm text-ink-gray-6"
          >
            {{
              run.status === "Running"
                ? __("Leads appear here as they are found.")
                : __("This run created no leads.")
            }}
          </p>
          <ul
            v-else
            class="divide-y divide-outline-gray-1 overflow-hidden rounded-lg border border-outline-gray-2"
          >
            <li v-for="lead in run.leads" :key="lead.name">
              <router-link
                :to="{ name: 'Lead', params: { leadId: lead.name } }"
                class="flex flex-col gap-0.5 px-3 py-2.5 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
              >
                <span class="flex flex-wrap items-baseline gap-x-3">
                  <span class="text-base text-ink-gray-9">{{
                    lead.company_name || lead.name
                  }}</span>
                  <span
                    v-if="lead.phone"
                    class="font-mono text-sm tabular-nums text-ink-gray-7"
                    >{{ lead.phone }}</span
                  >
                  <span
                    v-if="!lead.owner"
                    class="ml-auto text-xs text-ink-gray-5"
                    >{{ __("In the pool") }}</span
                  >
                </span>
                <span v-if="lead.why_call" class="text-p-sm text-ink-gray-7">{{
                  lead.why_call
                }}</span>
              </router-link>
            </li>
          </ul>
        </section>

        <details v-if="run.log" class="text-p-sm text-ink-gray-7">
          <summary
            class="cursor-pointer rounded text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          >
            {{ __("Log") }}
          </summary>
          <pre class="mt-2 whitespace-pre-wrap font-mono text-xs">{{
            run.log
          }}</pre>
        </details>
      </template>
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useIntervalFn } from "@vueuse/core";
import { Button, createResource, Dialog } from "frappe-ui";
import { computed, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import DraftFirstMessages from "./DraftFirstMessages.vue";
import { runTitle, STATUS, usd, type ProspectRunDetail } from "./prospects";

const props = defineProps<{ open: boolean; name: string }>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
}>();

const detail = createResource({
  url: "helpdesk.api.prospects.get_prospect_run",
  makeParams: () => ({ name: props.name }),
});
const run = computed(() => detail.data as ProspectRunDetail | null);
const running = computed(() => run.value?.status === "Running");

// the counts grow district by district while it runs
const { pause, resume } = useIntervalFn(() => detail.reload(), 5000, {
  immediate: false,
});
watch(running, (busy) => (busy ? resume() : pause()), { immediate: true });
watch(
  () => [props.open, props.name] as const,
  ([open]) => {
    if (open && props.name) detail.reload();
    else pause();
  },
  { immediate: true }
);

const sourceName = computed(() => `Prospecting – ${run.value?.provider}`);
const counts = computed(() => [
  { label: __("Found"), value: String(run.value?.count_found ?? 0) },
  { label: __("Created"), value: String(run.value?.count_created ?? 0) },
  { label: __("Duplicates"), value: String(run.value?.count_duplicates ?? 0) },
  { label: __("Skipped"), value: String(run.value?.count_skipped ?? 0) },
]);
const lastLine = computed(
  () => (run.value?.log || "").trim().split("\n").pop() || ""
);
</script>

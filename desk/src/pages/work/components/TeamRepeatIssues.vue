<template>
  <SectionCard
    :title="__('Repeat issues')"
    :count="data?.summary.issues"
    :description="description"
    class="overflow-hidden"
  >
    <div
      v-if="!data && !issues.error"
      class="flex flex-col gap-2 p-4"
      aria-busy="true"
    >
      <div
        v-for="i in 3"
        :key="i"
        class="h-12 animate-pulse rounded-md bg-surface-gray-2"
      />
    </div>

    <TaskyState
      v-else-if="issues.error && !data"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the repeat issues')"
      :message="
        errorText(issues.error, __('Check your connection and try again.'))
      "
      error
    >
      <Button :label="__('Retry')" @click="issues.reload()" />
    </TaskyState>

    <div
      v-else-if="data"
      class="transition-opacity"
      :class="issues.loading ? 'opacity-60' : ''"
      :aria-busy="issues.loading"
      :inert="issues.loading"
    >
      <p
        class="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-outline-gray-1 px-4 py-2.5 text-p-sm tabular-nums text-ink-gray-7"
      >
        <span>{{ summaryText }}</span>
        <span
          v-if="data.summary.rising"
          class="inline-flex items-center gap-1 text-warning"
        >
          <LucideTrendingUp class="size-3.5" aria-hidden="true" />
          {{ __("{0} rising", String(data.summary.rising)) }}
        </span>
      </p>

      <TaskyState
        v-if="!data.customers.length"
        :icon="LucideRepeat"
        :title="__('No repeat issues')"
        :message="emptyText"
      />

      <ul v-else role="list">
        <li
          v-for="row in data.customers"
          :key="row.customer"
          class="border-b border-outline-gray-1 last:border-b-0"
        >
          <NativeButton
            type="button"
            class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
            :aria-expanded="isOpen(row.customer)"
            :aria-controls="panelId(row.customer)"
            @click="toggle(row.customer)"
          >
            <span class="min-w-0 flex-1">
              <span class="block truncate text-base text-ink-gray-9">
                {{ row.customer }}
              </span>
              <span class="block text-p-sm tabular-nums text-ink-gray-6">
                {{
                  row.issues === 1
                    ? __("1 repeat issue")
                    : __("{0} repeat issues", String(row.issues))
                }}
                ·
                {{ __("{0} this period", String(row.in_period)) }}
                ·
                {{
                  __(
                    "{0} in {1} days",
                    String(row.total),
                    String(data.rules.lookback_days)
                  )
                }}
              </span>
            </span>
            <TaskyBadge
              v-if="row.rising"
              tone="warning"
              :icon="LucideTrendingUp"
              :label="__('Rising')"
            />
            <LucideChevronDown
              class="size-4 shrink-0 text-ink-gray-4 transition-transform motion-reduce:transition-none"
              :class="isOpen(row.customer) ? 'rotate-180' : ''"
              aria-hidden="true"
            />
          </NativeButton>
          <div
            v-if="isOpen(row.customer)"
            :id="panelId(row.customer)"
            class="flex flex-col gap-3 bg-surface-gray-1 px-4 py-3"
          >
            <RepeatIssueCard
              v-for="cluster in row.clusters"
              :key="cluster.id"
              :cluster="cluster"
              :projects="row.projects"
              :access="data.access"
              :lookback-days="data.rules.lookback_days"
              :scope="scope"
              @changed="issues.reload()"
              @dismissed="onDismissed"
            />
          </div>
        </li>
      </ul>
    </div>
  </SectionCard>
</template>

<script setup lang="ts">
import NativeButton from "@/components/NativeButton";
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideRepeat from "~icons/lucide/repeat";
import LucideTrendingUp from "~icons/lucide/trending-up";
import {
  PERIODS,
  type PeriodKey,
  type RepeatIssues,
  type RepeatScope,
} from "../teamDashboardMeta";
import RepeatIssueCard from "./RepeatIssueCard.vue";

const props = defineProps<{
  period: PeriodKey;
  department: string;
  group: string;
  /** A past day whose period the Scoreboard shows; empty for the one in progress. */
  day: string;
}>();

// the same period and department or group as the rest of the Scoreboard
const scope = computed<RepeatScope>(() => ({
  period: props.period,
  department: props.department || null,
  group: props.group || null,
  day: props.day || null,
}));

const issues = createResource({
  url: "helpdesk.api.repeat_issues.get_repeat_issues",
  makeParams: () => scope.value,
  auto: true,
});
const data = computed(() => issues.data as RepeatIssues | undefined);
// "this week", or "in the period" for a period that has closed
const current = computed(() =>
  props.day
    ? __("in the period")
    : PERIODS.find((p) => p.key === props.period)?.current ?? ""
);

const description = __(
  "The same problem coming back from one customer, across tickets and tasks. A customer and process insight: it never changes anyone's score."
);

const summaryText = computed(() => {
  const s = data.value?.summary;
  if (!s) return "";
  const issueText =
    s.issues === 1
      ? __("1 repeat issue")
      : __("{0} repeat issues", String(s.issues));
  const customerText =
    s.customers === 1
      ? __("1 customer")
      : __("{0} customers", String(s.customers));
  const parts = [__("{0} across {1}", issueText, customerText)];
  if (s.tickets_in_period)
    parts.push(
      s.tickets_in_period === 1
        ? __("1 ticket {0}", current.value)
        : __("{0} tickets {1}", String(s.tickets_in_period), current.value)
    );
  if (s.tasks_in_period)
    parts.push(
      s.tasks_in_period === 1
        ? __("1 task {0}", current.value)
        : __("{0} tasks {1}", String(s.tasks_in_period), current.value)
    );
  return parts.join(" · ");
});

const emptyText = computed(() => {
  const r = data.value?.rules;
  if (!r) return "";
  return __(
    "No customer raised the same problem {0} or more times in the last {1} days with one {2}.",
    String(r.min_occurrences),
    String(r.lookback_days),
    current.value
  );
});

const restore = createResource({
  url: "helpdesk.api.repeat_issues.restore_repeat_issue",
  onSuccess: () => issues.reload(),
  onError(error: unknown) {
    toast.error(errorText(error, __("Couldn't bring the issue back.")));
  },
});
function onDismissed(issue: string) {
  toast.success(__("Marked as not a repeat"), {
    action: { label: __("Undo"), onClick: () => restore.submit({ issue }) },
  });
  issues.reload();
}

// the first customer opens on its own: it has the most repeats
const opened = ref<Set<string>>(new Set());
const closedFirst = ref(false);
const first = computed(() => data.value?.customers[0]?.customer);
const isOpen = (customer: string) =>
  opened.value.has(customer) ||
  (customer === first.value && !closedFirst.value);
function toggle(customer: string) {
  const open = isOpen(customer);
  if (customer === first.value) closedFirst.value = open;
  const next = new Set(opened.value);
  if (open) next.delete(customer);
  else next.add(customer);
  opened.value = next;
}
const panelId = (customer: string) =>
  `repeat-${customer.replace(/[^a-zA-Z0-9]+/g, "-")}`;

watch(
  () => [props.period, props.department, props.group, props.day],
  () => {
    opened.value = new Set();
    closedFirst.value = false;
    issues.reload();
  }
);
</script>

<template>
  <article
    class="flex min-w-0 flex-col gap-2.5 rounded-lg border border-outline-gray-2 bg-surface-base p-3"
    :aria-labelledby="headingId"
  >
    <header class="flex flex-wrap items-start justify-between gap-2">
      <div class="min-w-0 flex-1">
        <h3
          :id="headingId"
          class="flex items-center gap-1.5 text-base-medium text-ink-gray-9"
        >
          <span class="min-w-0 break-words">{{ cluster.title }}</span>
          <LucideSparkles
            v-if="cluster.title_source === 'ai'"
            class="size-3.5 shrink-0 text-ink-gray-5"
            :aria-label="__('Title written by AI')"
            role="img"
          />
        </h3>
        <p class="mt-0.5 text-p-sm tabular-nums text-ink-gray-6">
          {{ countsText }}
        </p>
      </div>
      <TaskyBadge
        v-if="cluster.trend === 'rising'"
        tone="warning"
        :icon="LucideTrendingUp"
        :label="__('Rising')"
      />
      <TaskyBadge v-else :icon="LucideMoveRight" :label="__('Steady')" />
    </header>

    <dl class="grid grid-cols-1 gap-x-6 gap-y-1 text-p-sm sm:grid-cols-2">
      <div class="flex gap-1.5">
        <dt class="text-ink-gray-5">{{ __("Seen") }}</dt>
        <dd class="tabular-nums text-ink-gray-8">
          {{ dayText(cluster.first_seen) }} – {{ dayText(cluster.last_seen) }}
        </dd>
      </div>
      <div class="flex gap-1.5">
        <dt class="text-ink-gray-5">{{ __("Raised as") }}</dt>
        <dd class="tabular-nums text-ink-gray-8">{{ kindText }}</dd>
      </div>
      <div v-if="cluster.avg_resolution_hours" class="flex gap-1.5">
        <dt class="text-ink-gray-5">{{ __("Resolved in") }}</dt>
        <dd class="tabular-nums text-ink-gray-8">
          {{ __("{0} on average", hoursText(cluster.avg_resolution_hours)) }}
        </dd>
      </div>
      <div v-if="cluster.people.length" class="flex min-w-0 gap-1.5">
        <dt class="shrink-0 text-ink-gray-5">{{ __("Handled by") }}</dt>
        <dd class="min-w-0 text-ink-gray-8">{{ peopleText }}</dd>
      </div>
    </dl>

    <div
      v-if="cluster.cause || cluster.fix"
      class="flex flex-col gap-1 border-l-2 border-outline-gray-3 pl-3 text-p-sm"
    >
      <p v-if="cluster.cause" class="text-ink-gray-7">
        <span class="text-ink-gray-5">{{ __("Likely cause:") }}</span>
        {{ cluster.cause }}
      </p>
      <p v-if="cluster.fix" class="text-ink-gray-7">
        <span class="text-ink-gray-5">{{ __("Suggested fix:") }}</span>
        {{ cluster.fix }}
      </p>
    </div>

    <p v-if="cluster.root_cause" class="flex gap-1.5 text-p-sm text-ink-gray-7">
      <LucideCircleCheck
        v-if="cluster.root_cause.status === 'Completed'"
        class="mt-0.5 size-4 shrink-0 text-success"
        aria-hidden="true"
      />
      <LucideWrench
        v-else
        class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      <span class="min-w-0">
        {{ __("Root-cause task:") }}
        <RouterLink
          v-if="cluster.root_cause.project"
          :to="{
            name: 'TaskyProject',
            params: { projectId: cluster.root_cause.project },
          }"
          class="rounded text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ cluster.root_cause.subject || cluster.root_cause.task }}
        </RouterLink>
        <span class="text-ink-gray-5">
          · {{ __(cluster.root_cause.status || "Open") }}
        </span>
      </span>
    </p>

    <p v-if="cluster.article" class="flex gap-1.5 text-p-sm text-ink-gray-7">
      <LucideBookOpen
        class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      <span class="min-w-0">
        {{ __("KB article:") }}
        <RouterLink
          :to="{ name: 'Article', params: { articleId: cluster.article.name } }"
          class="rounded text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ cluster.article.title }}
        </RouterLink>
        <span class="text-ink-gray-5">· {{ __(cluster.article.status) }}</span>
      </span>
    </p>

    <!-- the occurrences, newest first -->
    <div>
      <NativeButton
        type="button"
        class="inline-flex items-center gap-1 rounded text-p-sm text-ink-gray-7 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        :aria-expanded="showItems"
        :aria-controls="itemsId"
        @click="showItems = !showItems"
      >
        <LucideChevronRight
          class="size-3.5 transition-transform motion-reduce:transition-none"
          :class="showItems ? 'rotate-90' : ''"
          aria-hidden="true"
        />
        {{
          showItems
            ? __("Hide the {0} occurrences", String(cluster.total))
            : __("Show the {0} occurrences", String(cluster.total))
        }}
      </NativeButton>
      <ul
        v-if="showItems"
        :id="itemsId"
        class="mt-1.5 flex flex-col divide-y divide-outline-gray-1 rounded-md border border-outline-gray-1"
        role="list"
      >
        <li
          v-for="item in cluster.items"
          :key="`${item.doctype}:${item.name}`"
          class="flex min-w-0 items-center gap-2 px-2.5 py-1.5 text-p-sm"
        >
          <component
            :is="item.kind === 'ticket' ? LucideTicket : LucideSquareCheck"
            class="size-3.5 shrink-0 text-ink-gray-5"
            :aria-label="item.kind === 'ticket' ? __('Ticket') : __('Task')"
            role="img"
          />
          <RouterLink
            v-if="itemRoute(item)"
            :to="itemRoute(item)!"
            class="shrink-0 rounded font-mono text-xs text-ink-gray-7 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            {{ item.kind === "ticket" ? `#${item.name}` : item.name }}
          </RouterLink>
          <span
            class="min-w-0 flex-1 truncate text-ink-gray-8"
            :title="item.subject"
          >
            {{ item.subject }}
          </span>
          <span
            class="shrink-0 tabular-nums"
            :class="item.in_period ? 'text-ink-gray-8' : 'text-ink-gray-5'"
          >
            {{ dayText(item.date) }}
            <span v-if="item.in_period" class="sr-only">
              {{ __("this period") }}
            </span>
          </span>
        </li>
      </ul>
    </div>

    <div
      v-if="canRootCause || canDraft"
      class="flex flex-wrap items-center gap-2 pt-0.5"
    >
      <Button
        v-if="canRootCause && projects.length"
        :label="__('Create root-cause task')"
        @click="openRootCause"
      >
        <template #prefix>
          <LucideWrench class="size-3.5" aria-hidden="true" />
        </template>
      </Button>
      <Button
        v-if="canDraft"
        :label="__('Draft KB article')"
        :loading="draft.loading"
        @click="draft.submit(params)"
      >
        <template #prefix>
          <LucideBookOpen class="size-3.5" aria-hidden="true" />
        </template>
      </Button>
      <Button
        v-if="access.can_act && !cluster.root_cause"
        variant="ghost"
        :label="__('Not a repeat')"
        :loading="dismiss.loading"
        @click="dismiss.submit(params)"
      />
    </div>
    <p
      v-if="canRootCause && !projects.length"
      class="text-p-sm text-ink-gray-5"
    >
      {{
        __(
          "{0} has no open project, so a root-cause task can't be added yet.",
          cluster.customer
        )
      }}
    </p>
    <p
      v-if="actionError"
      class="flex items-start gap-1.5 text-p-sm text-danger"
      role="alert"
    >
      <LucideCircleAlert class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      {{ actionError }}
    </p>

    <Dialog
      v-model:open="rootCauseOpen"
      :title="__('Create root-cause task')"
      size="md"
    >
      <form
        :id="formId"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="submitRootCause"
      >
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "A key task in {0}'s project to find and fix why this keeps coming back. It lists the {1} tickets and tasks.",
              cluster.customer,
              String(cluster.total)
            )
          }}
        </p>
        <FormControl
          v-model="project"
          type="select"
          :label="__('Project')"
          :options="projectOptions"
        />
        <div
          v-if="rootCause.error"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span>{{
            errorText(rootCause.error, __("Couldn't create the task."))
          }}</span>
        </div>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            :form="formId"
            :label="__('Create task')"
            :loading="rootCause.loading"
            :disabled="!project || rootCause.loading"
          />
        </div>
      </template>
    </Dialog>
  </article>
</template>

<script setup lang="ts">
import NativeButton from "@/components/NativeButton";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  Dialog,
  dayjs,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref, useId } from "vue";
import { RouterLink } from "vue-router";
import LucideBookOpen from "~icons/lucide/book-open";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideMoveRight from "~icons/lucide/move-right";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideSquareCheck from "~icons/lucide/square-check";
import LucideTicket from "~icons/lucide/ticket";
import LucideTrendingUp from "~icons/lucide/trending-up";
import LucideWrench from "~icons/lucide/wrench";
import {
  hoursText,
  type RepeatCluster,
  type RepeatCustomer,
  type RepeatIssues,
  type RepeatItem,
  type RepeatScope,
} from "../teamDashboardMeta";

const props = defineProps<{
  cluster: RepeatCluster;
  projects: RepeatCustomer["projects"];
  access: RepeatIssues["access"];
  lookbackDays: number;
  /** The Scoreboard's period, day and department or group, as the API takes them. */
  scope: RepeatScope;
}>();
const emit = defineEmits<{ changed: []; dismissed: [issue: string] }>();

const uid = useId();
const headingId = `repeat-title-${uid}`;
const itemsId = `repeat-items-${uid}`;
const formId = `repeat-root-cause-${uid}`;
const showItems = ref(false);

const params = computed(() => ({ ...props.scope, cluster: props.cluster.id }));

const dayText = (day: string) => dayjs(day).format("D MMM");
const countsText = computed(() =>
  __(
    "{0} this period · {1} in the last {2} days",
    String(props.cluster.in_period),
    String(props.cluster.total),
    String(props.lookbackDays)
  )
);
const kindText = computed(() => {
  const { tickets, tasks } = props.cluster;
  const parts = [];
  if (tickets)
    parts.push(
      tickets === 1 ? __("1 ticket") : __("{0} tickets", String(tickets))
    );
  if (tasks)
    parts.push(tasks === 1 ? __("1 task") : __("{0} tasks", String(tasks)));
  return parts.join(", ");
});
const peopleText = computed(() =>
  props.cluster.people.map((p) => `${p.name} (${p.count})`).join(", ")
);

function itemRoute(item: RepeatItem) {
  if (item.kind === "ticket")
    return { name: "TicketAgent", params: { ticketId: item.name } };
  if (item.project)
    return { name: "TaskyProject", params: { projectId: item.project } };
  return null;
}

const canRootCause = computed(
  () => props.access.can_act && !props.cluster.root_cause
);
const canDraft = computed(
  () => props.access.can_draft_kb && !props.cluster.article
);

// --- actions ---

const draft = createResource({
  url: "helpdesk.api.repeat_issues.draft_kb_article",
  onSuccess(article: { title: string; existing: boolean }) {
    toast.success(
      article.existing
        ? __("An article already covers it: {0}", article.title)
        : __(
            "Draft article written: {0}. The managers will review it.",
            article.title
          )
    );
    emit("changed");
  },
  onError() {},
});

// the list (which outlives this card) offers Undo
const dismiss = createResource({
  url: "helpdesk.api.repeat_issues.dismiss_repeat_issue",
  onSuccess: (result: { issue: string }) => emit("dismissed", result.issue),
  onError() {},
});

const actionError = computed(() => {
  if (draft.error)
    return errorText(draft.error, __("Couldn't draft the article."));
  if (dismiss.error)
    return errorText(dismiss.error, __("Couldn't mark it as not a repeat."));
  return "";
});

const rootCauseOpen = ref(false);
const project = ref("");
const projectOptions = computed(() =>
  props.projects.map((p) => ({ label: p.project_name, value: p.name }))
);
const rootCause = createResource({
  url: "helpdesk.api.repeat_issues.create_root_cause_task",
  onSuccess() {
    rootCauseOpen.value = false;
    toast.success(__("Root-cause task created"));
    emit("changed");
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});
function openRootCause() {
  project.value = props.projects[0]?.name ?? "";
  rootCause.reset();
  rootCauseOpen.value = true;
}
function submitRootCause() {
  if (!project.value || rootCause.loading) return;
  rootCause.submit({ ...params.value, project: project.value });
}
</script>

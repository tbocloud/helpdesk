<template>
  <section :aria-labelledby="headingId" class="flex flex-col gap-3">
    <h3 :id="headingId" class="text-base-medium text-ink-gray-8">
      {{ __("Activity") }}
    </h3>

    <form
      v-if="activity.data?.can_comment"
      class="flex flex-col gap-2"
      @submit.prevent="submitComment"
      @keydown.enter="onEnter"
    >
      <FormControl
        v-model="draft"
        type="textarea"
        :rows="2"
        :maxlength="MAX_COMMENT"
        :aria-label="__('Add a comment')"
        :placeholder="__('Add a comment…')"
      />
      <div class="flex justify-end">
        <Button
          type="submit"
          :label="__('Comment')"
          :disabled="!draft.trim()"
          :loading="addComment.loading"
        />
      </div>
    </form>

    <div
      v-if="activity.loading && !activity.data"
      role="status"
      class="flex flex-col gap-3"
      :aria-label="__('Loading')"
    >
      <div
        v-for="i in 3"
        :key="i"
        aria-hidden="true"
        class="h-4 animate-pulse rounded bg-surface-gray-2"
      />
    </div>
    <div
      v-else-if="activity.error"
      class="flex flex-col items-start gap-2"
      role="alert"
    >
      <p class="text-p-sm text-ink-gray-6">
        {{ errorText(activity.error, __("Couldn't load the activity.")) }}
      </p>
      <Button :label="__('Retry')" @click="activity.reload()">
        <template #prefix>
          <LucideRotateCw class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <p v-else-if="!items.length" class="text-p-sm text-ink-gray-5">
      {{ __("No activity yet.") }}
    </p>
    <ol
      v-else
      :aria-label="__('Activity')"
      class="flex flex-col divide-y divide-outline-gray-1"
    >
      <li
        v-for="(item, i) in items"
        :key="`${item.kind}-${item.at}-${i}`"
        class="flex gap-3 py-2.5"
      >
        <component
          :is="iconOf(item)"
          class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
          aria-hidden="true"
        />
        <div class="flex min-w-0 flex-1 flex-col gap-1">
          <div
            class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5"
          >
            <p class="text-p-sm text-ink-gray-8">
              <template v-for="(part, j) in sentenceOf(item)" :key="j">
                <span
                  v-if="part.mono"
                  class="font-mono tabular-nums text-ink-gray-9"
                  >{{ part.text }}</span
                >
                <template v-else>{{ part.text }}</template>
              </template>
            </p>
            <time
              :datetime="isoOf(item.at)"
              :title="exactOf(item.at)"
              class="shrink-0 text-xs tabular-nums text-ink-gray-5"
            >
              {{ relativeOf(item.at) }}
            </time>
          </div>
          <p
            v-if="item.text || item.note"
            class="whitespace-pre-line break-words text-p-sm text-ink-gray-7"
          >
            {{ item.text || item.note }}
          </p>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  FormControl,
  createResource,
  dayjs,
  dayjsLocal,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch, type Component } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideClock from "~icons/lucide/clock";
import LucideInfo from "~icons/lucide/info";
import LucideMessageSquare from "~icons/lucide/message-square";
import LucidePlusCircle from "~icons/lucide/plus-circle";
import LucideRotateCw from "~icons/lucide/rotate-cw";
import LucideTimer from "~icons/lucide/timer";
import LucideUserMinus from "~icons/lucide/user-minus";
import LucideUserPlus from "~icons/lucide/user-plus";
import { TASK_STATUSES, taskStatusMeta } from "../taskMeta";

/** One entry of helpdesk.tasky.api.get_task_activity; extra fields depend on `kind`. */
interface ActivityItem {
  kind:
    | "created"
    | "assigned"
    | "unassigned"
    | "status"
    | "due"
    | "estimate"
    | "note"
    | "comment"
    | "time";
  at: string;
  by: string | null;
  by_name: string | null;
  origin?: {
    type: "ticket" | "content_post" | "recurring" | null;
    name: string | null;
  };
  to?: string | number | null;
  to_name?: string | null;
  from?: string | number | null;
  note?: string | null;
  reason?: string | null;
  text?: string | null;
  name?: string;
  hours?: number;
  date?: string;
}

interface ActivityData {
  items: ActivityItem[];
  can_comment: boolean;
}

interface Part {
  text: string;
  mono?: boolean;
}

const MAX_COMMENT = 5000;

const props = defineProps<{ task: string }>();

const headingId = useId();

const activity = createResource({
  url: "helpdesk.tasky.api.get_task_activity",
  makeParams: () => ({ task: props.task }),
  onError() {},
});

watch(
  () => props.task,
  (task) => task && activity.reload(),
  { immediate: true }
);

const items = computed<ActivityItem[]>(
  () => (activity.data as ActivityData | null)?.items ?? []
);

const draft = ref("");

const addComment = createResource({
  url: "helpdesk.tasky.api.add_task_comment",
  onSuccess(item: ActivityItem) {
    const data = activity.data as ActivityData | null;
    if (data) activity.setData({ ...data, items: [item, ...data.items] });
    draft.value = "";
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't add the comment.")));
  },
});

function submitComment() {
  const content = draft.value.trim();
  if (!content || addComment.loading) return;
  addComment.submit({ task: props.task, content });
}

function onEnter(e: KeyboardEvent) {
  if (!(e.metaKey || e.ctrlKey)) return;
  e.preventDefault();
  submitComment();
}

function iconOf(item: ActivityItem): Component {
  switch (item.kind) {
    case "created":
      return LucidePlusCircle;
    case "assigned":
      return LucideUserPlus;
    case "unassigned":
      return LucideUserMinus;
    case "status": {
      const to = String(item.to ?? "");
      return TASK_STATUSES.includes(to) ? taskStatusMeta(to).icon : LucideInfo;
    }
    case "due":
      return LucideCalendarClock;
    case "estimate":
      return LucideTimer;
    case "comment":
      return LucideMessageSquare;
    case "time":
      return LucideClock;
    default:
      return LucideInfo;
  }
}

// Splits a translated sentence on its {n} placeholders so values can be styled.
function fill(template: string, values: Part[]): Part[] {
  return template
    .split(/(\{\d+\})/)
    .filter(Boolean)
    .map((chunk) => {
      const m = chunk.match(/^\{(\d+)\}$/);
      return m ? values[Number(m[1])] ?? { text: "" } : { text: chunk };
    });
}

function dayOf(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  const d = dayjs(String(value));
  if (!d.isValid()) return String(value);
  return d.format(d.year() === dayjs().year() ? "D MMM" : "D MMM YYYY");
}

function hoursOf(value: unknown): string {
  // a narrow no-break space: the mono font's full space reads as a gap, and "2 h" never wraps
  return __("{0}\u202fh", String(Number(value) || 0));
}

function sentenceOf(item: ActivityItem): Part[] {
  const by = { text: item.by_name || item.by || __("Someone") };
  const to = { text: item.to_name || String(item.to ?? "") };
  switch (item.kind) {
    case "created": {
      const origin = item.origin?.type;
      if (origin === "ticket" && item.origin?.name)
        return fill(__("Created from ticket {0}"), [
          { text: `#${item.origin.name}`, mono: true },
        ]);
      if (origin === "content_post")
        return [{ text: __("Created from a content post") }];
      if (origin === "recurring")
        return [{ text: __("Created by a recurring schedule") }];
      return fill(__("{0} created it"), [by]);
    }
    case "assigned":
      return item.by && item.by === item.to
        ? fill(__("{0} took it"), [by])
        : fill(__("{0} assigned it to {1}"), [by, to]);
    case "unassigned":
      return item.by && item.by === item.to
        ? fill(__("{0} left it"), [by])
        : fill(__("{0} removed {1}"), [by, to]);
    case "status": {
      // Overdue, Template or a translated value has no meta; show it as stored
      const status = String(item.to ?? "");
      const label = TASK_STATUSES.includes(status)
        ? __(taskStatusMeta(status).label)
        : status;
      return fill(__("{0} moved it to {1}"), [by, { text: label }]);
    }
    case "due": {
      const from = { text: dayOf(item.from), mono: true };
      const next = { text: dayOf(item.to), mono: true };
      if (!from.text)
        return fill(__("{0} set the due date to {1}"), [by, next]);
      if (!next.text) return fill(__("{0} cleared the due date"), [by]);
      return fill(__("{0} moved the due date from {1} to {2}"), [
        by,
        from,
        next,
      ]);
    }
    case "estimate": {
      const from = { text: hoursOf(item.from), mono: true };
      const next = { text: hoursOf(item.to), mono: true };
      if (!Number(item.from))
        return fill(__("{0} set the estimate to {1}"), [by, next]);
      if (!Number(item.to)) return fill(__("{0} cleared the estimate"), [by]);
      return fill(__("{0} changed the estimate from {1} to {2}"), [
        by,
        from,
        next,
      ]);
    }
    case "comment":
      return fill(__("{0} commented"), [by]);
    case "time":
      return fill(__("{0} logged {1} on {2}"), [
        by,
        { text: hoursOf(item.hours), mono: true },
        { text: dayOf(item.date), mono: true },
      ]);
    default:
      return [by];
  }
}

// activity times are stored in the site's time zone
function isoOf(at: string) {
  return dayjsLocal(at).toISOString();
}

function exactOf(at: string) {
  return dayjsLocal(at).format("D MMM YYYY, h:mm A");
}

function relativeOf(at: string) {
  return dayjsLocal(at).fromNow();
}
</script>

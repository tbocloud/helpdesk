<template>
  <!-- the title's button stretches over the card, so a click anywhere opens the task;
       the buttons in the footer sit above it -->
  <article
    class="relative flex min-w-0 flex-col gap-2 rounded-xl border border-outline-gray-2 bg-surface-base p-3 shadow-sm transition-colors hover:border-outline-gray-3"
    :aria-labelledby="titleId"
  >
    <div class="flex min-w-0 items-center gap-2">
      <span
        class="inline-flex h-5 shrink-0 items-center rounded-[6px] px-1.5 text-xs font-semibold"
        :class="
          task.role
            ? ROLE_TONES[task.role]
            : 'bg-surface-gray-2 text-ink-gray-7'
        "
        >{{ __(task.role_label) }}</span
      >
      <span
        v-if="dueChip"
        class="ml-auto inline-flex h-5 min-w-0 items-center gap-1 rounded-full px-1.5 text-xs font-medium"
        :class="
          dueChip.late
            ? 'bg-danger-soft text-danger'
            : 'bg-surface-gray-2 text-ink-gray-7'
        "
      >
        <component
          :is="dueChip.late ? LucideCircleAlert : LucideCalendarClock"
          class="size-3 shrink-0"
          aria-hidden="true"
        />
        <span class="truncate first-letter:uppercase">{{ dueChip.text }}</span>
      </span>
    </div>

    <h3 class="min-w-0">
      <button
        :id="titleId"
        type="button"
        class="block max-w-full rounded text-left text-base font-semibold leading-snug text-ink-gray-9 after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-highlight"
        :aria-label="__('Open {0} task: {1}', __(task.role_label), title)"
        @click="emit('open')"
      >
        <span class="line-clamp-2">{{ title }}</span>
      </button>
    </h3>

    <div class="flex min-w-0 flex-col gap-1 text-sm text-ink-gray-6">
      <p class="flex min-w-0 items-center gap-1.5">
        <span class="truncate font-medium text-ink-gray-8">{{
          post?.customer
        }}</span>
        <span
          v-if="platforms.length"
          class="flex shrink-0 items-center gap-1"
          :aria-label="platforms.join(', ')"
          role="img"
        >
          <ChannelIcon
            v-for="p in platforms"
            :key="p"
            :channel="p"
            class="size-3.5"
          />
        </span>
      </p>
      <p
        v-if="task.publish_on"
        class="flex items-center gap-1.5"
        :class="missed && 'font-medium text-danger'"
      >
        <component
          :is="missed ? LucideCircleAlert : LucideClock"
          class="size-3.5 shrink-0"
          aria-hidden="true"
        />
        <time :datetime="task.publish_on" class="tabular-nums">{{
          missed
            ? __("Missed · was due {0}", goLive)
            : __("Goes live {0}", goLive)
        }}</time>
      </p>
    </div>

    <div v-if="task.stage === 'on_hold'" class="flex min-w-0 flex-col gap-1">
      <TaskyBadge
        tone="warning"
        :icon="LucidePause"
        class="max-w-full self-start"
        :label="
          task.hold_reason
            ? `${__('On hold')} · ${__(task.hold_reason)}`
            : __('On hold')
        "
      />
      <HoldNote :note="task.hold_note" :by-name="task.hold_by_name" />
    </div>
    <p
      v-else-if="note"
      class="flex min-w-0 items-start gap-1.5 text-p-sm text-ink-gray-7"
    >
      <component
        :is="note.icon"
        class="mt-0.5 size-3.5 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      <span class="min-w-0">{{ note.text }}</span>
    </p>

    <div
      class="mt-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 border-t border-outline-gray-1 pt-2.5"
    >
      <span class="flex min-w-0 flex-1 basis-32 items-center gap-2">
        <span class="flex shrink-0 -space-x-1.5">
          <Avatar
            v-for="user in task.assignees.slice(0, 3)"
            :key="user"
            shape="circle"
            size="sm"
            class="ring-2 ring-[var(--surface-base)]"
            :image="userStore.getUser(user)?.user_image"
            :label="task.assignee_names[user] || user"
            aria-hidden="true"
          />
        </span>
        <span class="truncate text-sm text-ink-gray-8" :title="people">{{
          task.mine ? __("You") : people || __("Unassigned")
        }}</span>
      </span>
      <TaskyBadge
        v-if="timer"
        :tone="timer.running ? 'info' : 'neutral'"
        :icon="timer.running ? LucideTimer : LucideCirclePause"
        :title="
          timer.running ? __('Tracking time on this task') : __('Timer paused')
        "
      >
        <span class="sr-only">{{
          timer.running ? __("Tracking") : __("Paused")
        }}</span>
        <span class="font-mono tabular-nums">{{
          formatElapsed(timer.elapsed, false)
        }}</span>
      </TaskyBadge>
      <span class="relative z-10 ml-auto flex shrink-0 items-center gap-3">
        <Button
          v-if="timerStep"
          size="md"
          variant="outline"
          class="relative after:absolute after:-inset-1.5"
          :aria-label="`${__(STEPS[timerStep].label)}: ${title}`"
          :title="__(STEPS[timerStep].label)"
          :loading="busy"
          @click="emit('step', timerStep)"
        >
          <template #icon>
            <component
              :is="STEPS[timerStep].icon"
              class="size-4"
              aria-hidden="true"
            />
          </template>
        </Button>
        <Button
          v-if="primary"
          size="md"
          :variant="primary === 'resume' ? 'outline' : 'solid'"
          class="relative after:absolute after:-inset-1.5"
          :label="__(STEPS[primary].label)"
          :aria-label="`${__(STEPS[primary].label)}: ${title}`"
          :loading="busy && !timerStep"
          @click="emit('step', primary)"
        >
          <template #prefix>
            <component
              :is="STEPS[primary].icon"
              class="size-4"
              aria-hidden="true"
            />
          </template>
        </Button>
        <Dropdown :options="menu" align="end">
          <Button
            size="md"
            variant="ghost"
            class="relative after:absolute after:-inset-1.5"
            :aria-label="__('More for {0}', title)"
          >
            <template #icon>
              <LucideEllipsis class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
      </span>
    </div>
  </article>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import HoldNote from "@/pages/tasky/components/HoldNote.vue";
import { formatElapsed, taskTimer } from "@/pages/tasky/taskMeta";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { Avatar, Button, dayjs, Dropdown } from "frappe-ui";
import { type Component, computed, useId } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCirclePause from "~icons/lucide/circle-pause";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideEye from "~icons/lucide/eye";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideLock from "~icons/lucide/lock";
import LucidePanelRight from "~icons/lucide/panel-right";
import LucidePause from "~icons/lucide/pause";
import LucideClock from "~icons/lucide/clock";
import LucideTimer from "~icons/lucide/timer";
import { platformsOf, ROLE_TONES } from "../constants";
import {
  type ContentTask,
  dueText,
  STEPS,
  type TaskPost,
  type TaskStep,
  waitingText,
} from "../contentTasks";
import ChannelIcon from "./ChannelIcon.vue";

const props = defineProps<{
  task: ContentTask;
  post?: TaskPost;
  /** The clock the timers read; the list ticks it. */
  now: ReturnType<typeof dayjs>;
  /** A step on this task is running. */
  busy?: boolean;
}>();

const emit = defineEmits<{
  step: [step: TaskStep];
  /** Open the task in the task dialog. */
  open: [];
  "view-post": [];
}>();

const userStore = useUserStore();
const titleId = useId();

const title = computed(() => props.post?.title || props.task.subject);
const platforms = computed(() => (props.post ? platformsOf(props.post) : []));
const missed = computed(() => !!props.post?.is_missed);
const goLive = computed(() =>
  dayjs(props.task.publish_on).format("ddd D MMM, h:mm A")
);
const people = computed(() =>
  props.task.assignees.map((u) => props.task.assignee_names[u] || u).join(", ")
);
const timer = computed(() => taskTimer(props.task, props.now));

/** When the task is due; red when it's overdue or its post went past its time. */
const dueChip = computed(() => {
  const t = props.task;
  if (t.stage === "done" || !t.due) return null;
  const due = dueText(t.due);
  if (t.is_overdue && !due.late)
    // due today, and already worked past its estimate
    return { text: __("Past its estimate"), late: true };
  return { text: due.text, late: t.is_overdue || due.late || missed.value };
});

/** One line saying what the task waits on, when it waits. */
const note = computed<{ icon: Component; text: string } | null>(() => {
  const t = props.task;
  if (t.stage === "review" && t.review_label)
    return { icon: LucideEye, text: __("Waiting on {0}", t.review_label) };
  if (t.waiting_on)
    return { icon: LucideLock, text: __("Waiting on {0}", t.waiting_on) };
  const waiting = props.post?.progress.waiting_on;
  // the post waits on another part first (e.g. the writer, before design)
  if (
    t.stage === "todo" &&
    waiting?.kind === "part" &&
    waiting.role !== t.role &&
    t.role
  )
    return {
      icon: LucideHourglass,
      text: __("The post is {0}", waitingText(waiting)),
    };
  return null;
});

const has = (step: TaskStep) => props.task.actions.includes(step);

// the timer's own button sits next to Complete while the task is in progress
const timerStep = computed<TaskStep | null>(() =>
  has("pause") ? "pause" : has("resume_timer") ? "resume_timer" : null
);
/** The one filled button: start it, finish it, pick it back up, or sign it off. */
const primary = computed<TaskStep | null>(
  () => (["start", "complete", "resume", "approve"] as const).find(has) ?? null
);

const menu = computed(() => {
  const items = [
    {
      label: __("Open task"),
      icon: LucidePanelRight,
      onClick: () => emit("open"),
    },
    {
      label: __("View post"),
      icon: LucideExternalLink,
      onClick: () => emit("view-post"),
    },
  ];
  // Complete stays reachable when Start is the button
  for (const step of ["complete", "hold", "reassign"] as const) {
    if (!has(step) || primary.value === step) continue;
    items.push({
      label: __(STEPS[step].label),
      icon: STEPS[step].icon,
      onClick: () => emit("step", step),
    });
  }
  return items;
});
</script>

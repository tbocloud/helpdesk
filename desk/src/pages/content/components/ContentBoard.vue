<template>
  <div class="flex flex-col gap-4">
    <section
      class="grid grid-cols-2 gap-3 lg:grid-cols-4"
      :aria-label="__('Summary')"
    >
      <div
        v-for="tile in tiles"
        :key="tile.label"
        class="rounded-lg border border-outline-gray-2 bg-surface-base px-4 py-3"
      >
        <p class="text-xs text-ink-gray-5">{{ tile.label }}</p>
        <p
          class="mt-0.5 truncate text-xl font-semibold tabular-nums text-ink-gray-9"
        >
          {{ tile.value }}
        </p>
        <p class="truncate text-xs text-ink-gray-5">{{ tile.sub }}</p>
      </div>
    </section>

    <div v-if="active.length" class="flex flex-col gap-2">
      <div
        class="flex h-2 overflow-hidden rounded-full bg-surface-gray-2"
        aria-hidden="true"
      >
        <div
          v-for="b in buckets"
          :key="b.key"
          :class="b.swatch"
          :style="{ flex: b.count }"
        />
      </div>
      <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-gray-6">
        <span
          v-for="b in buckets"
          :key="b.key"
          class="flex items-center gap-1.5"
        >
          <span
            class="size-2 rounded-sm"
            :class="b.swatch"
            aria-hidden="true"
          />
          <span class="font-mono tabular-nums">{{ b.count }}</span>
          {{ b.label }}
        </span>
      </div>
    </div>

    <div
      v-if="missed.length"
      class="flex flex-wrap items-center gap-3 rounded-lg bg-danger-soft px-4 py-2.5 text-sm text-danger"
      role="status"
    >
      <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
      <span class="flex-1">
        <b class="font-semibold">{{
          missed.length === 1
            ? __("1 post needs action.")
            : __("{0} posts need action.", String(missed.length))
        }}</b>
        {{ __("Not published on the planned date. Publish or postpone it.") }}
      </span>
      <Button
        v-if="filter !== 'missed'"
        size="sm"
        :label="missed.length === 1 ? __('Show it') : __('Show them')"
        @click="filter = 'missed'"
      />
    </div>

    <div
      class="flex flex-wrap items-center gap-1.5"
      role="group"
      :aria-label="__('Filter entries')"
    >
      <ChipToggle
        v-for="f in filterChips"
        :key="f.key"
        :label="`${f.label} ${f.count}`"
        :pressed="filter === f.key"
        @toggle="filter = f.key"
      />
    </div>

    <div v-if="loading && !posts.length" class="flex flex-col gap-3">
      <div
        v-for="i in 3"
        :key="i"
        class="h-28 animate-pulse rounded-lg bg-surface-gray-2"
      />
    </div>

    <div
      v-else-if="!days.length"
      class="flex flex-col items-center gap-3 rounded-lg border border-dashed border-outline-gray-3 px-4 py-12 text-center"
    >
      <p class="text-p-sm text-ink-gray-5">
        {{
          posts.length
            ? __("No entries match this filter.")
            : day
            ? __("Nothing planned for {0}.", dayjs(day).format("ddd D MMM"))
            : PERIOD_TEXT[period || "month"].empty
        }}
      </p>
      <Button
        :label="day ? __('Add entry for this day') : __('Add entry')"
        @click="emit('add', day || undefined)"
      >
        <template #prefix
          ><LucidePlus class="size-4" aria-hidden="true"
        /></template>
      </Button>
    </div>

    <section
      v-for="day in days"
      :key="day.date"
      class="flex flex-col gap-3 sm:flex-row"
      :aria-label="dayjs(day.date).format('dddd D MMMM')"
    >
      <div
        class="flex shrink-0 items-baseline gap-2 sm:w-20 sm:flex-col sm:items-start sm:gap-0 sm:pt-1"
      >
        <span
          class="text-2xl font-semibold tabular-nums"
          :class="day.date === today ? 'text-brand-ink' : 'text-ink-gray-9'"
          >{{ dayjs(day.date).format("D") }}</span
        >
        <span class="text-xs text-ink-gray-5">{{
          dayjs(day.date).format("ddd")
        }}</span>
        <span class="text-xs text-ink-gray-5">
          {{
            day.total === 1
              ? __("1 entry")
              : __("{0} entries", String(day.total))
          }}
        </span>
      </div>

      <div class="flex min-w-0 flex-1 flex-col gap-3">
        <article
          v-for="post in day.posts"
          :key="post.name"
          class="overflow-hidden rounded-lg border bg-surface-base"
          :class="isMissed(post) ? 'border-danger' : 'border-outline-gray-2'"
          :aria-labelledby="`entry-${post.name}`"
        >
          <header class="flex flex-wrap items-start gap-2 px-4 pt-3">
            <div class="min-w-0 flex-1">
              <button
                :id="`entry-${post.name}`"
                type="button"
                class="truncate text-left text-base font-medium text-ink-gray-9 hover:underline"
                @click="emit('open', post.name)"
              >
                {{ post.title }}
              </button>
              <p class="text-xs text-ink-gray-5">
                {{ platformsOf(post).join(", ") }} · {{ post.format }}
                <template v-if="!filtersCustomer">
                  · {{ post.customer }}</template
                >
              </p>
              <p
                v-if="needsApprovalSoon(post, now)"
                class="mt-1 inline-flex items-center gap-1 rounded bg-warning-soft px-1.5 py-0.5 text-xs text-warning"
              >
                <LucideTriangleAlert class="size-3.5" aria-hidden="true" />
                {{ __("Goes live within 2 days and isn't approved yet") }}
              </p>
            </div>
            <span class="font-mono text-xs tabular-nums text-ink-gray-5">{{
              dayjs(post.publish_on).format("h:mm A")
            }}</span>
            <StatusPill :post="post" />
          </header>

          <div
            v-if="captionOf(post) || post.brief"
            class="grid grid-cols-1 gap-3 px-4 pt-2 md:grid-cols-2"
          >
            <div>
              <p class="text-2xs uppercase tracking-[0.06em] text-ink-gray-5">
                {{ __("Post content") }}
              </p>
              <p
                class="line-clamp-3 whitespace-pre-line text-p-sm"
                :class="captionOf(post) ? 'text-ink-gray-8' : 'text-ink-gray-4'"
              >
                {{ captionOf(post) || __("Not written yet") }}
              </p>
            </div>
            <div>
              <p class="text-2xs uppercase tracking-[0.06em] text-ink-gray-5">
                {{ __("Brief") }}
              </p>
              <p
                class="line-clamp-3 whitespace-pre-line text-p-sm"
                :class="post.brief ? 'text-ink-gray-8' : 'text-ink-gray-4'"
              >
                {{ post.brief || __("No brief yet") }}
              </p>
            </div>
          </div>

          <div class="flex flex-wrap gap-x-6 gap-y-2 px-4 pt-3">
            <div
              v-for="role in TEAM_ROLES"
              :key="role.field"
              class="flex flex-col gap-0.5"
            >
              <span
                class="text-2xs uppercase tracking-[0.06em] text-ink-gray-5"
                >{{ __(role.label) }}</span
              >
              <!-- everyone on the role, each with how far their task is -->
              <button
                v-if="!peopleOf(post, role.field).length"
                type="button"
                class="flex items-center gap-1.5 rounded text-sm text-brand-ink hover:underline"
                @click="emit('action', post, 'assign', role.field)"
              >
                <LucidePlus class="size-3.5" aria-hidden="true" />{{
                  __("Assign")
                }}
              </button>
              <button
                v-else
                type="button"
                class="flex flex-col items-start gap-1 rounded text-left text-sm text-ink-gray-8"
                :title="__('Change who is on this')"
                @click="emit('action', post, 'assign', role.field)"
              >
                <span
                  v-for="person in peopleOf(post, role.field)"
                  :key="person.user"
                  class="flex flex-wrap items-center gap-1.5"
                >
                  <Avatar size="xs" :label="person.full_name" />
                  <span class="max-w-[12rem] truncate hover:underline">{{
                    person.full_name
                  }}</span>
                  <TaskStatusBadge
                    v-if="person.status"
                    :status="person.status"
                    :title="person.task"
                  />
                  <span v-if="isTaskLate(person)" class="text-xs text-danger">{{
                    __("late")
                  }}</span>
                </span>
              </button>
            </div>
          </div>

          <footer
            class="mt-3 flex flex-wrap items-center gap-2 border-t border-outline-gray-2 px-4 py-2.5"
            :class="isMissed(post) ? 'bg-danger-soft' : 'bg-surface-gray-1'"
          >
            <p
              class="flex-1 text-p-sm"
              :class="isMissed(post) ? 'text-danger' : 'text-ink-gray-6'"
            >
              {{ statusLine(post) }}
            </p>
            <template v-if="!CLOSED_STATUSES.includes(post.status)">
              <Button
                size="sm"
                :variant="isMissed(post) ? 'solid' : 'subtle'"
                :label="__('Mark published')"
                @click="emit('action', post, 'publish')"
              >
                <template #prefix
                  ><LucideSend class="size-3.5" aria-hidden="true"
                /></template>
              </Button>
              <Button
                size="sm"
                variant="subtle"
                :label="__('Postpone')"
                @click="emit('action', post, 'postpone')"
              >
                <template #prefix
                  ><LucideCalendarClock class="size-3.5" aria-hidden="true"
                /></template>
              </Button>
              <Button
                size="sm"
                variant="ghost"
                :aria-label="__('Cancel post')"
                :title="__('Cancel post')"
                @click="emit('action', post, 'cancel')"
              >
                <LucideBan class="size-3.5" aria-hidden="true" />
              </Button>
            </template>
            <a
              v-else-if="post.status === 'Published' && post.published_url"
              :href="post.published_url"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 text-sm text-brand-ink hover:underline"
            >
              <LucideExternalLink class="size-3.5" aria-hidden="true" />{{
                __("View post")
              }}
            </a>
          </footer>
        </article>

        <div>
          <Button
            size="sm"
            variant="ghost"
            :label="__('Add entry for this day')"
            @click="emit('add', day.date)"
          >
            <template #prefix
              ><LucidePlus class="size-3.5" aria-hidden="true"
            /></template>
          </Button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import TaskStatusBadge from "@/pages/tasky/components/TaskStatusBadge.vue";
import { Avatar, Button, createResource, dayjs } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideBan from "~icons/lucide/ban";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideExternalLink from "~icons/lucide/external-link";
import LucidePlus from "~icons/lucide/plus";
import LucideSend from "~icons/lucide/send";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import {
  CLOSED_STATUSES,
  type ContentPost,
  type EntryAction,
  htmlToText,
  isMissed,
  needsApprovalSoon,
  platformsOf,
  type RolePerson,
  TEAM_ROLES,
  type TeamRole,
} from "../constants";
import ChipToggle from "./ChipToggle.vue";
import StatusPill from "./StatusPill.vue";

const PERIOD_TEXT = {
  day: {
    progress: __("Day progress"),
    sub: __("this day"),
    empty: __("Nothing planned for this day."),
  },
  week: {
    progress: __("Week progress"),
    sub: __("this week"),
    empty: __("Nothing planned for this week."),
  },
  month: {
    progress: __("Month progress"),
    sub: __("this month"),
    empty: __("Nothing planned for this month yet."),
  },
};

const props = defineProps<{
  posts: ContentPost[];
  month: string;
  period?: "day" | "week" | "month";
  // set in Day view, so an empty day offers to add an entry on it
  day?: string;
  loading?: boolean;
  filtersCustomer?: string;
}>();
const emit = defineEmits<{
  (e: "open", name: string): void;
  (e: "add", date?: string): void;
  (e: "action", post: ContentPost, action: EntryAction, role?: TeamRole): void;
}>();

// everyone on each post's roles, with their task's status; reloaded with the posts
const team = createResource({
  url: "helpdesk.api.content_board.get_team_task_status",
  makeParams: () => ({ posts: props.posts.map((p) => p.name) }),
});
watch(
  () => props.posts,
  () => props.posts.length && team.reload(),
  { immediate: true }
);

/** Everyone on a role, the main person first; just the main person until the team loads. */
function peopleOf(post: ContentPost, role: TeamRole): RolePerson[] {
  const people = team.data?.[post.name]?.[role];
  if (people) return people;
  return post[role] ? [{ user: post[role]!, full_name: post[role]! }] : [];
}

function isTaskLate(person: RolePerson) {
  return (
    !!person.due &&
    // an Overdue status already says so
    !["Completed", "Cancelled", "Overdue"].includes(person.status ?? "") &&
    dayjs(person.due).isBefore(dayjs(), "day")
  );
}

type FilterKey = "all" | "missed" | "upcoming" | "published" | "cancelled";
const filter = ref<FilterKey>("all");
watch(
  () => props.month,
  () => (filter.value = "all")
);

const today = dayjs().format("YYYY-MM-DD");
// re-read the clock whenever posts reload, so a post that just passed its time shows as missed
const now = computed(() => {
  void props.posts;
  return new Date();
});

const active = computed(() =>
  props.posts.filter((p) => p.status !== "Cancelled")
);
const published = computed(() =>
  props.posts.filter((p) => p.status === "Published")
);
const missed = computed(() =>
  props.posts.filter((p) => isMissed(p, now.value))
);
const upcoming = computed(() =>
  props.posts.filter(
    (p) => !CLOSED_STATUSES.includes(p.status) && !isMissed(p, now.value)
  )
);
const cancelled = computed(() =>
  props.posts.filter((p) => p.status === "Cancelled")
);

const MATCHERS: Record<FilterKey, (p: ContentPost) => boolean> = {
  all: () => true,
  missed: (p) => isMissed(p, now.value),
  upcoming: (p) =>
    !CLOSED_STATUSES.includes(p.status) && !isMissed(p, now.value),
  published: (p) => p.status === "Published",
  cancelled: (p) => p.status === "Cancelled",
};

const filterChips = computed(() =>
  (
    [
      { key: "all", label: __("All"), count: props.posts.length },
      { key: "missed", label: __("Missed"), count: missed.value.length },
      { key: "upcoming", label: __("Upcoming"), count: upcoming.value.length },
      {
        key: "published",
        label: __("Published"),
        count: published.value.length,
      },
      {
        key: "cancelled",
        label: __("Cancelled"),
        count: cancelled.value.length,
      },
    ] as { key: FilterKey; label: string; count: number }[]
  ).filter((c) => c.key === "all" || c.key === filter.value || c.count)
);

const buckets = computed(() =>
  [
    {
      key: "published",
      label: __("Published"),
      count: published.value.length,
      swatch: "bg-success",
    },
    {
      key: "missed",
      label: __("Missed"),
      count: missed.value.length,
      swatch: "bg-danger",
    },
    {
      key: "upcoming",
      label: __("Upcoming"),
      count: upcoming.value.length,
      swatch: "bg-info",
    },
  ].filter((b) => b.count)
);

const tiles = computed(() => {
  const onTime = published.value.filter(
    (p) =>
      p.published_on &&
      dayjs(p.published_on).format("YYYY-MM-DD") <=
        dayjs(p.publish_on).format("YYYY-MM-DD")
  ).length;
  const postponed = props.posts.filter(
    (p) => (p.times_postponed || 0) > 0
  ).length;
  const next = upcoming.value
    .filter((p) => dayjs(p.publish_on).isAfter(dayjs()))
    .sort((a, b) => (a.publish_on! < b.publish_on! ? -1 : 1))[0];
  const planned = active.value.length;
  return [
    {
      label: PERIOD_TEXT[props.period || "month"].progress,
      value: planned
        ? `${Math.round((published.value.length / planned) * 100)}%`
        : "—",
      sub: __(
        "{0} of {1} published",
        String(published.value.length),
        String(planned)
      ),
    },
    {
      label: __("On-time rate"),
      value: published.value.length
        ? `${Math.round((onTime / published.value.length) * 100)}%`
        : "—",
      sub: __(
        "{0} of {1} on the planned day",
        String(onTime),
        String(published.value.length)
      ),
    },
    {
      label: __("Postponed"),
      value: String(postponed),
      sub: PERIOD_TEXT[props.period || "month"].sub,
    },
    {
      label: __("Next post"),
      value: next ? dayjs(next.publish_on).format("ddd D MMM, h:mm A") : "—",
      sub: next
        ? `${next.title} · ${platformsOf(next).join(", ")}`
        : __("Nothing scheduled"),
    },
  ];
});

const days = computed(() => {
  const byDay = new Map<
    string,
    { date: string; total: number; posts: ContentPost[] }
  >();
  for (const post of props.posts) {
    if (!post.publish_on) continue;
    const date = dayjs(post.publish_on).format("YYYY-MM-DD");
    if (!byDay.has(date)) byDay.set(date, { date, total: 0, posts: [] });
    const day = byDay.get(date)!;
    day.total++;
    if (MATCHERS[filter.value](post)) day.posts.push(post);
  }
  return [...byDay.values()]
    .filter((d) => d.posts.length)
    .sort((a, b) => (a.date < b.date ? -1 : 1))
    .map((d) => ({
      ...d,
      posts: d.posts.sort((a, b) => (a.publish_on! < b.publish_on! ? -1 : 1)),
    }));
});

function captionOf(post: ContentPost) {
  return htmlToText(post.caption);
}

function statusLine(post: ContentPost) {
  const when = dayjs(post.publish_on).format("ddd D MMM, h:mm A");
  if (post.status === "Published") {
    return post.published_on
      ? __("Published {0}", dayjs(post.published_on).format("D MMM, h:mm A"))
      : __("Published");
  }
  if (post.status === "Cancelled") return __("Cancelled");
  if (isMissed(post, now.value)) return __("Not published. Was due {0}.", when);
  const postponed = post.times_postponed
    ? " · " +
      (post.times_postponed === 1
        ? __("postponed once")
        : __("postponed {0} times", String(post.times_postponed)))
    : "";
  return __("Goes live {0}", when) + postponed;
}
</script>

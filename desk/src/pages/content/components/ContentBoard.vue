<template>
  <div class="flex flex-col gap-4">
    <section
      class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
      :aria-label="__('Summary')"
    >
      <div
        v-for="tile in tiles"
        :key="tile.key"
        class="flex items-start gap-3 rounded-lg border px-4 py-3"
        :class="TILE_TONES[tile.tone].tile"
      >
        <div class="min-w-0 flex-1">
          <p class="text-sm text-ink-gray-7">{{ tile.label }}</p>
          <p
            class="mt-0.5 truncate font-mono text-xl font-semibold tabular-nums text-ink-gray-9"
          >
            {{ tile.value }}
          </p>
          <p class="truncate text-xs text-ink-gray-6" :title="tile.sub">
            {{ tile.sub }}
          </p>
        </div>
        <!-- how much of the period is published, as a ring -->
        <svg
          v-if="tile.ring !== undefined"
          viewBox="0 0 36 36"
          class="size-9 shrink-0 -rotate-90"
          aria-hidden="true"
        >
          <circle
            cx="18"
            cy="18"
            r="15"
            fill="none"
            stroke-width="4"
            style="stroke: var(--outline-gray-2)"
          />
          <circle
            v-if="tile.ring > 0"
            cx="18"
            cy="18"
            r="15"
            fill="none"
            stroke-width="4"
            stroke-linecap="round"
            style="stroke: var(--success)"
            :stroke-dasharray="`${(tile.ring / 100) * RING} ${RING}`"
          />
        </svg>
        <span
          v-else
          class="grid size-8 shrink-0 place-items-center rounded-full bg-surface-base"
          :class="TILE_TONES[tile.tone].icon"
        >
          <component :is="tile.icon" class="size-4" aria-hidden="true" />
        </span>
      </div>
    </section>

    <div v-if="active.length" class="flex flex-col gap-2">
      <div
        class="flex h-2 gap-0.5 overflow-hidden rounded-full bg-surface-gray-2"
        role="img"
        :aria-label="barLabel"
      >
        <div
          v-for="b in buckets"
          :key="b.key"
          :class="b.swatch"
          :style="{ flex: b.count }"
        />
      </div>
      <div
        class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-gray-6"
        aria-hidden="true"
      >
        <span
          v-for="b in buckets"
          :key="b.key"
          class="flex items-center gap-1.5"
        >
          <span class="size-2 rounded-full" :class="b.swatch" />
          <span class="font-mono tabular-nums text-ink-gray-8">{{
            b.count
          }}</span>
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
        class="flex shrink-0 items-baseline gap-2 sm:w-20 sm:flex-col sm:items-start sm:gap-0 sm:pt-2"
      >
        <span
          class="font-mono text-2xl font-semibold tabular-nums"
          :class="day.date === today ? 'text-brand-ink' : 'text-ink-gray-9'"
          >{{ dayjs(day.date).format("D") }}</span
        >
        <span class="text-sm text-ink-gray-7">{{
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
          class="entry overflow-hidden rounded-xl border"
          :class="`entry-${entryTone(post)}`"
          :aria-labelledby="`entry-${post.name}`"
        >
          <header class="flex flex-wrap items-start gap-x-3 gap-y-2 px-4 pt-3">
            <div class="min-w-0 flex-1 basis-60">
              <button
                :id="`entry-${post.name}`"
                type="button"
                class="max-w-full truncate rounded text-left text-base font-semibold text-ink-gray-9 hover:underline"
                @click="emit('open', post.name)"
              >
                {{ post.title }}
              </button>
              <p class="text-sm text-ink-gray-6">
                {{
                  [post.format, filtersCustomer ? "" : post.customer]
                    .filter(Boolean)
                    .join(" · ")
                }}
              </p>
              <p
                v-if="needsApprovalSoon(post, now)"
                class="mt-1.5 inline-flex items-center gap-1.5 rounded-md bg-danger-soft px-2 py-0.5 text-sm text-danger"
              >
                <LucideTriangleAlert
                  class="size-3.5 shrink-0"
                  aria-hidden="true"
                />
                {{ __("Goes live within 2 days and isn't approved yet.") }}
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
              <ul
                class="flex flex-wrap items-center gap-x-3 gap-y-1"
                :aria-label="__('Platforms')"
              >
                <li
                  v-for="p in platformsOf(post)"
                  :key="p"
                  class="inline-flex items-center gap-1.5 text-sm text-ink-gray-8"
                >
                  <ChannelIcon :channel="p" class="size-4 shrink-0" />{{
                    __(p)
                  }}
                </li>
              </ul>
              <span
                class="font-mono text-sm tabular-nums text-ink-gray-8"
                :aria-label="__('Time')"
                >{{ dayjs(post.publish_on).format("h:mm A") }}</span
              >
              <StatusPill :post="post" />
            </div>
          </header>

          <div class="grid grid-cols-1 gap-3 px-4 pt-3 md:grid-cols-2 md:gap-0">
            <div class="md:pr-4">
              <p class="text-2xs uppercase tracking-[0.06em] text-ink-gray-6">
                {{ __("Post content") }}
              </p>
              <p
                class="line-clamp-3 whitespace-pre-line text-p-sm"
                :class="captionOf(post) ? 'text-ink-gray-8' : 'text-ink-gray-5'"
              >
                {{ captionOf(post) || __("Not written yet") }}
              </p>
            </div>
            <div class="entry-rule md:border-l md:pl-4">
              <p class="text-2xs uppercase tracking-[0.06em] text-ink-gray-6">
                {{ __("Brief") }}
              </p>
              <p
                class="line-clamp-3 whitespace-pre-line text-p-sm"
                :class="post.brief ? 'text-ink-gray-8' : 'text-ink-gray-5'"
              >
                {{ post.brief || __("No brief yet") }}
              </p>
            </div>
          </div>

          <div class="flex flex-wrap gap-x-6 gap-y-3 px-4 pt-3">
            <div
              v-for="role in TEAM_ROLES"
              :key="role.field"
              class="flex flex-col items-start gap-1"
            >
              <span
                class="text-2xs uppercase tracking-[0.06em] text-ink-gray-6"
                >{{ __(role.label) }}</span
              >
              <button
                v-if="!peopleOf(post, role.field).length"
                type="button"
                class="inline-flex h-6 items-center gap-1 rounded-full bg-warning-soft px-2.5 text-xs font-medium text-warning hover:underline"
                :aria-label="__('Assign {0}', __(role.label).toLowerCase())"
                @click="emit('action', post, 'assign', role.field)"
              >
                <LucidePlus class="size-3.5" aria-hidden="true" />{{
                  __("Assign")
                }}
              </button>
              <!-- everyone on the role, each with how far their task is -->
              <button
                v-else
                type="button"
                class="flex flex-col items-start gap-1 rounded-lg text-left text-sm text-ink-gray-8"
                :title="__('Change who is on this')"
                @click="emit('action', post, 'assign', role.field)"
              >
                <span
                  v-for="person in peopleOf(post, role.field)"
                  :key="person.user"
                  class="inline-flex flex-wrap items-center gap-1.5 rounded-full border border-outline-gray-2 bg-surface-base py-0.5 pl-0.5 pr-1"
                >
                  <Avatar size="xs" :label="person.full_name" />
                  <span class="max-w-[10rem] truncate hover:underline">{{
                    person.full_name
                  }}</span>
                  <TaskStatusBadge
                    v-if="person.status"
                    :status="person.status"
                    :title="person.task"
                  />
                  <span
                    v-if="isTaskLate(person)"
                    class="pr-1 text-xs text-danger"
                    >{{ __("late") }}</span
                  >
                </span>
              </button>
            </div>
          </div>

          <footer
            class="entry-footer mt-3 flex flex-wrap items-center gap-2 border-t px-4 py-2.5"
          >
            <p
              class="flex-1 basis-48 text-sm"
              :class="isMissed(post, now) ? 'text-danger' : 'text-ink-gray-7'"
            >
              {{ statusLine(post) }}
            </p>
            <template v-if="!CLOSED_STATUSES.includes(post.status)">
              <button
                type="button"
                class="inline-flex h-7 items-center gap-1.5 rounded-md bg-success px-2.5 text-sm font-medium text-ink-base transition-opacity hover:opacity-90"
                @click="emit('action', post, 'publish')"
              >
                <LucideSend class="size-3.5" aria-hidden="true" />
                {{ __("Mark published") }}
              </button>
              <Button
                size="sm"
                variant="outline"
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
                :tooltip="__('Cancel post')"
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
              class="inline-flex items-center gap-1 rounded text-sm text-success hover:underline"
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
import { onTimeTone } from "@/pages/performance/performanceMeta";
import TaskStatusBadge from "@/pages/tasky/components/TaskStatusBadge.vue";
import type { Tone } from "@/pages/tasky/taskMeta";
import { Avatar, Button, createResource, dayjs } from "frappe-ui";
import { type Component, computed, markRaw, ref, watch } from "vue";
import LucideBan from "~icons/lucide/ban";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClock from "~icons/lucide/clock";
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
import ChannelIcon from "./ChannelIcon.vue";
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

// circumference of the progress ring (r = 15)
const RING = 2 * Math.PI * 15;

// Full class strings so Tailwind's scanner keeps them
const TILE_TONES: Record<Tone, { tile: string; icon: string }> = {
  neutral: {
    tile: "border-outline-gray-2 bg-surface-base",
    icon: "text-ink-gray-6 border border-outline-gray-2",
  },
  info: { tile: "border-outline-gray-2 bg-info-soft", icon: "text-info" },
  success: {
    tile: "border-outline-gray-2 bg-success-soft",
    icon: "text-success",
  },
  warning: {
    tile: "border-outline-gray-2 bg-warning-soft",
    icon: "text-warning",
  },
  danger: { tile: "border-outline-gray-2 bg-danger-soft", icon: "text-danger" },
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
// same rule as the delivery report: late when it went out after its planned day
const late = computed(() =>
  published.value.filter(
    (p) =>
      p.published_on &&
      dayjs(p.published_on).format("YYYY-MM-DD") >
        dayjs(p.publish_on).format("YYYY-MM-DD")
  )
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
      key: "on-time",
      label: __("Published on time"),
      count: published.value.length - late.value.length,
      swatch: "bg-success",
    },
    {
      key: "late",
      label: __("Published late"),
      count: late.value.length,
      swatch: "bg-warning",
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
const barLabel = computed(() =>
  buckets.value.map((b) => `${b.count} ${b.label}`).join(", ")
);

interface Tile {
  key: string;
  label: string;
  value: string;
  sub: string;
  tone: Tone;
  icon?: Component;
  ring?: number;
}

const tiles = computed<Tile[]>(() => {
  const publishedCount = published.value.length;
  const onTime = publishedCount - late.value.length;
  const onTimePct = publishedCount
    ? Math.round((onTime / publishedCount) * 100)
    : null;
  const postponedPosts = props.posts.filter(
    (p) => (p.times_postponed || 0) > 0
  );
  const postponements = postponedPosts.reduce(
    (n, p) => n + (p.times_postponed || 0),
    0
  );
  const next = upcoming.value
    .filter((p) => dayjs(p.publish_on).isAfter(dayjs()))
    .sort((a, b) => (a.publish_on! < b.publish_on! ? -1 : 1))[0];
  const planned = active.value.length;
  const progress = planned ? Math.round((publishedCount / planned) * 100) : 0;
  const periodSub = PERIOD_TEXT[props.period || "month"].sub;
  return [
    {
      key: "progress",
      label: PERIOD_TEXT[props.period || "month"].progress,
      value: planned ? `${progress}%` : "—",
      sub: __("{0} of {1} published", String(publishedCount), String(planned)),
      tone: "neutral",
      ring: progress,
    },
    {
      key: "on-time",
      label: __("On-time rate"),
      value: onTimePct == null ? "—" : `${onTimePct}%`,
      sub: __(
        "{0} of {1} on the planned day",
        String(onTime),
        String(publishedCount)
      ),
      tone: onTimeTone(onTimePct),
      icon: markRaw(LucideClock),
    },
    {
      key: "postponed",
      label: __("Postponed"),
      value: String(postponedPosts.length),
      sub:
        postponements > postponedPosts.length
          ? `${periodSub} · ${__("{0} moves", String(postponements))}`
          : periodSub,
      tone: postponedPosts.length ? "warning" : "neutral",
      icon: markRaw(LucideCalendarClock),
    },
    {
      key: "next",
      label: __("Next post"),
      value: next ? dayjs(next.publish_on).format("ddd D MMM, h:mm A") : "—",
      sub: next
        ? `${next.title} · ${platformsOf(next).join(", ")}`
        : __("Nothing scheduled"),
      tone: next ? "info" : "neutral",
      icon: markRaw(LucideSend),
    },
  ];
});

/** The card's tint: what needs chasing first, then how it went. */
function entryTone(post: ContentPost) {
  if (isMissed(post, now.value) || needsApprovalSoon(post, now.value))
    return "danger";
  if (post.status === "Published") return "success";
  if (post.status === "Cancelled") return "neutral";
  return "info";
}

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

<style scoped>
/* Cards take a light wash of their tone; the footer and border carry it a step stronger. */
.entry {
  --tone: var(--outline-gray-3);
  --tone-soft: var(--surface-gray-2);
  background-color: color-mix(
    in srgb,
    var(--tone-soft) 55%,
    var(--surface-base)
  );
  border-color: color-mix(in srgb, var(--tone) 30%, var(--outline-gray-2));
}
.entry-info {
  --tone: var(--info);
  --tone-soft: var(--info-soft);
}
.entry-danger {
  --tone: var(--danger);
  --tone-soft: var(--danger-soft);
}
.entry-success {
  --tone: var(--success);
  --tone-soft: var(--success-soft);
}
.entry-footer {
  background-color: var(--tone-soft);
  border-color: color-mix(in srgb, var(--tone) 20%, var(--outline-gray-2));
}
.entry-rule {
  border-color: color-mix(in srgb, var(--tone) 20%, var(--outline-gray-2));
}
</style>

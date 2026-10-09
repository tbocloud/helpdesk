<template>
  <div class="flex flex-col gap-3">
    <section
      class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
      :aria-label="__('Summary')"
    >
      <div
        v-for="tile in tiles"
        :key="tile.key"
        class="flex items-center gap-3 rounded-xl border px-4 py-3"
        :class="
          tile.warn
            ? 'stat-warning bg-warning-soft'
            : 'border-outline-gray-2 bg-surface-base'
        "
      >
        <div class="min-w-0 flex-1">
          <p
            class="text-sm"
            :class="tile.warn ? 'text-warning' : 'text-ink-gray-7'"
          >
            {{ tile.label }}
          </p>
          <p
            class="truncate font-mono text-[20px] font-semibold tabular-nums leading-snug"
            :class="tile.warn ? 'text-warning' : 'text-ink-gray-9'"
          >
            {{ tile.value }}
          </p>
          <p
            class="truncate text-xs"
            :class="tile.warn ? 'text-warning' : 'text-ink-gray-6'"
            :title="tile.sub"
          >
            {{ tile.sub }}
          </p>
        </div>
        <!-- how much of the period is published, as a ring -->
        <svg
          v-if="tile.ring !== undefined"
          viewBox="0 0 38 38"
          class="size-8 shrink-0 -rotate-90"
          aria-hidden="true"
        >
          <circle
            cx="19"
            cy="19"
            r="15"
            fill="none"
            stroke-width="4"
            style="stroke: var(--outline-gray-2)"
          />
          <circle
            v-if="tile.ring > 0"
            cx="19"
            cy="19"
            r="15"
            fill="none"
            stroke-width="4"
            stroke-linecap="round"
            style="stroke: var(--brand)"
            :stroke-dasharray="`${(tile.ring / 100) * RING} ${RING}`"
          />
          <!-- at 0% a dot marks where progress starts -->
          <circle v-else cx="34" cy="19" r="2.5" style="fill: var(--brand)" />
        </svg>
        <span
          v-else
          class="grid size-8 shrink-0 place-items-center rounded-[10px]"
          :class="tile.iconClass"
        >
          <component :is="tile.icon" class="size-4" aria-hidden="true" />
        </span>
      </div>
    </section>

    <div v-if="active.length" class="flex flex-col gap-1.5">
      <!-- a segment per post while they fit; past that, one block per bucket -->
      <div
        v-if="segments.length <= MAX_SEGMENTS"
        class="flex h-1 gap-1"
        role="img"
        :aria-label="barLabel"
      >
        <div
          v-for="(swatch, i) in segments"
          :key="i"
          class="flex-1 rounded-full"
          :class="swatch"
        />
      </div>
      <div
        v-else
        class="flex h-1 gap-0.5 overflow-hidden rounded-full bg-surface-gray-2"
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
        class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-gray-7"
        aria-hidden="true"
      >
        <span
          v-for="b in buckets"
          :key="b.key"
          class="flex items-center gap-1.5"
        >
          <span class="size-1.5 rounded-full" :class="b.swatch" />
          <span class="font-mono font-semibold tabular-nums text-ink-gray-9">{{
            b.count
          }}</span>
          {{ b.label }}
        </span>
      </div>
    </div>

    <div
      v-if="missed.length"
      class="action-banner flex flex-wrap items-center gap-2.5 rounded-xl border bg-danger-soft px-3 py-2 text-sm text-danger"
      role="status"
    >
      <span
        class="grid size-6 shrink-0 place-items-center rounded-[6px] bg-surface-base"
      >
        <LucideCircleAlert class="size-3.5" aria-hidden="true" />
      </span>
      <span class="min-w-0 flex-1 basis-56">
        <b class="font-semibold">{{
          missed.length === 1
            ? __("1 post needs action.")
            : __("{0} posts need action.", String(missed.length))
        }}</b>
        {{
          missed.length === 1
            ? __("Not published on the planned date. Publish or postpone it.")
            : __("Not published on the planned date. Publish or postpone them.")
        }}
      </span>
      <button
        v-if="filter !== 'missed'"
        type="button"
        class="action-banner-btn inline-flex h-7 shrink-0 items-center rounded-[8px] border bg-surface-base px-3 text-sm font-medium text-danger transition-colors hover:bg-danger-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        @click="filter = 'missed'"
      >
        {{ missed.length === 1 ? __("Show it") : __("Show them") }}
      </button>
    </div>

    <div
      class="flex flex-wrap items-center gap-2"
      role="group"
      :aria-label="__('Filter entries')"
    >
      <button
        v-for="f in filterChips"
        :key="f.key"
        type="button"
        :aria-pressed="filter === f.key"
        class="inline-flex h-8 items-center gap-1.5 rounded-full border pl-3 pr-1 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        :class="
          filter === f.key
            ? 'border-brand bg-brand-soft text-brand-ink'
            : 'border-outline-gray-2 bg-surface-base text-ink-gray-8 hover:bg-surface-gray-2'
        "
        @click="filter = f.key"
      >
        {{ f.label }}
        <span
          class="grid h-5 min-w-[1.25rem] place-items-center rounded-full px-1.5 font-mono text-xs tabular-nums"
          :class="
            filter === f.key
              ? 'bg-brand text-brand-on'
              : f.key === 'missed'
              ? 'bg-danger-soft text-danger'
              : 'bg-surface-gray-2 text-ink-gray-7'
          "
          >{{ f.count }}</span
        >
      </button>
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
        v-if="auth.canEditContent"
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
      class="flex flex-col gap-2 sm:flex-row sm:gap-4"
      :aria-label="dayjs(day.date).format('dddd D MMMM')"
    >
      <div
        class="flex shrink-0 flex-wrap items-center gap-2 sm:w-[64px] sm:flex-col sm:items-stretch"
      >
        <!-- a calendar page: month band, date, weekday -->
        <div
          class="w-[64px] shrink-0 overflow-hidden rounded-[10px] border bg-surface-base pb-1 text-center shadow-sm"
          :class="day.date === today ? 'border-brand' : 'border-outline-gray-2'"
          aria-hidden="true"
        >
          <div
            class="grid h-6 place-items-center bg-brand text-[11px] font-bold uppercase tracking-[0.1em] text-brand-on"
          >
            {{ dayjs(day.date).format("MMM") }}
          </div>
          <div
            class="font-mono text-[22px] font-medium tabular-nums leading-tight"
            :class="day.date === today ? 'text-brand-ink' : 'text-ink-gray-9'"
          >
            {{ dayjs(day.date).format("D") }}
          </div>
          <div
            class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6"
          >
            {{ dayjs(day.date).format("ddd") }}
          </div>
        </div>
        <div class="flex flex-col gap-1.5 sm:items-start">
          <span class="text-[13px] text-ink-gray-6">
            <template v-if="day.date === today">{{ __("Today") }} · </template>
            {{
              day.total === 1
                ? __("1 entry")
                : __("{0} entries", String(day.total))
            }}
          </span>
          <SpecialDayBadge
            v-for="name in day.specialDays"
            :key="name"
            :name="name"
          />
        </div>
      </div>

      <div class="flex min-w-0 flex-1 flex-col gap-3">
        <article
          v-for="post in day.posts"
          :key="post.name"
          class="entry overflow-hidden rounded-[16px] border"
          :class="`entry-${entryTone(post)}`"
          :aria-labelledby="`client-${post.name} entry-${post.name}`"
        >
          <header class="flex flex-wrap items-start gap-x-3 gap-y-2 px-4 pt-3">
            <div class="flex min-w-0 flex-1 basis-72 gap-3">
              <span
                class="grid size-10 shrink-0 place-items-center rounded-[10px] border border-outline-gray-2 bg-surface-base text-ink-gray-7 shadow-sm"
                aria-hidden="true"
              >
                <LucideBuilding2 class="size-[18px]" />
              </span>
              <div class="min-w-0 flex-1">
                <!-- the client leads, shown even when filtered, so every card says whose it is -->
                <p
                  v-if="post.customer"
                  :id="`client-${post.name}`"
                  class="truncate text-lg font-semibold text-ink-gray-9"
                >
                  {{ post.customer }}
                </p>
                <p
                  class="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1"
                >
                  <button
                    :id="`entry-${post.name}`"
                    type="button"
                    class="min-w-0 max-w-full truncate rounded text-left text-base text-ink-gray-7 hover:text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    @click="emit('open', post.name)"
                  >
                    {{ post.title }}
                  </button>
                  <span
                    v-if="post.format"
                    class="inline-flex h-5 items-center rounded-[6px] border border-outline-gray-2 bg-surface-base px-1.5 text-xs text-ink-gray-7"
                    >{{ post.format }}</span
                  >
                </p>
                <SpecialDayBadge
                  v-if="post.special_day"
                  :name="post.special_day"
                  class="mt-1.5"
                />
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
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <ul
                class="flex flex-wrap items-center gap-2"
                :aria-label="__('Platforms')"
              >
                <li
                  v-for="p in platformsOf(post)"
                  :key="p"
                  class="inline-flex h-7 items-center gap-1.5 rounded-full border border-outline-gray-2 bg-surface-base px-2.5 text-sm text-ink-gray-8"
                >
                  <ChannelIcon :channel="p" class="size-[15px] shrink-0" />{{
                    __(p)
                  }}
                </li>
              </ul>
              <span
                class="inline-flex h-7 items-center gap-1.5 rounded-full border border-outline-gray-2 bg-surface-base px-2.5 font-mono text-sm tabular-nums text-ink-gray-8"
              >
                <LucideClock
                  class="size-3.5 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                /><span class="sr-only">{{ __("Time:") }}</span
                ><time :datetime="post.publish_on">{{
                  dayjs(post.publish_on).format("h:mm A")
                }}</time></span
              >
              <StatusPill :post="post" size="md" />
              <Tooltip
                :text="
                  auth.canEditContent
                    ? __('Edit entry')
                    : __('Open to add files')
                "
              >
                <button
                  type="button"
                  class="grid size-7 place-items-center rounded-full border border-outline-gray-2 bg-surface-base text-ink-gray-7 transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                  :aria-label="
                    auth.canEditContent
                      ? __('Edit {0}', post.title)
                      : __('Open {0} to add files', post.title)
                  "
                  @click="emit('open', post.name)"
                >
                  <LucidePencil
                    v-if="auth.canEditContent"
                    class="size-3.5"
                    aria-hidden="true"
                  />
                  <LucidePaperclip v-else class="size-3.5" aria-hidden="true" />
                </button>
              </Tooltip>
            </div>
          </header>

          <div
            class="grid grid-cols-1 gap-2 px-4 pt-2.5 md:grid-cols-[1.65fr_1fr]"
          >
            <div
              class="min-w-0 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-2"
            >
              <p class="text-[13px] text-ink-gray-6">{{ __("Sub copy") }}</p>
              <p
                class="mt-0.5 line-clamp-2 whitespace-pre-line text-sm leading-snug"
                :class="
                  captionOf(post) ? 'text-ink-gray-9' : 'italic text-ink-gray-5'
                "
              >
                {{ captionOf(post) || __("Not written yet") }}
              </p>
            </div>
            <div
              class="min-w-0 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-2"
            >
              <p class="text-[13px] text-ink-gray-6">{{ __("Description") }}</p>
              <p
                class="mt-0.5 line-clamp-2 whitespace-pre-line text-sm leading-snug"
                :class="
                  post.brief ? 'text-ink-gray-9' : 'italic text-ink-gray-5'
                "
              >
                {{ post.brief || __("No description yet") }}
              </p>
            </div>
          </div>

          <div
            class="grid grid-cols-1 gap-2 px-4 pt-2 min-[420px]:grid-cols-2 lg:grid-cols-4"
          >
            <RoleBox
              v-for="role in TEAM_ROLES"
              :key="role.field"
              :label="role.label"
              :role="role.field"
              :people="peopleOf(post, role.field)"
              :can-edit="auth.canEditContent"
              @assign="emit('action', post, 'assign', role.field)"
            />
          </div>

          <footer
            class="entry-footer mt-3 flex flex-wrap items-center gap-2 border-t px-4 py-2"
          >
            <p
              class="flex flex-1 basis-48 items-center gap-2 text-base"
              :class="isMissed(post, now) ? 'text-danger' : 'text-ink-gray-7'"
            >
              <component
                :is="statusIcon(post)"
                class="size-[15px] shrink-0"
                aria-hidden="true"
              />
              {{ statusLine(post) }}
            </p>
            <template v-if="!CLOSED_STATUSES.includes(post.status)">
              <!-- waiting on the head: only they move it on, so no Mark published -->
              <template v-if="post.status === HEAD_REVIEW">
                <template v-if="auth.isDmHead">
                  <button
                    type="button"
                    :class="PRIMARY_BTN"
                    @click="emit('action', post, 'head_approve')"
                  >
                    <LucideCheck class="size-4" aria-hidden="true" />
                    {{ __("Approve") }}
                  </button>
                  <button
                    type="button"
                    :class="OUTLINE_BTN"
                    @click="emit('action', post, 'head_send_back')"
                  >
                    <LucideUndo2
                      class="size-4 text-ink-gray-6"
                      aria-hidden="true"
                    />
                    {{ __("Send back") }}
                  </button>
                </template>
              </template>
              <!-- a post with the client can't be published until they and the head approve -->
              <button
                v-else-if="
                  post.status !== 'Client Review' && auth.canEditContent
                "
                type="button"
                :class="PRIMARY_BTN"
                @click="emit('action', post, 'publish')"
              >
                <LucideSend class="size-4" aria-hidden="true" />
                {{ __("Mark published") }}
              </button>
              <button
                v-if="auth.canEditContent"
                type="button"
                :class="OUTLINE_BTN"
                @click="emit('action', post, 'postpone')"
              >
                <LucideCalendarClock
                  class="size-4 text-ink-gray-6"
                  aria-hidden="true"
                />
                {{ __("Postpone") }}
              </button>
              <Tooltip v-if="auth.canEditContent" :text="__('Cancel post')">
                <button
                  type="button"
                  class="grid size-8 place-items-center rounded-full border border-outline-gray-2 bg-surface-base text-ink-gray-6 transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                  :aria-label="__('Cancel post')"
                  @click="emit('action', post, 'cancel')"
                >
                  <LucideBan class="size-4" aria-hidden="true" />
                </button>
              </Tooltip>
            </template>
            <a
              v-else-if="post.status === 'Published' && post.published_url"
              :href="post.published_url"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 rounded text-sm text-success hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              <LucideExternalLink class="size-3.5" aria-hidden="true" />{{
                __("View post")
              }}
            </a>
          </footer>
        </article>

        <div v-if="auth.canEditContent">
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
import { Button, createResource, dayjs, Tooltip } from "frappe-ui";
import { type Component, computed, markRaw, ref, watch } from "vue";
import LucideBan from "~icons/lucide/ban";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClock from "~icons/lucide/clock";
import LucideExternalLink from "~icons/lucide/external-link";
import LucidePlus from "~icons/lucide/plus";
import LucideSend from "~icons/lucide/send";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucidePencil from "~icons/lucide/pencil";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import { useAuthStore } from "@/stores/auth";
import LucideCheck from "~icons/lucide/check";
import LucideUndo2 from "~icons/lucide/undo-2";
import {
  CLOSED_STATUSES,
  type ContentPost,
  HEAD_REVIEW,
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
import RoleBox from "./RoleBox.vue";
import SpecialDayBadge from "./SpecialDayBadge.vue";
import StatusPill from "./StatusPill.vue";

const auth = useAuthStore();

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

const PRIMARY_BTN =
  "inline-flex h-8 items-center gap-1.5 rounded-[10px] bg-brand px-3 text-sm font-semibold text-brand-on shadow-sm transition-colors hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2";
const OUTLINE_BTN =
  "inline-flex h-8 items-center gap-1.5 rounded-[10px] border border-outline-gray-2 bg-surface-base px-3 text-sm font-medium text-ink-gray-8 transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4";

// circumference of the progress ring (r = 15)
const RING = 2 * Math.PI * 15;

// past this many posts the bar's segments get too thin to read
const MAX_SEGMENTS = 40;

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
// one swatch per post, in the buckets' order
const segments = computed(() =>
  buckets.value.flatMap((b) => Array<string>(b.count).fill(b.swatch))
);
const barLabel = computed(() =>
  buckets.value.map((b) => `${b.count} ${b.label}`).join(", ")
);

interface Tile {
  key: string;
  label: string;
  value: string;
  sub: string;
  // Postponed above 0 tints the whole tile
  warn?: boolean;
  iconClass?: string;
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
      iconClass: "bg-info-soft text-info",
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
      warn: postponedPosts.length > 0,
      iconClass: postponedPosts.length
        ? "bg-surface-base text-warning"
        : "bg-surface-gray-2 text-ink-gray-6",
      icon: markRaw(LucideCalendarClock),
    },
    {
      key: "next",
      label: __("Next post"),
      value: next ? dayjs(next.publish_on).format("ddd D MMM") : "—",
      sub: next
        ? `${dayjs(next.publish_on).format("h:mm A")} · ${
            next.title
          } · ${platformsOf(next).join(", ")}`
        : __("Nothing scheduled"),
      iconClass: "bg-brand-soft text-brand",
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
      // each special day once, so the day heading names them
      specialDays: [
        ...new Set(d.posts.map((p) => p.special_day).filter(Boolean)),
      ] as string[],
    }));
});

function captionOf(post: ContentPost) {
  return htmlToText(post.caption);
}

function statusIcon(post: ContentPost): Component {
  if (post.status === "Published") return LucideSend;
  if (post.status === "Cancelled") return LucideBan;
  if (isMissed(post, now.value)) return LucideCircleAlert;
  return LucideClock;
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
  if (post.status === HEAD_REVIEW)
    return __(
      "Client approved · waiting for the Digital Marketing Head. Goes live {0}.",
      when
    );
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
.stat-warning {
  border-color: color-mix(in srgb, var(--warning) 35%, var(--outline-gray-2));
}
.action-banner,
.action-banner-btn {
  border-color: color-mix(in srgb, var(--danger) 30%, var(--outline-gray-2));
}
</style>

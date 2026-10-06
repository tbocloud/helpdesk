<template>
  <div class="flex flex-col gap-4">
    <p
      v-if="!data.customers.length"
      class="rounded-xl border border-dashed border-outline-gray-3 px-4 py-14 text-center text-p-sm text-ink-gray-5"
    >
      {{ __("No content posts were due in this period.") }}
    </p>

    <template v-else>
      <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatTile
          :label="__('Customers')"
          :value="String(sum.customers)"
          :sub="__('with posts due')"
          :icon="LucideBuilding2"
        />
        <StatTile
          :label="__('Posts published')"
          :value="`${sum.published} / ${sum.posts - sum.upcoming}`"
          :sub="sum.upcoming ? __('{0} not due yet', String(sum.upcoming)) : ''"
          :icon="LucideSend"
          :meter="pct(sum.published, sum.posts - sum.upcoming)"
        />
        <StatTile
          :label="__('On-time rate')"
          :value="pctText(sum.on_time_pct)"
          :sub="__('of published posts')"
          :icon="LucideCircleCheck"
          :value-tone="onTimeTone(sum.on_time_pct)"
        />
        <StatTile
          :label="__('Missed slots')"
          :value="String(sum.missed)"
          :sub="__('due and not published')"
          :icon="LucideCircleAlert"
          :meter="sum.missed ? pct(sum.missed, sum.posts - sum.upcoming) : null"
          tone="danger"
          :value-tone="sum.missed ? 'danger' : 'neutral'"
        />
        <StatTile
          :label="__('Avg. post score')"
          :value="scoreText(sum.avg_score)"
          :sub="__('out of 100')"
          :icon="LucideGauge"
          :meter="sum.avg_score"
          :tone="scoreTone(sum.avg_score)"
          :value-tone="scoreTone(sum.avg_score)"
        />
        <StatTile
          :label="__('Client change requests')"
          :value="String(sum.change_requests)"
          :sub="perPost(sum.change_requests, sum.posts)"
          :icon="LucideMessageSquareWarning"
        />
      </div>

      <div class="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <section
          class="rounded-xl border border-outline-gray-2 bg-surface-base p-4 xl:col-span-3"
        >
          <header class="mb-3 flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __("Delivery by customer") }}
              </h2>
              <p class="text-p-sm text-ink-gray-5">
                {{
                  __(
                    "Posts due in {0}. Click a customer to open it.",
                    periodLabel
                  )
                }}
              </p>
            </div>
            <TimingLegend />
          </header>
          <DeliveryByCustomerChart
            :rows="data.customers"
            :selected="detail?.customer"
            @select="emit('select', $event)"
          />
        </section>
        <section
          class="rounded-xl border border-outline-gray-2 bg-surface-base p-4 xl:col-span-2"
        >
          <header class="mb-3">
            <h2 class="text-base font-semibold text-ink-gray-9">
              {{ __("Delivery over time") }}
            </h2>
            <p class="text-p-sm text-ink-gray-5">
              {{
                data.trend.bucket === "week"
                  ? __("Posts due each week, all customers")
                  : __("Posts due each day, all customers")
              }}
            </p>
          </header>
          <DeliveryTrendChart :trend="data.trend" />
        </section>
      </div>

      <!-- every customer, comparable at a glance -->
      <section
        class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
      >
        <header class="p-4">
          <h2 class="text-base font-semibold text-ink-gray-9">
            {{ __("Customers") }}
          </h2>
        </header>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[760px] text-left text-sm">
            <thead
              class="border-y border-outline-gray-2 bg-surface-gray-1 text-xs text-ink-gray-5"
            >
              <tr>
                <th scope="col" class="px-4 py-2 font-medium">
                  {{ __("Customer") }}
                </th>
                <th scope="col" class="px-4 py-2 text-right font-medium">
                  {{ __("Posts") }}
                </th>
                <th scope="col" class="px-4 py-2 text-right font-medium">
                  {{ __("Published") }}
                </th>
                <th scope="col" class="px-4 py-2 text-right font-medium">
                  {{ __("On time") }}
                </th>
                <th scope="col" class="px-4 py-2 text-right font-medium">
                  {{ __("Missed") }}
                </th>
                <th scope="col" class="px-4 py-2 text-right font-medium">
                  {{ __("Changes") }}
                </th>
                <th scope="col" class="px-4 py-2 text-right font-medium">
                  {{ __("Team") }}
                </th>
                <th scope="col" class="w-48 px-4 py-2 font-medium">
                  {{ __("Avg. score") }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in data.customers"
                :key="row.customer"
                class="cursor-pointer border-b border-outline-gray-1 last:border-0"
                :class="
                  row.customer === detail?.customer
                    ? 'bg-brand-soft'
                    : 'hover:bg-surface-gray-1'
                "
                tabindex="0"
                :aria-selected="row.customer === detail?.customer"
                @click="emit('select', row.customer)"
                @keydown.enter="emit('select', row.customer)"
              >
                <td
                  class="px-4 py-2.5 font-medium"
                  :class="
                    row.customer === detail?.customer
                      ? 'text-brand-ink'
                      : 'text-ink-gray-9'
                  "
                >
                  {{ row.customer || __("No customer") }}
                </td>
                <td class="px-4 py-2.5 text-right tabular-nums text-ink-gray-8">
                  {{ row.posts }}
                </td>
                <td class="px-4 py-2.5 text-right tabular-nums text-ink-gray-8">
                  {{ row.published }}
                </td>
                <td
                  class="px-4 py-2.5 text-right font-semibold tabular-nums"
                  :class="
                    row.on_time_pct == null
                      ? 'text-ink-gray-5'
                      : INK[onTimeTone(row.on_time_pct)]
                  "
                >
                  {{ pctText(row.on_time_pct) }}
                </td>
                <td class="px-4 py-2.5 text-right tabular-nums">
                  <CountPill :value="row.missed" tone="danger" />
                </td>
                <td class="px-4 py-2.5 text-right tabular-nums">
                  <CountPill :value="row.change_requests" tone="warning" />
                </td>
                <td class="px-4 py-2.5 text-right tabular-nums text-ink-gray-8">
                  {{ row.people }}
                </td>
                <td class="px-4 py-2.5">
                  <div class="flex items-center gap-2">
                    <b
                      class="w-7 text-right text-sm font-semibold tabular-nums"
                      :class="
                        row.avg_score == null
                          ? 'text-ink-gray-5'
                          : INK[scoreTone(row.avg_score)]
                      "
                      >{{ scoreText(row.avg_score) }}</b
                    >
                    <ScoreBar
                      class="flex-1"
                      :value="row.avg_score"
                      :tone="scoreTone(row.avg_score)"
                    />
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- the selected customer -->
      <template v-if="detail">
        <section
          class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
          :aria-label="detail.customer || __('No customer')"
        >
          <header class="mb-4 flex flex-wrap items-center gap-3">
            <div
              class="flex size-11 items-center justify-center rounded-lg bg-surface-gray-2 text-ink-gray-6"
              aria-hidden="true"
            >
              <LucideBuilding2 class="size-5" />
            </div>
            <div class="min-w-0 flex-1">
              <h2 class="text-xl font-semibold text-ink-gray-9">
                {{ detail.customer || __("No customer") }}
              </h2>
              <p class="text-p-sm text-ink-gray-5">
                {{
                  __(
                    "{0} posts due in {1}",
                    String(detail.summary.posts),
                    periodLabel
                  )
                }}
              </p>
            </div>
          </header>
          <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Tile
              :tone="scoreTone(ds.avg_score)"
              :label="__('Avg. post score')"
              :value="scoreText(ds.avg_score)"
              :sub="vsAll"
              :sub-tone="vsAllTone"
            />
            <Tile
              :label="__('Posts published')"
              :value="`${ds.published} / ${ds.posts - ds.upcoming}`"
              :sub="
                ds.missed
                  ? __('{0} missed', String(ds.missed))
                  : __('nothing missed')
              "
              :sub-tone="ds.missed ? 'danger' : 'muted'"
            />
            <Tile
              :tone="onTimeTone(ds.on_time_pct)"
              :label="__('On-time rate')"
              :value="pctText(ds.on_time_pct)"
              :sub="__('all customers {0}', pctText(sum.on_time_pct))"
            />
            <Tile
              :label="__('Client change requests')"
              :value="String(ds.change_requests)"
              :sub="perPost(ds.change_requests, ds.posts)"
            />
            <Tile
              :label="__('Postponed')"
              :value="String(ds.postponed)"
              :sub="__('of {0} posts', String(ds.posts))"
            />
            <Tile
              :label="__('Team members')"
              :value="String(detail.people.length)"
              :sub="__('worked on these posts')"
            />
          </div>
        </section>

        <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <!-- who worked on this customer -->
          <section
            class="rounded-xl border border-outline-gray-2 bg-surface-base p-4 xl:col-span-2"
          >
            <h3 class="text-base font-semibold text-ink-gray-9">
              {{ __("Team on this customer") }}
            </h3>
            <p class="mb-3 text-p-sm text-ink-gray-5">
              {{
                __(
                  "Each person's posts for this customer, ranked by average score. Open someone to see all their content."
                )
              }}
            </p>
            <p
              v-if="!detail.people.length"
              class="rounded-lg border border-dashed border-outline-gray-3 px-3 py-6 text-center text-p-sm text-ink-gray-5"
            >
              {{ __("Nobody is on these posts yet.") }}
            </p>
            <ul v-else class="flex flex-col divide-y divide-outline-gray-1">
              <li v-for="p in detail.people" :key="p.employee">
                <button
                  type="button"
                  class="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 rounded-lg px-2 py-2.5 text-left hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_10rem]"
                  :title="
                    __('Open {0}\'s content performance', p.employee_name)
                  "
                  @click="emit('person', p.employee)"
                >
                  <div class="flex min-w-0 items-center gap-2.5">
                    <Avatar
                      size="lg"
                      :image="p.image"
                      :label="p.employee_name"
                    />
                    <div class="min-w-0">
                      <div
                        class="truncate text-sm font-semibold text-ink-gray-9"
                      >
                        {{ p.employee_name }}
                      </div>
                      <div class="flex flex-wrap gap-1 pt-0.5">
                        <span
                          v-for="r in rolesOf(p)"
                          :key="r.role"
                          class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-2xs font-medium text-ink-gray-7"
                        >
                          {{ r.label }} · {{ r.count }}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div class="hidden text-xs text-ink-gray-6 md:block">
                    <span class="tabular-nums"
                      >{{ p.published }}/{{ p.posts - p.upcoming }}</span
                    >
                    {{ __("published") }}
                    <template v-if="p.missed">
                      ·
                      <span class="font-medium text-danger">{{
                        __("{0} missed", String(p.missed))
                      }}</span>
                    </template>
                    <template v-if="p.change_requests">
                      · {{ __("{0} changes", String(p.change_requests)) }}
                    </template>
                  </div>
                  <div class="flex items-center gap-2">
                    <b
                      class="w-7 text-right text-sm font-semibold tabular-nums"
                      :class="INK[scoreTone(p.avg_score)]"
                      >{{ scoreText(p.avg_score) }}</b
                    >
                    <ScoreBar
                      class="flex-1"
                      :value="p.avg_score"
                      :tone="scoreTone(p.avg_score)"
                    />
                  </div>
                </button>
              </li>
            </ul>
          </section>

          <div class="flex flex-col gap-4">
            <MixCard
              channels
              :title="__('Channels')"
              :rows="
                detail.channels.map((c: any) => ({
                  key: c.channel,
                  count: c.posts,
                  score: c.avg_score,
                }))
              "
            />
            <MixCard
              :title="__('Formats')"
              :rows="
                detail.formats.map((f: any) => ({ key: f.format, count: f.posts }))
              "
            />
          </div>
        </div>

        <!-- the customer's posts -->
        <section
          class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
        >
          <header class="flex flex-wrap items-start justify-between gap-2 p-4">
            <div>
              <h3 class="text-base font-semibold text-ink-gray-9">
                {{ __("Posts ({0})", String(detail.posts.length)) }}
              </h3>
              <p class="text-p-sm text-ink-gray-5">
                {{ __("How each post was delivered, and who was on it") }}
              </p>
            </div>
            <div
              class="inline-flex rounded-lg bg-surface-gray-2 p-0.5"
              role="tablist"
              :aria-label="__('Sort posts')"
            >
              <button
                v-for="o in SORTS"
                :key="o.key"
                type="button"
                role="tab"
                :aria-selected="sort === o.key"
                class="h-7 rounded-md px-3 text-sm"
                :class="
                  sort === o.key
                    ? 'bg-brand text-brand-on shadow-sm'
                    : 'text-ink-gray-6 hover:text-ink-gray-8'
                "
                @click="sort = o.key"
              >
                {{ o.label }}
              </button>
            </div>
          </header>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[820px] text-left text-sm">
              <thead
                class="border-y border-outline-gray-2 bg-surface-gray-1 text-xs text-ink-gray-5"
              >
                <tr>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Date") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Post") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Channel") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Team") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Score") }}
                  </th>
                  <th
                    scope="col"
                    class="whitespace-nowrap px-4 py-2 font-medium"
                  >
                    {{ __("Timing") }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="p in sortedPosts"
                  :key="p.name"
                  class="border-b border-outline-gray-1 last:border-0"
                >
                  <td
                    class="whitespace-nowrap px-4 py-2.5 font-mono text-xs tabular-nums text-ink-gray-7"
                  >
                    {{ dayjs(p.publish_on).format("ddd D MMM") }}
                  </td>
                  <td class="max-w-[16rem] px-4 py-2.5">
                    <div class="truncate font-medium text-ink-gray-9">
                      {{ p.title }}
                    </div>
                    <div class="text-xs text-ink-gray-5">
                      {{ p.format }}
                      <template v-if="p.changes">
                        ·
                        {{
                          p.changes === 1
                            ? __("1 change request")
                            : __("{0} change requests", String(p.changes))
                        }}
                      </template>
                    </div>
                  </td>
                  <td class="whitespace-nowrap px-4 py-2.5">
                    <span
                      v-for="(c, i) in p.platforms"
                      :key="c"
                      class="font-medium"
                      :style="{ color: channelColor(c) }"
                      >{{ c
                      }}<template v-if="i < p.platforms.length - 1"
                        >,
                      </template></span
                    >
                  </td>
                  <td class="px-4 py-2.5 text-xs text-ink-gray-6">
                    <span v-if="!teamOf(p).length" class="text-ink-gray-4"
                      >—</span
                    >
                    <span
                      v-for="m in teamOf(p)"
                      :key="m.name"
                      class="block whitespace-nowrap"
                      :title="m.roles"
                    >
                      <span class="text-ink-gray-8">{{ m.name }}</span>
                      <span class="text-ink-gray-5"> · {{ m.short }}</span>
                    </span>
                  </td>
                  <td class="px-4 py-2.5">
                    <div class="flex items-center gap-2">
                      <b
                        class="w-7 text-right text-sm font-semibold tabular-nums"
                        :class="
                          p.score == null
                            ? 'text-ink-gray-5'
                            : INK[scoreTone(p.score)]
                        "
                        >{{ scoreText(p.score) }}</b
                      >
                      <ScoreBar
                        class="w-20"
                        :value="p.score"
                        :tone="scoreTone(p.score)"
                      />
                    </div>
                  </td>
                  <td class="whitespace-nowrap px-4 py-2.5">
                    <span
                      class="inline-flex h-6 items-center gap-1 rounded-full px-2 text-xs font-medium"
                      :class="TIMING[p.timing].class"
                    >
                      <component
                        :is="TIMING[p.timing].icon"
                        class="size-3.5"
                        aria-hidden="true"
                      />
                      {{ __(p.timing) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>

      <p class="text-xs text-ink-gray-5">
        {{
          __(
            "Post score: published on time 100, late 60, missed 0, minus 10 for each client change request. Posts not due yet are counted but not scored."
          )
        }}
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Avatar, dayjs } from "frappe-ui";
import { computed, h, ref } from "vue";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideGauge from "~icons/lucide/gauge";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideMessageSquareWarning from "~icons/lucide/message-square-warning";
import LucideSend from "~icons/lucide/send";
import { useChartColors } from "../chartTheme";
import {
  channelColor,
  FILL,
  INK,
  onTimeTone,
  pctText,
  roles,
  scoreText,
  scoreTone,
  TIMINGS,
  timingColor,
  TRACK,
  type Tone,
} from "../performanceMeta";
import DeliveryByCustomerChart from "./DeliveryByCustomerChart.vue";
import DeliveryTrendChart from "./DeliveryTrendChart.vue";
import StatTile from "./StatTile.vue";

const props = defineProps<{ data: any; periodLabel: string }>();
const emit = defineEmits<{
  (e: "select", customer: string): void;
  (e: "person", employee: string): void;
}>();

const ROLES = roles();
const TIMING: Record<string, { class: string; icon: unknown }> = {
  "On time": { class: "bg-success-soft text-success", icon: LucideCircleCheck },
  Late: { class: "bg-warning-soft text-warning", icon: LucideClock },
  Missed: { class: "bg-danger-soft text-danger", icon: LucideCircleAlert },
  Upcoming: {
    class: "bg-surface-gray-2 text-ink-gray-6",
    icon: LucideHourglass,
  },
};
const SORTS = [
  { key: "date", label: __("By date") },
  { key: "best", label: __("Best first") },
] as const;

const sort = ref<"best" | "date">("date");
const sum = computed(() => props.data.summary);
const detail = computed(() => props.data.detail);
const ds = computed(() => detail.value.summary);

const pct = (part: number, whole: number) =>
  whole ? Math.round((part / whole) * 100) : null;
const perPost = (n: number, posts: number) =>
  posts ? __("{0} per post", (n / posts).toFixed(1)) : "";

const vsAll = computed(() => {
  if (ds.value.avg_score == null || sum.value.avg_score == null) return "";
  const diff = ds.value.avg_score - sum.value.avg_score;
  if (diff === 0) return __("same as all customers");
  return __("{0} vs. all customers", `${diff > 0 ? "+" : ""}${diff}`);
});
const vsAllTone = computed(() => {
  if (ds.value.avg_score == null || sum.value.avg_score == null) return "muted";
  return ds.value.avg_score >= sum.value.avg_score ? "success" : "danger";
});

function rolesOf(person: any) {
  return ROLES.filter((r) => person.roles[r.role]).map((r) => ({
    ...r,
    count: person.roles[r.role],
  }));
}

/** One line per person on a post, however many roles they held on it. */
function teamOf(post: any) {
  const people = new Map<string, { name: string; held: typeof ROLES }>();
  for (const r of ROLES) {
    // each role is a list: a role can have more than one person
    for (const m of post.team[r.role] ?? []) {
      const entry = people.get(m.user) ?? { name: m.name, held: [] };
      entry.held.push(r);
      people.set(m.user, entry);
    }
  }
  return [...people.values()].map((e) => ({
    name: e.name,
    short: e.held.map((r) => r.short).join(" "),
    roles: e.held.map((r) => r.label).join(", "),
  }));
}

const sortedPosts = computed(() => {
  const posts = [...(detail.value?.posts ?? [])];
  if (sort.value === "date")
    return posts.sort((a, b) => (a.publish_on < b.publish_on ? -1 : 1));
  // best first; posts not scored yet go last
  return posts.sort(
    (a, b) =>
      (b.score ?? -1) - (a.score ?? -1) ||
      (a.publish_on < b.publish_on ? -1 : 1)
  );
});

// small presentational pieces kept local to this view
const ScoreBar = (p: { value: number | null; tone?: Tone }) =>
  h("div", { class: "h-2 rounded-full bg-surface-gray-2" }, [
    h("div", {
      class: `h-full rounded-full ${FILL[p.tone || "neutral"]}`,
      style: { width: `${Math.max(0, Math.min(p.value ?? 0, 100))}%` },
    }),
  ]);
ScoreBar.props = ["value", "tone"];

/** A count, in a coloured pill when it isn't zero. */
const CountPill = (p: { value: number; tone: Tone }) =>
  p.value
    ? h(
        "span",
        {
          class: `inline-flex min-w-7 justify-center rounded-full px-2 py-0.5 text-xs font-semibold ${
            TRACK[p.tone]
          } ${INK[p.tone]}`,
        },
        String(p.value)
      )
    : h("span", { class: "text-ink-gray-5" }, "0");
CountPill.props = ["value", "tone"];

const colors = useChartColors();
const TimingLegend = () =>
  h(
    "ul",
    {
      class: "flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-gray-6",
      "aria-label": __("Legend"),
    },
    TIMINGS.map((t) =>
      h("li", { class: "flex items-center gap-1.5" }, [
        h("span", {
          class: "size-2.5 rounded-sm",
          style: { background: timingColor(colors.value, t) },
          "aria-hidden": "true",
        }),
        t === "Upcoming" ? __("Not due yet") : __(t),
      ])
    )
  );

const MixCard = (p: {
  channels?: boolean;
  title: string;
  rows: { key: string; count: number; score?: number | null }[];
}) => {
  const max = Math.max(1, ...p.rows.map((r) => r.count));
  return h(
    "section",
    { class: "rounded-xl border border-outline-gray-2 bg-surface-base p-4" },
    [
      h(
        "h3",
        { class: "mb-3 text-base font-semibold text-ink-gray-9" },
        p.title
      ),
      h(
        "ul",
        { class: "flex flex-col gap-2.5", "aria-label": p.title },
        p.rows.map((r) =>
          h(
            "li",
            {
              class:
                "grid grid-cols-[6rem_1fr_1.5rem_2.5rem] items-center gap-2 text-sm",
            },
            [
              h(
                "span",
                {
                  class: "truncate font-medium",
                  style: {
                    color: p.channels ? channelColor(r.key) : undefined,
                  },
                },
                r.key
              ),
              h("div", { class: "h-2 rounded-full bg-surface-gray-2" }, [
                h("div", {
                  class: `h-full rounded-full ${
                    p.channels ? "" : "bg-surface-gray-7"
                  }`,
                  style: {
                    width: `${(r.count / max) * 100}%`,
                    background: p.channels ? channelColor(r.key) : undefined,
                  },
                }),
              ]),
              h(
                "span",
                {
                  class:
                    "text-right font-mono text-xs tabular-nums text-ink-gray-6",
                },
                String(r.count)
              ),
              r.score !== undefined
                ? h(
                    "span",
                    {
                      class:
                        "rounded bg-surface-gray-2 px-1.5 py-0.5 text-center font-mono text-xs font-semibold tabular-nums text-ink-gray-7",
                      title: __("Average score"),
                    },
                    scoreText(r.score)
                  )
                : h("span"),
            ]
          )
        )
      ),
    ]
  );
};
MixCard.props = ["title", "rows", "channels"];

const Tile = (p: {
  label: string;
  value: string;
  sub?: string;
  subTone?: "muted" | "success" | "danger";
  /** colours the value, only when that says how it went */
  tone?: Tone;
}) =>
  h("div", { class: "rounded-lg border border-outline-gray-2 p-3" }, [
    h("div", { class: "text-xs text-ink-gray-6" }, p.label),
    h(
      "div",
      {
        class: `mt-0.5 truncate text-2xl font-semibold tabular-nums ${
          !p.tone || p.tone === "neutral" ? "text-ink-gray-9" : INK[p.tone]
        }`,
      },
      p.value
    ),
    p.sub
      ? h(
          "div",
          {
            class: `text-xs ${
              p.subTone === "success"
                ? "text-success"
                : p.subTone === "danger"
                ? "text-danger"
                : "text-ink-gray-6"
            }`,
          },
          p.sub
        )
      : null,
  ]);
Tile.props = ["label", "value", "sub", "subTone", "tone"];
</script>

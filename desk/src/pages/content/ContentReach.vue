<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex min-w-0 flex-col gap-1">
          <div
            class="flex min-w-0 items-center gap-1.5 text-lg font-bold md:text-[28px] md:leading-[1.2] md:tracking-[-0.02em]"
          >
            <router-link
              :to="{ name: 'ContentCalendar' }"
              class="truncate rounded text-ink-gray-6 hover:text-ink-gray-9"
              >{{ __("Content Calendar") }}</router-link
            >
            <LucideChevronRight
              class="size-5 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            <h1 class="truncate text-ink-gray-9">{{ __("Reach report") }}</h1>
          </div>
          <p class="hidden text-[14px] text-ink-gray-6 md:block">
            {{
              __(
                "How far each client's Facebook Page and Instagram account reached."
              )
            }}
          </p>
        </div>
      </template>
      <template #right-header>
        <Button
          v-if="selected?.can_sync && selected.insights_allowed"
          size="md"
          :label="__('Sync now')"
          :tooltip="__('Read the last 90 days from Meta again')"
          :loading="syncing"
          @click="syncNow"
        >
          <template #prefix
            ><LucideRefreshCw class="size-[18px]" aria-hidden="true"
          /></template>
        </Button>
        <Button
          size="md"
          :label="__('Download PDF')"
          :tooltip="__('Download this report as a PDF to send to the client')"
          :disabled="!data?.report"
          @click="downloadPdf"
        >
          <template #prefix
            ><LucideFileText class="size-[18px]" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <div
          class="flex flex-wrap items-end gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
        >
          <div class="w-full sm:w-72">
            <FormControl
              v-model="filters.project"
              type="select"
              size="md"
              :label="__('Client')"
              :options="clientOptions"
              :disabled="!clientOptions.length"
            />
          </div>
          <div class="w-full sm:w-44">
            <FormControl
              v-model="filters.from_date"
              type="date"
              size="md"
              :label="__('From')"
            />
          </div>
          <div class="w-full sm:w-44">
            <FormControl
              v-model="filters.to_date"
              type="date"
              size="md"
              :label="__('To')"
            />
          </div>
          <span class="pb-2.5 text-[13px] text-ink-gray-6">{{
            periodLabel
          }}</span>
        </div>

        <div
          v-if="report.error"
          class="flex items-center justify-between gap-3 rounded-xl bg-danger-soft px-4 py-3.5 text-[13px] text-danger"
          role="alert"
        >
          {{ errorText(report.error, __("Couldn't load the report.")) }}
          <Button size="sm" :label="__('Retry')" @click="report.reload()" />
        </div>

        <div
          v-else-if="report.loading && !data"
          class="grid grid-cols-2 gap-3 lg:grid-cols-4"
          aria-busy="true"
        >
          <div
            v-for="i in 4"
            :key="i"
            class="h-28 animate-pulse rounded-xl bg-surface-gray-3"
          />
          <div
            class="col-span-2 h-72 animate-pulse rounded-xl bg-surface-gray-3 lg:col-span-4"
          />
        </div>

        <template v-else-if="data">
          <!-- why there's nothing to show, and what to do about it -->
          <p
            v-if="!data.enabled"
            class="flex items-start gap-2 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3.5 text-p-sm text-ink-gray-7"
          >
            <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {{
              __(
                "Reach reports are off. A System Manager turns them on in Settings → Meta once Meta has approved the insights permissions."
              )
            }}
          </p>

          <p
            v-if="!data.connections.length"
            class="rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-14 text-center text-p-sm text-ink-gray-6"
          >
            {{
              __(
                "No client of yours has connected Meta yet. Connect it from the project's Meta tab."
              )
            }}
          </p>

          <template v-else-if="selected">
            <div
              v-if="!selected.insights_allowed"
              class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-warning-soft px-4 py-3.5 text-p-sm text-ink-gray-8"
              role="status"
            >
              <span class="flex items-start gap-2">
                <LucideTriangleAlert
                  class="mt-0.5 size-4 shrink-0 text-warning"
                  aria-hidden="true"
                />
                {{
                  __(
                    "This client hasn't allowed Meta to share their reach. Connect Meta again from the project and allow the insights permissions."
                  )
                }}
              </span>
              <Button
                size="sm"
                :label="__('Open the Meta tab')"
                :route="{
                  name: 'TaskyMeta',
                  params: { projectId: selected.project },
                }"
              />
            </div>
            <p
              v-else-if="!selected.insights_synced_on"
              class="flex items-start gap-2 rounded-xl bg-info-soft px-4 py-3.5 text-p-sm text-ink-gray-8"
              role="status"
            >
              <LucideClock
                class="mt-0.5 size-4 shrink-0 text-info"
                aria-hidden="true"
              />
              {{
                __(
                  "The first sync is running: the last 90 days arrive in a few minutes. Reload then."
                )
              }}
            </p>
            <p
              v-if="selected.insights_error"
              class="flex items-start gap-2 rounded-xl bg-warning-soft px-4 py-3.5 text-p-sm text-ink-gray-8"
              role="alert"
            >
              <LucideTriangleAlert
                class="mt-0.5 size-4 shrink-0 text-warning"
                aria-hidden="true"
              />
              {{ selected.insights_error }}
            </p>

            <div
              v-if="data.report"
              class="flex flex-col gap-4 transition-opacity"
              :class="report.loading ? 'opacity-60' : ''"
            >
              <section
                class="grid grid-cols-2 gap-3 lg:grid-cols-4"
                :aria-label="__('Totals')"
              >
                <StatTile
                  v-for="tile in tiles"
                  :key="tile.label"
                  :label="tile.label"
                  :value="tile.value"
                  :sub="tile.sub"
                  :icon="tile.icon"
                  :delta="tile.delta"
                  :delta-text="tile.deltaText"
                />
              </section>

              <section
                class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
                :aria-labelledby="ids.daily"
              >
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2
                      :id="ids.daily"
                      class="text-base font-semibold text-ink-gray-9"
                    >
                      {{ __("Day by day") }}
                    </h2>
                    <p class="text-p-sm text-ink-gray-6">
                      {{ metricHint }}
                    </p>
                  </div>
                  <TabButtons
                    :model-value="metric"
                    :aria-label="__('Number to show')"
                    :options="metricOptions"
                    @update:model-value="metric = $event"
                  />
                </div>
                <WeekLineChart
                  v-if="data.report.days.length && hasDaily"
                  :days="data.report.days"
                  :series="chartSeries"
                  :label="__('{0} per day', currentMetricLabel)"
                  day-format="D MMM"
                  area
                  height="h-64"
                />
                <p v-else class="py-14 text-center text-p-sm text-ink-gray-6">
                  {{ __("No numbers from Meta for these days yet.") }}
                </p>
              </section>

              <div
                class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]"
              >
                <section
                  class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base"
                  :aria-labelledby="ids.posts"
                >
                  <header class="px-4 pb-2 pt-4">
                    <h2
                      :id="ids.posts"
                      class="text-base font-semibold text-ink-gray-9"
                    >
                      {{ __("Posts by reach") }}
                    </h2>
                    <p class="text-p-sm text-ink-gray-6">
                      {{
                        data.report.post_count > data.report.posts.length
                          ? __(
                              "The top {0} of {1} posts in this period",
                              String(data.report.posts.length),
                              String(data.report.post_count)
                            )
                          : __(
                              "{0} posts in this period",
                              String(data.report.post_count)
                            )
                      }}
                    </p>
                  </header>
                  <p
                    v-if="!data.report.posts.length"
                    class="px-4 pb-10 pt-6 text-center text-p-sm text-ink-gray-6"
                  >
                    {{ __("Nothing was posted in this period.") }}
                  </p>
                  <ul v-else class="divide-y divide-outline-gray-1">
                    <li
                      v-for="post in data.report.posts"
                      :key="post.name"
                      class="flex gap-3 px-4 py-3"
                    >
                      <div
                        class="grid size-14 shrink-0 place-items-center overflow-hidden rounded-lg bg-surface-gray-2"
                      >
                        <img
                          v-if="
                            post.thumbnail_url && !brokenImages.has(post.name)
                          "
                          :src="post.thumbnail_url"
                          alt=""
                          class="size-full object-cover"
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @error="brokenImages.add(post.name)"
                        />
                        <component
                          :is="KIND_ICONS[post.kind] || LucideImage"
                          v-else
                          class="size-5 text-ink-gray-5"
                          aria-hidden="true"
                        />
                      </div>
                      <div class="flex min-w-0 flex-1 flex-col gap-1">
                        <p class="line-clamp-2 text-p-sm text-ink-gray-9">
                          {{ post.caption || __("No caption") }}
                        </p>
                        <p class="text-xs text-ink-gray-6">
                          {{ __(post.platform) }} ·
                          {{ __(post.kind || "Other") }}
                          ·
                          {{ dateFormat(post.posted_on, "D MMM, h:mm a") }}
                          <template v-if="post.content_post">
                            ·
                            <router-link
                              :to="{
                                name: 'ContentCalendar',
                                query: { post: post.content_post },
                              }"
                              class="rounded text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                              >{{ __("In the calendar") }}</router-link
                            >
                          </template>
                        </p>
                        <p
                          v-if="post.insights_note"
                          class="text-xs text-ink-gray-6"
                        >
                          {{ post.insights_note }}
                        </p>
                      </div>
                      <dl
                        class="grid shrink-0 grid-cols-[auto_auto] content-start gap-x-3 gap-y-0.5 text-right text-xs tabular-nums"
                      >
                        <dt class="text-ink-gray-6">{{ __("Reach") }}</dt>
                        <dd class="font-semibold text-ink-gray-9">
                          {{ formatCount(post.reach) }}
                        </dd>
                        <dt class="text-ink-gray-6">
                          {{ __("Interactions") }}
                        </dt>
                        <dd class="text-ink-gray-8">
                          {{ formatCount(post.interactions) }}
                        </dd>
                      </dl>
                      <a
                        v-if="post.permalink"
                        :href="post.permalink"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="grid size-8 shrink-0 place-items-center rounded-lg text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                        :aria-label="
                          __('Open the post on {0}', __(post.platform))
                        "
                      >
                        <LucideExternalLink class="size-4" aria-hidden="true" />
                      </a>
                    </li>
                  </ul>
                </section>

                <section
                  class="flex flex-col gap-3 self-start rounded-xl border border-outline-gray-2 bg-surface-base p-4"
                  :aria-labelledby="ids.kinds"
                >
                  <div>
                    <h2
                      :id="ids.kinds"
                      class="text-base font-semibold text-ink-gray-9"
                    >
                      {{ __("What works best") }}
                    </h2>
                    <p class="text-p-sm text-ink-gray-6">
                      {{ __("Average reach per post, by kind") }}
                    </p>
                  </div>
                  <p
                    v-if="!data.report.kinds.length"
                    class="py-6 text-center text-p-sm text-ink-gray-6"
                  >
                    {{ __("No posts in this period.") }}
                  </p>
                  <ul v-else class="flex flex-col gap-3">
                    <li
                      v-for="kind in data.report.kinds"
                      :key="kind.kind"
                      class="flex flex-col gap-1"
                    >
                      <div
                        class="flex items-baseline justify-between gap-2 text-sm"
                      >
                        <span class="text-ink-gray-8">
                          {{ __(kind.kind) }}
                          <span class="text-xs text-ink-gray-6">
                            · {{ __("{0} posts", String(kind.posts)) }}
                          </span>
                        </span>
                        <b class="font-semibold tabular-nums text-ink-gray-9">{{
                          formatCount(kind.average_reach)
                        }}</b>
                      </div>
                      <span
                        class="h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                        aria-hidden="true"
                      >
                        <span
                          class="block h-full rounded-full bg-brand"
                          :style="{
                            width: `${kindWidth(kind.average_reach)}%`,
                          }"
                        />
                      </span>
                    </li>
                  </ul>
                </section>
              </div>

              <p class="text-xs text-ink-gray-6">
                {{ __("Numbers from Meta, synced every night.") }}
                <template v-if="selected.insights_synced_on">
                  {{
                    __(
                      "Last synced {0}.",
                      dateFormat(selected.insights_synced_on, "D MMM, h:mm a")
                    )
                  }}
                </template>
                {{
                  __(
                    "Reach is added up day by day, so a person reached on two days counts twice. Meta can be up to two days late."
                  )
                }}
              </p>
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import StatTile from "@/components/StatTile.vue";
import WeekLineChart, {
  type WeekLine,
} from "@/pages/sales-dashboard/WeekLineChart.vue";
import { __ } from "@/translation";
import { dateFormat, errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideClock from "~icons/lucide/clock";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideEye from "~icons/lucide/eye";
import LucideFileText from "~icons/lucide/file-text";
import LucideFilm from "~icons/lucide/film";
import LucideGalleryHorizontal from "~icons/lucide/gallery-horizontal";
import LucideHeart from "~icons/lucide/heart";
import LucideImage from "~icons/lucide/image";
import LucideInfo from "~icons/lucide/info";
import LucideRadio from "~icons/lucide/radio";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideText from "~icons/lucide/text";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUsers from "~icons/lucide/users";
import { formatCount } from "./boost";

type Platform = "Facebook" | "Instagram";
type Metric = "reach" | "views" | "engagements";

interface Connection {
  project: string;
  customer: string | null;
  facebook_page_name: string | null;
  instagram_username: string | null;
  insights_allowed: boolean;
  insights_synced_on: string | null;
  insights_error: string | null;
  can_sync: boolean;
}
interface Totals {
  reach: number;
  views: number;
  engagements: number;
  net_follows: number;
}
interface PlatformSummary {
  platform: Platform;
  current: Totals;
  previous: Totals | null;
  followers: number | null;
  followers_before: number | null;
  posts: number;
  engagement_rate: number | null;
}
interface Post {
  name: string;
  platform: Platform;
  kind: string | null;
  posted_on: string;
  caption: string | null;
  permalink: string | null;
  thumbnail_url: string | null;
  reach: number;
  interactions: number;
  content_post: string | null;
  insights_note: string | null;
}
interface Report {
  platforms: PlatformSummary[];
  days: string[];
  series: Record<Platform, Record<Metric, number[]>>;
  posts: Post[];
  post_count: number;
  kinds: { kind: string; posts: number; average_reach: number }[];
  engagement_rate: number | null;
}
interface ReachData {
  enabled: boolean;
  connections: Connection[];
  selected: string | null;
  report: Report | null;
}

// one accent and a neutral: the legend names each line, so colour is never the only cue
const PLATFORM_COLORS: Record<Platform, string> = {
  Facebook: "--brand",
  Instagram: "--ink-gray-6",
};
const KIND_ICONS: Record<string, unknown> = {
  Image: LucideImage,
  Carousel: LucideGalleryHorizontal,
  Video: LucideFilm,
  Reel: LucideFilm,
  Story: LucideRadio,
  Text: LucideText,
};

const route = useRoute();
const router = useRouter();
const ids = { daily: useId(), posts: useId(), kinds: useId() };

const filters = reactive({
  project: String(route.query.project || ""),
  from_date: dayjs().startOf("month").format("YYYY-MM-DD"),
  to_date: dayjs().endOf("month").format("YYYY-MM-DD"),
});

const periodLabel = computed(() => {
  const from = dayjs(filters.from_date);
  const to = dayjs(filters.to_date);
  if (!from.isValid() || !to.isValid()) return "";
  return `${from.format("D MMM")} – ${to.format("D MMM YYYY")}`;
});

const report = createResource({
  url: "helpdesk.api.meta_insights.get_reach_report",
  makeParams: () => ({
    from_date: filters.from_date,
    to_date: filters.to_date,
    ...(filters.project ? { project: filters.project } : {}),
  }),
  auto: true,
  onSuccess(result: ReachData) {
    // the server picks the first client when none was asked for
    if (result.selected) filters.project = result.selected;
    loadedFor = filtersKey();
  },
});

// what the shown report was loaded for, so taking the server's pick doesn't load it again
let loadedFor = "";
function filtersKey() {
  return [filters.project, filters.from_date, filters.to_date].join("|");
}

watch(filters, () => {
  router.replace({
    query: filters.project ? { project: filters.project } : {},
  });
  if (filtersKey() !== loadedFor) report.reload();
});

const data = computed(() => report.data as ReachData | undefined);
const selected = computed(() =>
  data.value?.connections.find((c) => c.project === data.value?.selected)
);

const clientOptions = computed(() =>
  (data.value?.connections ?? []).map((c) => ({
    label: [c.customer, c.facebook_page_name].filter(Boolean).join(" · "),
    value: c.project,
  }))
);

// -- the tiles: both platforms added up, the split underneath

function sum(field: keyof Totals, which: "current" | "previous" = "current") {
  return (data.value?.report?.platforms ?? []).reduce(
    (n, p) => n + (p[which]?.[field] ?? 0),
    0
  );
}

function split(value: (p: PlatformSummary) => string) {
  const platforms = data.value?.report?.platforms ?? [];
  return platforms.length > 1
    ? platforms.map((p) => `${__(p.platform)} ${value(p)}`).join(" · ")
    : undefined;
}

function change(field: keyof Totals) {
  const hasPrevious = data.value?.report?.platforms.some((p) => p.previous);
  const before = sum(field, "previous");
  if (!hasPrevious || !before) return { delta: null, deltaText: undefined };
  const pct = Math.round(((sum(field) - before) / before) * 100);
  return {
    delta: pct,
    deltaText: __("{0}% on the period before", `${pct > 0 ? "+" : ""}${pct}`),
  };
}

const followers = computed(() => {
  const platforms = data.value?.report?.platforms ?? [];
  const counted = platforms.filter((p) => p.followers != null);
  return counted.length
    ? counted.reduce((n, p) => n + (p.followers ?? 0), 0)
    : null;
});

const tiles = computed(() => {
  const net = sum("net_follows");
  const rate = data.value?.report?.engagement_rate;
  return [
    {
      label: __("Reach"),
      value: formatCount(sum("reach")),
      sub: split((p) => formatCount(p.current.reach)),
      icon: LucideRadio,
      ...change("reach"),
    },
    {
      label: __("Views"),
      value: formatCount(sum("views")),
      sub: split((p) => formatCount(p.current.views)),
      icon: LucideEye,
      ...change("views"),
    },
    {
      label: __("Engagements"),
      value: formatCount(sum("engagements")),
      sub:
        rate == null
          ? split((p) => formatCount(p.current.engagements))
          : __("{0}% of people reached by posts interacted", String(rate)),
      icon: LucideHeart,
      ...change("engagements"),
    },
    {
      label: __("Followers"),
      value: followers.value == null ? "—" : formatCount(followers.value),
      sub: split((p) => (p.followers == null ? "—" : formatCount(p.followers))),
      icon: LucideUsers,
      delta: net || null,
      deltaText: __(
        "{0} net new in this period",
        `${net > 0 ? "+" : ""}${formatCount(net)}`
      ),
    },
  ];
});

// -- the chart

const metric = ref<Metric>("reach");
const metricOptions = computed(() => [
  { label: __("Reach"), value: "reach" },
  { label: __("Views"), value: "views" },
  { label: __("Engagements"), value: "engagements" },
]);
const currentMetricLabel = computed(
  () => metricOptions.value.find((o) => o.value === metric.value)?.label ?? ""
);
const metricHint = computed(
  () =>
    ({
      reach: __("People who saw the content each day"),
      views: __("Times the content was played or shown each day"),
      engagements: __("Likes, comments, shares and saves each day"),
    }[metric.value])
);

const chartSeries = computed<WeekLine[]>(() =>
  (data.value?.report?.platforms ?? []).map((p) => ({
    name: __(p.platform),
    values: data.value?.report?.series[p.platform]?.[metric.value] ?? [],
    color: PLATFORM_COLORS[p.platform],
  }))
);
const hasDaily = computed(() =>
  chartSeries.value.some((line) => line.values.some((v) => v > 0))
);

// -- posts by kind

const topKindReach = computed(() =>
  Math.max(0, ...(data.value?.report?.kinds ?? []).map((k) => k.average_reach))
);
function kindWidth(reach: number) {
  return topKindReach.value
    ? Math.round((reach / topKindReach.value) * 100)
    : 0;
}

// thumbnails are Meta's links, which expire; an icon stands in for a broken one
const brokenImages = reactive(new Set<string>());

// -- actions

const syncing = ref(false);
async function syncNow() {
  if (!selected.value) return;
  syncing.value = true;
  try {
    await call("helpdesk.api.meta_insights.sync_now", {
      project: selected.value.project,
    });
    toast.success(
      __("Syncing the last 90 days from Meta. Reload in a few minutes.")
    );
  } catch (e) {
    toast.error(errorText(e, __("Couldn't start the sync.")));
  } finally {
    syncing.value = false;
  }
}

function downloadPdf() {
  if (!selected.value) return;
  const params = new URLSearchParams({
    project: selected.value.project,
    from_date: filters.from_date,
    to_date: filters.to_date,
  });
  window.open(
    `/api/method/helpdesk.api.meta_insights.export_pdf?${params}`,
    "_blank"
  );
}
</script>

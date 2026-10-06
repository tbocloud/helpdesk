<template>
  <div class="flex flex-col gap-4">
    <p
      v-if="!data.team.length"
      class="rounded-xl border border-dashed border-outline-gray-3 px-4 py-14 text-center text-p-sm text-ink-gray-5"
    >
      {{ __("Nobody had content posts due in this period.") }}
    </p>

    <template v-else>
      <!-- team ranking -->
      <section :aria-label="__('Team ranking')">
        <header class="mb-2 flex items-baseline justify-between gap-2">
          <h2 class="text-base font-semibold text-ink-gray-9">
            {{ __("Team, ranked by average post score") }}
          </h2>
          <span
            class="flex items-center gap-1.5 text-xs text-ink-gray-5"
            :title="__('The average post score of everyone shown')"
          >
            <span class="h-3 w-px bg-ink-gray-7" aria-hidden="true" />
            {{ __("Team average") }}
            <b class="font-semibold tabular-nums text-ink-gray-8">{{
              scoreText(data.team_summary.avg_score)
            }}</b>
          </span>
        </header>
        <div class="flex gap-3 overflow-x-auto pb-1">
          <button
            v-for="row in data.team"
            :key="row.employee"
            type="button"
            class="flex w-60 shrink-0 flex-col gap-2 rounded-xl border bg-surface-base p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
            :class="
              row.employee === detail?.employee
                ? 'border-brand ring-1 ring-brand'
                : 'border-outline-gray-2 hover:border-outline-gray-4'
            "
            :aria-pressed="row.employee === detail?.employee"
            @click="emit('select', row.employee)"
          >
            <div class="flex items-start gap-2.5">
              <PersonBadge
                :image="row.image"
                :name="row.employee_name"
                :tone="toneOf(row.rank)"
              />
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-semibold text-ink-gray-9">
                  {{ row.employee_name }}
                </div>
                <div class="text-xs text-ink-gray-5">
                  {{ postsLine(row) }}
                </div>
              </div>
              <span
                class="rounded-md px-1.5 py-0.5 font-mono text-xs font-semibold tabular-nums"
                :class="rankClass(row.rank)"
                >#{{ row.rank }}</span
              >
            </div>
            <div class="flex items-baseline justify-between text-xs">
              <span class="text-ink-gray-6">{{ __("Avg. post score") }}</span>
              <b class="text-sm font-semibold tabular-nums text-brand-ink">{{
                scoreText(row.avg_score)
              }}</b>
            </div>
            <ScoreBar
              :value="row.avg_score"
              :marker="data.team_summary.avg_score"
            />
            <div class="mt-1 grid grid-cols-2 gap-2 text-xs">
              <div>
                <div class="text-ink-gray-5">{{ __("Published") }}</div>
                <div class="font-semibold tabular-nums text-ink-gray-8">
                  {{ row.published }} / {{ row.posts - row.upcoming }}
                </div>
              </div>
              <div>
                <div class="text-ink-gray-5">{{ __("On time") }}</div>
                <div
                  class="font-semibold tabular-nums"
                  :class="onTimeClass(row.on_time_pct)"
                >
                  {{ pctText(row.on_time_pct) }}
                </div>
              </div>
            </div>
          </button>
        </div>
      </section>

      <!-- the selected person -->
      <section
        v-if="detail"
        class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
        :aria-label="detail.employee_name"
      >
        <header class="mb-4 flex flex-wrap items-center gap-3">
          <PersonBadge
            :image="detail.image"
            :name="detail.employee_name"
            tone="solid"
            large
          />
          <div class="min-w-0 flex-1">
            <h2 class="text-xl font-semibold text-ink-gray-9">
              {{ detail.employee_name }}
            </h2>
            <p class="text-p-sm text-ink-gray-5">
              {{
                __(
                  "On {0} posts in {1}",
                  String(detail.summary.posts),
                  periodLabel
                )
              }}
            </p>
          </div>
          <span
            v-if="detail.rank"
            class="rounded-md bg-warning-soft px-2.5 py-1 text-xs font-semibold text-warning"
          >
            {{
              __(
                "Ranked #{0} of {1} by avg. post score",
                String(detail.rank),
                String(detail.ranked_of)
              )
            }}
          </span>
        </header>
        <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Tile
            tone="brand"
            :label="__('Avg. post score')"
            :value="scoreText(s.avg_score)"
            :sub="vsTeam"
            :sub-tone="vsTeamTone"
          />
          <Tile
            tone="info"
            :label="__('Posts published')"
            :value="String(s.published)"
            :sub="
              s.missed
                ? s.missed === 1
                  ? __('1 missed slot')
                  : __('{0} missed slots', String(s.missed))
                : __('no missed slots')
            "
            :sub-tone="s.missed ? 'danger' : 'muted'"
          />
          <Tile
            tone="teal"
            :label="__('On-time rate')"
            :value="pctText(s.on_time_pct)"
            :sub="__('team {0}', pctText(t.on_time_pct))"
          />
          <Tile
            tone="warning"
            :label="__('Client change requests')"
            :value="String(s.change_requests)"
            :sub="perPost(s.change_requests, s.posts)"
          />
          <Tile
            tone="pink"
            :label="__('Postponed')"
            :value="String(s.postponed)"
            :sub="__('of {0} posts', String(s.posts))"
          />
          <Tile
            tone="success"
            :label="__('Best channel')"
            :value="bestChannel?.channel || '—'"
            :sub="
              bestChannel
                ? __('avg. score {0}', scoreText(bestChannel.avg_score))
                : __('nothing scored yet')
            "
          />
        </div>
      </section>

      <div v-if="detail" class="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <!-- their posts -->
        <section
          class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base xl:col-span-2"
        >
          <header class="flex flex-wrap items-start justify-between gap-2 p-4">
            <div>
              <h3 class="text-base font-semibold text-ink-gray-9">
                {{
                  __(
                    "{0}'s posts ({1})",
                    firstName,
                    String(detail.posts.length)
                  )
                }}
              </h3>
              <p class="text-p-sm text-ink-gray-5">
                {{ __("How each post they worked on was delivered") }}
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
            <table class="w-full min-w-[720px] text-left text-sm">
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
                    {{ __("Role") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Score") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
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
                  <td
                    class="whitespace-nowrap px-4 py-2.5 text-xs text-ink-gray-6"
                    :title="p.roles.map((r: string) => __(ROLE_LABEL[r])).join(', ')"
                  >
                    {{ roleText(p.roles) }}
                  </td>
                  <td class="px-4 py-2.5">
                    <div class="flex items-center gap-2">
                      <b
                        class="w-7 text-right text-sm font-semibold tabular-nums"
                        :class="scoreClass(p.score)"
                        >{{ scoreText(p.score) }}</b
                      >
                      <div class="w-24">
                        <ScoreBar :value="p.score" :tone="scoreTone(p.score)" />
                      </div>
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
          <div
            v-if="missedDates.length"
            class="m-4 rounded-lg border border-dashed border-warning bg-warning-soft px-3 py-2 text-p-sm text-warning"
          >
            <b class="font-semibold">{{ __("Missed slots:") }}</b>
            {{ missedDates.join(", ") }}
          </div>
        </section>

        <div class="flex flex-col gap-4">
          <!-- compared with the team -->
          <section
            class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
          >
            <h3 class="text-base font-semibold text-ink-gray-9">
              {{ __("Compared with the team") }}
            </h3>
            <ul
              class="mb-3 mt-1 flex gap-3 text-xs text-ink-gray-6"
              :aria-label="__('Legend')"
            >
              <li class="flex items-center gap-1.5">
                <span class="size-2.5 rounded-sm bg-brand" aria-hidden="true" />
                {{ firstName }}
              </li>
              <li class="flex items-center gap-1.5">
                <span
                  class="size-2.5 rounded-sm bg-surface-gray-5"
                  aria-hidden="true"
                />
                {{ __("Team") }}
              </li>
            </ul>
            <div class="flex flex-col gap-4">
              <div v-for="m in comparisons" :key="m.label">
                <div class="mb-1 text-sm text-ink-gray-8">{{ m.label }}</div>
                <div class="flex flex-col gap-1">
                  <CompareBar
                    :value="m.person"
                    :max="m.max"
                    :text="m.format(m.person)"
                    tone="brand"
                    :label="`${firstName}: ${m.format(m.person)}`"
                  />
                  <CompareBar
                    :value="m.team"
                    :max="m.max"
                    :text="m.format(m.team)"
                    tone="team"
                    :label="`${__('Team')}: ${m.format(m.team)}`"
                  />
                </div>
                <p v-if="m.hint" class="mt-1 text-xs text-ink-gray-5">
                  {{ m.hint }}
                </p>
              </div>
            </div>
          </section>

          <!-- channel mix -->
          <section
            class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
          >
            <h3 class="text-base font-semibold text-ink-gray-9">
              {{ __("Channel mix") }}
            </h3>
            <p class="mb-3 text-p-sm text-ink-gray-5">
              {{ __("Posts per channel, with average score") }}
            </p>
            <ul class="flex flex-col gap-2.5" :aria-label="__('Channel mix')">
              <li
                v-for="c in detail.channels"
                :key="c.channel"
                class="grid grid-cols-[6rem_1fr_1.5rem_2.5rem] items-center gap-2 text-sm"
              >
                <span
                  class="truncate font-medium"
                  :style="{ color: channelColor(c.channel) }"
                  >{{ c.channel }}</span
                >
                <div class="h-2 rounded-full bg-surface-gray-2">
                  <div
                    class="h-full rounded-full"
                    :style="{
                      width: `${(c.posts / maxChannelPosts) * 100}%`,
                      background: channelColor(c.channel),
                    }"
                  />
                </div>
                <span
                  class="text-right font-mono text-xs tabular-nums text-ink-gray-6"
                  >{{ c.posts }}</span
                >
                <span
                  class="rounded px-1.5 py-0.5 text-center font-mono text-xs font-semibold tabular-nums"
                  :class="
                    c.channel === bestChannel?.channel
                      ? 'bg-success-soft text-success'
                      : 'bg-brand-soft text-brand-ink'
                  "
                  >{{ scoreText(c.avg_score) }}</span
                >
              </li>
            </ul>
          </section>
        </div>
      </div>

      <p class="text-xs text-ink-gray-5">
        {{
          __(
            "Post score: published on time 100, late 60, missed 0, minus 10 for each client change request. Posts not due yet are listed but not scored."
          )
        }}
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Avatar, dayjs } from "frappe-ui";
import { channelColor, type Tone } from "../performanceMeta";
import { computed, h, ref } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideHourglass from "~icons/lucide/hourglass";

const props = defineProps<{ data: any; periodLabel: string }>();
const emit = defineEmits<{ (e: "select", employee: string): void }>();

const ROLE_LABEL: Record<string, string> = {
  writer: "Writer",
  designer: "Designer",
  marketer: "Digital marketer",
  video_editor: "Video editor",
};
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
  { key: "best", label: __("Best first") },
  { key: "date", label: __("By date") },
] as const;

// --- colours (always alongside a number or label, never on their own) ---
type CardTone = "brand" | "pink" | "info" | "teal" | "warning";
const PERSON_TONES: CardTone[] = ["brand", "pink", "info", "teal", "warning"];
const toneOf = (rank: number) => PERSON_TONES[(rank - 1) % PERSON_TONES.length];

function rankClass(rank: number) {
  if (rank === 1) return "bg-warning-soft text-warning";
  if (rank === 2) return "bg-surface-gray-2 text-ink-gray-7";
  if (rank === 3) return "bg-pink-soft text-pink";
  return "bg-surface-gray-2 text-ink-gray-6";
}

function onTimeClass(pct: number | null) {
  if (pct == null) return "text-ink-gray-5";
  if (pct >= 95) return "text-success";
  if (pct >= 80) return "text-brand-ink";
  return "text-danger";
}

const scoreTone = (score: number | null): Tone =>
  score != null && score >= 90 ? "success" : "brand";
const scoreClass = (score: number | null) =>
  score == null
    ? "text-ink-gray-5"
    : score >= 90
    ? "text-success"
    : "text-brand-ink";


const sort = ref<"best" | "date">("best");
const detail = computed(() => props.data.detail);
const s = computed(() => detail.value.summary);
const t = computed(() => props.data.team_summary);
const firstName = computed(
  () => detail.value?.employee_name.trim().split(/\s+/)[0] || ""
);

// all three roles in full would wrap the row to several lines
const roleText = (roles: string[]) =>
  roles.length === Object.keys(ROLE_LABEL).length
    ? __("All roles")
    : roles.map((r) => __(ROLE_LABEL[r])).join(", ");

const scoreText = (v: number | null) => (v == null ? "—" : String(v));
const pctText = (v: number | null) => (v == null ? "—" : `${v}%`);
const perPost = (n: number, posts: number) =>
  posts ? __("{0} per post", (n / posts).toFixed(1)) : "";

function postsLine(row: any) {
  const posts =
    row.posts === 1 ? __("1 post") : __("{0} posts", String(row.posts));
  return row.missed
    ? `${posts} · ${__("{0} missed", String(row.missed))}`
    : posts;
}

const vsTeam = computed(() => {
  if (s.value.avg_score == null || t.value.avg_score == null) return "";
  const diff = s.value.avg_score - t.value.avg_score;
  if (diff === 0) return __("same as team avg.");
  return __("{0} vs. team avg.", `${diff > 0 ? "+" : ""}${diff}`);
});
const vsTeamTone = computed(() => {
  if (s.value.avg_score == null || t.value.avg_score == null) return "muted";
  return s.value.avg_score >= t.value.avg_score ? "success" : "danger";
});

const bestChannel = computed(
  () =>
    [...(detail.value?.channels ?? [])]
      .filter((c: any) => c.avg_score != null)
      .sort(
        (a: any, b: any) => b.avg_score - a.avg_score || b.posts - a.posts
      )[0]
);
const maxChannelPosts = computed(() =>
  Math.max(1, ...(detail.value?.channels ?? []).map((c: any) => c.posts))
);

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

const missedDates = computed(() =>
  (detail.value?.posts ?? [])
    .filter((p: any) => p.timing === "Missed")
    .sort((a: any, b: any) => (a.publish_on < b.publish_on ? -1 : 1))
    .map((p: any) => dayjs(p.publish_on).format("ddd D MMM"))
);

const comparisons = computed(() => {
  const changeRate = (sum: any) =>
    sum.posts ? Math.round((sum.change_requests / sum.posts) * 10) / 10 : null;
  const personChanges = changeRate(s.value);
  const teamChanges = changeRate(t.value);
  return [
    {
      label: __("Avg. post score"),
      person: s.value.avg_score,
      team: t.value.avg_score,
      max: 100,
      format: scoreText,
    },
    {
      label: __("On-time rate"),
      person: s.value.on_time_pct,
      team: t.value.on_time_pct,
      max: 100,
      format: pctText,
    },
    {
      label: __("Client change requests per post"),
      person: personChanges,
      team: teamChanges,
      max: Math.max(1, personChanges ?? 0, teamChanges ?? 0),
      format: (v: number | null) => (v == null ? "—" : String(v)),
      hint: __("Lower is better"),
    },
  ];
});

// small presentational pieces kept local to this view
const ScoreBar = (p: {
  value: number | null;
  marker?: number | null;
  tone?: Tone;
}) =>
  h("div", { class: "relative h-2 rounded-full bg-surface-gray-2" }, [
    h("div", {
      class: `h-full rounded-full ${
        p.tone === "success" ? "bg-success" : "bg-brand"
      }`,
      style: { width: `${Math.max(0, Math.min(p.value ?? 0, 100))}%` },
    }),
    p.marker != null
      ? h("span", {
          class: "absolute -top-1 h-4 w-0.5 rounded bg-ink-gray-8",
          style: { left: `calc(${p.marker}% - 1px)` },
          title: __("Team average {0}", String(p.marker)),
          "aria-hidden": "true",
        })
      : null,
  ]);
ScoreBar.props = ["value", "marker", "tone"];

const TONE_CLASSES: Record<string, { soft: string; ink: string }> = {
  brand: { soft: "bg-brand-soft", ink: "text-brand-ink" },
  pink: { soft: "bg-pink-soft", ink: "text-pink" },
  info: { soft: "bg-info-soft", ink: "text-info" },
  teal: { soft: "bg-teal-soft", ink: "text-teal" },
  warning: { soft: "bg-warning-soft", ink: "text-warning" },
  success: { soft: "bg-success-soft", ink: "text-success" },
};

/** Photo when there is one, else coloured initials. */
const PersonBadge = (p: {
  image?: string;
  name: string;
  tone: CardTone | "solid";
  large?: boolean;
}) => {
  if (p.image)
    return h(Avatar, {
      size: p.large ? "3xl" : "lg",
      image: p.image,
      label: p.name,
    });
  const initials = p.name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  const colours =
    p.tone === "solid"
      ? "bg-brand text-brand-on"
      : `${TONE_CLASSES[p.tone].soft} ${TONE_CLASSES[p.tone].ink}`;
  return h(
    "span",
    {
      class: `inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${colours} ${
        p.large ? "size-12 text-base" : "size-8 text-xs"
      }`,
      "aria-hidden": "true",
    },
    initials
  );
};
PersonBadge.props = ["image", "name", "tone", "large"];

const CompareBar = (p: {
  value: number | null;
  max: number;
  text: string;
  tone: "brand" | "team";
  label: string;
}) =>
  h(
    "div",
    { class: "flex items-center gap-2", role: "img", "aria-label": p.label },
    [
      h("div", { class: "h-2 flex-1 rounded-full bg-surface-gray-2" }, [
        h("div", {
          class: `h-full rounded-full ${
            p.tone === "brand" ? "bg-brand" : "bg-surface-gray-5"
          }`,
          style: {
            width: `${Math.max(
              0,
              Math.min(((p.value ?? 0) / p.max) * 100, 100)
            )}%`,
          },
        }),
      ]),
      h(
        "span",
        {
          class: `w-12 text-right text-xs tabular-nums ${
            p.tone === "brand"
              ? "font-semibold text-ink-gray-9"
              : "text-ink-gray-6"
          }`,
        },
        p.text
      ),
    ]
  );
CompareBar.props = ["value", "max", "text", "tone", "label"];

const Tile = (p: {
  label: string;
  value: string;
  sub?: string;
  subTone?: "muted" | "success" | "danger";
  tone?: string;
}) =>
  h(
    "div",
    {
      class: `rounded-lg p-3 ${
        p.tone ? TONE_CLASSES[p.tone].soft : "border border-outline-gray-2"
      }`,
    },
    [
      h("div", { class: "text-xs text-ink-gray-6" }, p.label),
      h(
        "div",
        {
          class: `mt-0.5 truncate text-2xl font-semibold tabular-nums ${
            p.tone ? TONE_CLASSES[p.tone].ink : "text-ink-gray-9"
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
    ]
  );
Tile.props = ["label", "value", "sub", "subTone", "tone"];
</script>

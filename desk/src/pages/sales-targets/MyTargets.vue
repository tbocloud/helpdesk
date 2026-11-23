<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Your sales targets')"
      :subtitle="__('What your Sales Head set for you, month by month.')"
    >
      <template #right-header>
        <label class="flex items-center gap-3">
          <span class="text-sm text-ink-gray-6">{{ __("Month") }}</span>
          <FormControl
            :model-value="month"
            type="select"
            size="md"
            class="w-44"
            :options="monthChoices"
            @update:model-value="pickMonth(String($event))"
          />
        </label>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="mine.error && !mine.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :error="!isRefusal"
          :icon="isRefusal ? LucideLock : LucideCircleAlert"
          :title="
            isRefusal
              ? __('Sales targets aren\'t open to you')
              : __('Couldn\'t load your targets')
          "
          :message="
            errorText(mine.error, __('Check your connection and try again.'))
          "
        >
          <Button
            v-if="!isRefusal"
            :label="__('Try again')"
            @click="mine.reload()"
          />
        </TaskyState>

        <div
          v-else-if="!mine.data || mine.loading"
          class="h-72 animate-pulse rounded-xl bg-surface-gray-3"
          aria-busy="true"
          :aria-label="__('Loading')"
        />

        <template v-else-if="target">
          <!-- the month at a glance: reached so far, where each target stands, who set them -->
          <section
            class="flex flex-wrap items-center gap-x-8 gap-y-4 rounded-xl bg-hero px-5 py-5 text-hero-ink md:px-7"
            :aria-labelledby="heading"
          >
            <div class="flex min-w-0 items-center gap-4">
              <div
                class="relative size-[72px] shrink-0"
                role="img"
                :aria-label="
                  overall?.percent != null
                    ? __('{0}% of the month reached', String(overall.percent))
                    : __('Nothing counted yet')
                "
              >
                <svg viewBox="0 0 72 72" class="size-full -rotate-90">
                  <circle
                    cx="36"
                    cy="36"
                    r="30"
                    fill="none"
                    stroke-width="7"
                    class="stroke-hero-track"
                  />
                  <circle
                    v-if="overall?.percent"
                    cx="36"
                    cy="36"
                    r="30"
                    fill="none"
                    stroke-width="7"
                    stroke-linecap="round"
                    pathLength="100"
                    :stroke-dasharray="`${Math.min(overall.percent, 100)} 100`"
                    class="stroke-hero-fill"
                  />
                </svg>
                <span
                  class="absolute inset-0 grid place-items-center text-base font-bold tabular-nums"
                  aria-hidden="true"
                  >{{
                    overall?.percent != null ? `${overall.percent}%` : "—"
                  }}</span
                >
              </div>
              <div class="flex min-w-0 flex-col">
                <span class="text-sm text-hero-muted">{{
                  __("Your targets for")
                }}</span>
                <h2
                  :id="heading"
                  class="text-2xl font-bold leading-tight tracking-[-0.02em]"
                >
                  {{ monthTitle(month) }}
                </h2>
                <span class="text-sm text-hero-muted tabular-nums">{{
                  summary
                }}</span>
              </div>
            </div>

            <ul
              v-if="chips.length"
              class="flex flex-1 flex-wrap gap-2"
              :aria-label="__('Where your targets stand')"
            >
              <li
                v-for="chip in chips"
                :key="chip.label"
                class="inline-flex h-8 items-center rounded-full px-3.5 text-sm font-semibold tabular-nums"
                :class="chip.class"
              >
                {{ chip.label }}
              </li>
            </ul>
            <div v-else class="flex-1" />

            <div class="flex min-w-0 items-center gap-3">
              <PersonAvatar :name="setBy" size="lg" />
              <div class="flex min-w-0 flex-col">
                <span class="text-xs text-hero-muted">{{ __("Set by") }}</span>
                <span class="truncate text-sm font-semibold">{{ setBy }}</span>
                <span class="text-xs text-hero-muted tabular-nums">{{
                  dayjs(target.modified).format("D MMM YYYY, h:mm a")
                }}</span>
              </div>
            </div>
          </section>

          <!-- the targets counted from their leads -->
          <section
            v-if="figures.length"
            class="flex flex-col gap-3"
            :aria-labelledby="figuresHeading"
          >
            <div class="flex flex-wrap items-center justify-between gap-3">
              <h2
                :id="figuresHeading"
                class="flex items-center gap-2 text-lg font-semibold text-ink-gray-9"
              >
                {{ __("Counted from your leads") }}
                <span
                  class="rounded-full bg-surface-gray-3 px-2 py-px text-xs font-semibold text-ink-gray-7 tabular-nums"
                  >{{ figures.length }}</span
                >
              </h2>
              <div class="flex flex-wrap items-center gap-4">
                <span
                  v-if="pace.state === 'running'"
                  class="flex items-center gap-2 text-sm text-ink-gray-6"
                >
                  <span
                    class="h-3.5 w-0.5 rounded-full bg-surface-gray-9"
                    aria-hidden="true"
                  />
                  {{ __("Where you should be by today") }}
                </span>
                <TabButtons
                  v-model="standing"
                  :aria-label="__('Show')"
                  :options="standingOptions"
                >
                  <template #suffix="{ button }">
                    <span
                      class="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-surface-gray-3 px-1 text-2xs font-semibold text-ink-gray-7 tabular-nums"
                      >{{ standingCount(String(button.value)) }}</span
                    >
                  </template>
                </TabButtons>
              </div>
            </div>
            <div
              v-if="shownFigures.length"
              class="grid grid-cols-1 items-start gap-4 sm:grid-cols-2 xl:grid-cols-4"
            >
              <TargetMeter
                v-for="row in shownFigures"
                :key="row.criterion.criterion"
                :criterion="row.criterion"
                :currency="mine.data.currency"
                :progress="progress.data ?? null"
                :owner="auth.userName"
                :link="
                  auth.canUseLeads && progress.data
                    ? leadsLink(row.criterion, progress.data, auth.userId)
                    : null
                "
              />
            </div>
            <p
              v-else
              class="rounded-xl border border-dashed border-outline-gray-3 px-4 py-6 text-center text-sm text-ink-gray-6"
            >
              {{ __("None of your targets is here right now.") }}
            </p>
          </section>

          <div
            v-if="tasks.length || focus.length"
            class="grid grid-cols-1 items-start gap-4"
            :class="
              tasks.length &&
              focus.length &&
              'lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]'
            "
          >
            <!-- KPIs: written targets they tick off, a Sales Head confirms -->
            <section
              v-if="tasks.length"
              class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="tasksHeading"
            >
              <div class="border-b border-outline-gray-1 px-4 py-3.5 md:px-5">
                <h2
                  :id="tasksHeading"
                  class="flex items-center gap-2 text-lg font-semibold text-ink-gray-9"
                >
                  {{ __("Tasks to mark done") }}
                  <span
                    class="rounded-full bg-surface-gray-3 px-2 py-px text-xs font-semibold text-ink-gray-7 tabular-nums"
                    >{{ toMarkDone }}</span
                  >
                </h2>
                <p class="text-sm text-ink-gray-6">
                  {{
                    __(
                      "Each counts once you mark it done and your Sales Head confirms it. Until then it counts 0%."
                    )
                  }}
                </p>
              </div>
              <ul class="divide-y divide-outline-gray-1">
                <li
                  v-for="criterion in tasks"
                  :key="criterion.criterion"
                  class="flex flex-wrap items-center gap-3 px-4 py-3.5 md:px-5"
                >
                  <span
                    class="grid size-8 shrink-0 place-items-center rounded-md"
                    :class="VALUE_TYPE_LOOK.Text.tile"
                    aria-hidden="true"
                  >
                    <LucideFileText class="size-4" />
                  </span>
                  <div class="flex min-w-[10rem] flex-1 flex-col">
                    <span class="text-base font-semibold text-ink-gray-9">{{
                      criterion.criterion
                    }}</span>
                    <span
                      class="whitespace-pre-line break-words text-sm text-ink-gray-6"
                      >{{ criterion.target }}</span
                    >
                    <span
                      v-if="criterion.kpi_note"
                      class="mt-1 whitespace-pre-line break-words text-xs text-ink-gray-7"
                    >
                      {{ __("You noted: {0}", criterion.kpi_note) }}
                    </span>
                  </div>
                  <KpiStatus
                    compact
                    class="ml-auto"
                    :criterion="criterion"
                    :month="month"
                    mode="person"
                    @changed="mine.data.target = $event"
                  />
                </li>
              </ul>
            </section>

            <!-- information only (Industry, Location): where to look, nothing to tick off -->
            <section
              v-if="focus.length"
              class="min-w-0 rounded-xl border border-outline-gray-2 bg-surface-base p-4 md:px-5"
              :aria-labelledby="focusHeading"
            >
              <h2
                :id="focusHeading"
                class="text-base font-semibold text-ink-gray-9"
              >
                {{ __("Where to focus") }}
              </h2>
              <dl class="mt-2 flex flex-col gap-2">
                <div
                  v-for="criterion in focus"
                  :key="criterion.criterion"
                  class="flex flex-wrap gap-x-2 text-sm"
                >
                  <dt class="font-medium text-ink-gray-8">
                    {{ criterion.criterion }}
                  </dt>
                  <dd class="whitespace-pre-line break-words text-ink-gray-6">
                    {{ criterion.target }}
                  </dd>
                </div>
              </dl>
            </section>
          </div>

          <p class="flex items-center gap-2 text-sm text-ink-gray-6">
            <LucideInfo class="size-4 shrink-0" aria-hidden="true" />
            {{
              setBy
                ? __(
                    "Questions about a target? Ask {0}, your Sales Head.",
                    setBy
                  )
                : __("Questions about a target? Ask your Sales Head.")
            }}
          </p>
        </template>

        <!-- no targets for the month: what will come, a nudge to the head, where to go meanwhile -->
        <template v-else>
          <section
            class="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border border-outline-gray-2 bg-surface-base px-5 py-4"
            :aria-labelledby="heading"
          >
            <span
              class="grid size-14 shrink-0 place-items-center rounded-full border-[3px] border-dashed border-outline-gray-3 text-base font-bold text-ink-gray-7 tabular-nums"
              aria-hidden="true"
              >0</span
            >
            <div class="flex min-w-0 flex-1 flex-col">
              <span class="text-sm text-ink-gray-6">{{
                __("Your targets for")
              }}</span>
              <h2
                :id="heading"
                class="text-xl font-bold leading-tight text-ink-gray-9"
              >
                {{ monthTitle(month) }}
              </h2>
              <span class="text-sm text-ink-gray-6 tabular-nums">{{
                summary
              }}</span>
            </div>
            <Button
              v-if="latestOther"
              variant="ghost"
              :label="__('See {0}', monthTitle(latestOther))"
              @click="pickMonth(latestOther)"
            />
            <span
              class="inline-flex h-8 items-center gap-1.5 rounded-full bg-surface-gray-2 px-3 text-sm font-medium text-ink-gray-7"
            >
              <LucideCircleDashed class="size-3.5" aria-hidden="true" />
              {{ __("Not set yet") }}
            </span>
          </section>

          <section
            class="flex flex-col items-center gap-4 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-12 text-center"
            :aria-labelledby="emptyHeading"
          >
            <svg
              viewBox="0 0 120 120"
              class="size-28 text-brand"
              aria-hidden="true"
            >
              <circle cx="60" cy="60" r="58" class="fill-brand-soft" />
              <circle
                cx="60"
                cy="60"
                r="40"
                fill="none"
                stroke="currentColor"
                stroke-width="3"
                stroke-dasharray="6 7"
                stroke-linecap="round"
                opacity="0.35"
              />
              <circle
                cx="60"
                cy="60"
                r="24"
                fill="none"
                stroke="currentColor"
                stroke-width="3"
                stroke-dasharray="6 7"
                stroke-linecap="round"
                opacity="0.6"
              />
              <path
                d="M60 60 L88 30"
                stroke="currentColor"
                stroke-width="5"
                stroke-linecap="round"
              />
              <path d="M80 26 L95 23 L92 38 Z" fill="currentColor" />
              <circle cx="60" cy="60" r="9" fill="currentColor" />
            </svg>
            <h2
              :id="emptyHeading"
              class="text-2xl font-bold tracking-[-0.01em] text-ink-gray-9"
            >
              {{ __("No targets set for {0} yet", monthTitle(month)) }}
            </h2>
            <p class="max-w-xl text-p-base text-ink-gray-6">
              {{
                __(
                  "Your Sales Head hasn't given you targets for this month. When they do, each one shows here and your progress is counted from your leads automatically."
                )
              }}
            </p>
            <div class="mt-2 flex flex-wrap justify-center gap-3">
              <Button
                size="lg"
                variant="solid"
                :label="
                  asked ? __('Sales Head reminded') : __('Ask my Sales Head')
                "
                :loading="ask.loading"
                :disabled="asked"
                @click="ask.submit({ month })"
              >
                <template #prefix>
                  <LucideCheck v-if="asked" class="size-4" />
                  <LucideSend v-else class="size-4" />
                </template>
              </Button>
              <Button
                v-if="auth.canUseLeads"
                size="lg"
                :label="__('Go to my leads')"
                @click="router.push({ name: 'Leads', query: { view: 'mine' } })"
              />
            </div>
            <ErrorMessage
              v-if="ask.error"
              :message="
                errorText(ask.error, __('Couldn\'t send that. Try again.'))
              "
              role="alert"
            />
            <p v-else class="text-sm text-ink-gray-6" aria-live="polite">
              {{
                asked
                  ? __(
                      "Your Sales Head knows. Your targets show here once they set them."
                    )
                  : __(
                      "Sends your Sales Head a reminder to set your {0} targets.",
                      dayjs(`${month}-01`).format("MMMM")
                    )
              }}
            </p>
          </section>

          <div
            class="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]"
          >
            <section
              class="flex min-w-0 flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-5"
              :aria-labelledby="howHeading"
            >
              <h2
                :id="howHeading"
                class="text-lg font-semibold text-ink-gray-9"
              >
                {{ __("How your targets will work") }}
              </h2>
              <ol class="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
                <li v-for="(step, i) in HOW" :key="i" class="flex gap-3">
                  <span
                    class="grid size-8 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-semibold text-brand-ink tabular-nums"
                    aria-hidden="true"
                    >{{ i + 1 }}</span
                  >
                  <span class="flex min-w-0 flex-col">
                    <span class="text-base font-semibold text-ink-gray-9">{{
                      step.title
                    }}</span>
                    <span class="text-sm text-ink-gray-6">{{ step.text }}</span>
                  </span>
                </li>
              </ol>
              <div
                class="grid grid-cols-1 gap-3 sm:grid-cols-3"
                aria-hidden="true"
              >
                <div
                  v-for="n in 3"
                  :key="n"
                  class="flex flex-col gap-2.5 rounded-xl border border-dashed border-outline-gray-3 p-4"
                >
                  <span class="h-2.5 w-24 rounded-full bg-surface-gray-3" />
                  <span class="h-4 w-16 rounded-full bg-surface-gray-3" />
                  <span class="h-1.5 w-full rounded-full bg-surface-gray-2" />
                </div>
              </div>
              <p class="text-center text-sm text-ink-gray-6">
                {{ __("Your target cards will appear here.") }}
              </p>
            </section>

            <section
              v-if="shortcuts.length"
              class="flex min-w-0 flex-col gap-3"
              :aria-labelledby="meanwhileHeading"
            >
              <h2
                :id="meanwhileHeading"
                class="text-lg font-semibold text-ink-gray-9"
              >
                {{ __("Meanwhile, keep going") }}
              </h2>
              <RouterLink
                v-for="shortcut in shortcuts"
                :key="shortcut.title"
                :to="shortcut.to"
                class="flex items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >
                <span
                  class="grid size-10 shrink-0 place-items-center rounded-lg"
                  :class="shortcut.tile"
                  aria-hidden="true"
                >
                  <component :is="shortcut.icon" class="size-5" />
                </span>
                <span class="flex min-w-0 flex-1 flex-col">
                  <span class="text-base font-semibold text-ink-gray-9">{{
                    shortcut.title
                  }}</span>
                  <span class="text-sm text-ink-gray-6">{{
                    shortcut.text
                  }}</span>
                </span>
                <LucideChevronRight
                  class="size-4 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                />
              </RouterLink>
            </section>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { useAuthStore } from "@/stores/auth";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  ErrorMessage,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { batchesOn } from "@/pages/leads/callBatches";
import { leadOptions } from "@/pages/leads/leads";
import LucideCheck from "~icons/lucide/check";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideGauge from "~icons/lucide/gauge";
import LucidePhone from "~icons/lucide/phone";
import LucideSend from "~icons/lucide/send";
import LucideStar from "~icons/lucide/star";
import LucideFileText from "~icons/lucide/file-text";
import LucideInfo from "~icons/lucide/info";
import LucideLock from "~icons/lucide/lock";
import KpiStatus from "./KpiStatus.vue";
import {
  isKpi,
  leadsLink,
  monthPace,
  monthTitle,
  monthValue,
  overallOf,
  progressOf,
  VALUE_TYPE_LOOK,
  type MyTargets,
  type Progress,
  type Standing,
} from "./salesTargets";
import TargetMeter from "./TargetMeter.vue";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const heading = useId();
const figuresHeading = useId();
const tasksHeading = useId();
const focusHeading = useId();
const emptyHeading = useId();
const howHeading = useId();
const meanwhileHeading = useId();

// the month is in the URL, so a link or a reload opens the same one
const month = computed(() =>
  /^\d{4}-\d{2}$/.test(String(route.query.month || ""))
    ? String(route.query.month)
    : monthValue()
);
function pickMonth(value: string) {
  router.replace({ query: { ...route.query, month: value } });
}
const mine = createResource<MyTargets>({
  url: "helpdesk.api.sales_targets.get_my_targets",
  makeParams: () => ({ month: month.value }),
  auto: true,
});
watch(month, () => mine.reload());

const isRefusal = computed(
  () => mine.error?.exc_type === "SalesTargetsForbiddenError"
);

const target = computed(() => mine.data?.target ?? null);

// how far they are, counted from their leads; read once the month's targets are in
const progress = createResource<Progress>({
  url: "helpdesk.api.sales_targets.get_progress",
  makeParams: () => ({ month: month.value }),
});
watch(
  () => target.value?.modified,
  (modified) => {
    progress.reset();
    if (modified) progress.reload();
  },
  { immediate: true }
);
const overall = computed(() =>
  target.value && progress.data?.state === "counted"
    ? overallOf(target.value, progress.data, mine.data!.currency)
    : null
);
const setBy = computed(() =>
  target.value ? target.value.assigned_by_name || target.value.assigned_by : ""
);
const pace = computed(() => monthPace(month.value));

// what was assigned, in the head's order: the page shows nothing else
const assigned = computed(() => target.value?.criteria ?? []);
const tasks = computed(() => assigned.value.filter(isKpi));
const focus = computed(() =>
  assigned.value.filter((c) => c.value_type === "Text" && c.info_only)
);
const toMarkDone = computed(
  () => tasks.value.filter((c) => !c.kpi_status).length
);

/** Each numeric target with where it stands once counted (null until then). */
const figures = computed(() =>
  assigned.value
    .filter((c) => c.value_type !== "Text")
    .map((criterion) => {
      const measured =
        criterion.measure && progress.data?.state === "counted"
          ? progress.data.criteria?.[criterion.criterion]
          : null;
      const standing: Standing | null = measured
        ? progressOf(criterion, measured, progress.data!, mine.data!.currency)
            .standing
        : null;
      return { criterion, standing };
    })
);

type Show = "all" | "done" | "on_pace" | "behind";
const BEHIND: (Standing | null)[] = ["behind", "short", "below"];
const standing = ref<Show>("all");
function matches(show: Show, s: Standing | null) {
  if (show === "all") return true;
  if (show === "behind") return BEHIND.includes(s);
  return s === show;
}
function standingCount(show: string) {
  return figures.value.filter((f) => matches(show as Show, f.standing)).length;
}
const standingOptions = [
  { label: __("All"), value: "all" },
  { label: __("Reached"), value: "done" },
  { label: __("On pace"), value: "on_pace" },
  { label: __("Behind"), value: "behind" },
];
const shownFigures = computed(() =>
  figures.value.filter((f) => matches(standing.value, f.standing))
);
watch(month, () => (standing.value = "all"));

const summary = computed(() => {
  const count = assigned.value.length;
  const parts = [
    count === 1 ? __("1 target set") : __("{0} targets set", String(count)),
  ];
  if (pace.value.state === "running")
    parts.push(
      __(
        "{0} of {1} days gone",
        String(pace.value.day),
        String(pace.value.days)
      )
    );
  else if (pace.value.state === "over") parts.push(__("month over"));
  else parts.push(__("starts on the 1st"));
  return parts.join(" · ");
});

// the chips on the dark panel: each with its count in words, tinted by what it means
const chips = computed(() =>
  [
    {
      count: standingCount("done"),
      label: __("{0} reached", String(standingCount("done"))),
      class:
        "bg-[color-mix(in_srgb,var(--hero-fill)_18%,transparent)] text-hero-fill",
    },
    {
      count: standingCount("on_pace"),
      label: __("{0} on pace", String(standingCount("on_pace"))),
      class: "bg-hero-track text-hero-ink",
    },
    {
      count: standingCount("behind"),
      label: __("{0} behind", String(standingCount("behind"))),
      class:
        "bg-[color-mix(in_srgb,var(--hero-pace)_18%,transparent)] text-hero-pace",
    },
    {
      count: toMarkDone.value,
      label: __("{0} to mark done", String(toMarkDone.value)),
      class: "bg-hero-track text-hero-ink",
    },
  ].filter((chip) => chip.count)
);

// ---------- no targets yet ----------

// asking once is enough: the server tells each Sales Head once a month
const ask = createResource({
  url: "helpdesk.api.sales_targets.ask_for_targets",
  onSuccess: () => {
    if (mine.data) mine.data.asked = true;
  },
});
const asked = computed(() => !!mine.data?.asked);

const HOW = [
  {
    title: __("Your Sales Head sets them"),
    text: __(
      "Numbers like leads contacted, proposals or won value, plus tasks to mark done."
    ),
  },
  {
    title: __("Your leads count towards them"),
    text: __("Calls, stages and wins add up on their own. Nothing to fill in."),
  },
  {
    title: __("You see your pace here"),
    text: __("Each card shows where you are and where you should be by today."),
  },
];

// where to get on with the work meanwhile: only what the sidebar also offers them
const shortcuts = computed(() =>
  [
    {
      show:
        auth.canUseLeads &&
        batchesOn(leadOptions.data) &&
        !auth.hideTodaysCalls,
      title: __("Today's calls"),
      text: __("Work through your call list"),
      icon: LucidePhone,
      tile: "bg-brand-soft text-brand-ink",
      to: { name: "Leads", query: { view: "today" } },
    },
    {
      show: auth.canUseLeads,
      title: __("My leads"),
      text: __("Follow up and move stages"),
      icon: LucideStar,
      tile: "bg-violet-soft text-violet",
      to: { name: "Leads", query: { view: "mine" } },
    },
    {
      show: auth.canUseLeads && auth.hasOwnSalesDashboard,
      title: __("Dashboard"),
      text: __("See your calls and pipeline"),
      icon: LucideGauge,
      tile: "bg-warning-soft text-warning",
      to: { name: "SalesDashboard" },
    },
  ].filter((shortcut) => shortcut.show)
);

/** This month, the one open, and every month they have targets in, newest first. */
const monthChoices = computed(() =>
  [...new Set([monthValue(), month.value, ...(mine.data?.months ?? [])])]
    .sort()
    .reverse()
    .map((value) => ({ label: monthTitle(value), value }))
);
/** The newest other month with targets, offered when this one has none. */
const latestOther = computed(() =>
  (mine.data?.months ?? []).find((m) => m !== month.value)
);
</script>

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

        <template v-else>
          <!-- the month, how many targets, and who set them -->
          <section
            class="flex flex-wrap items-center gap-x-8 gap-y-5 rounded-xl bg-hero px-5 py-6 text-hero-ink md:px-8"
            :aria-labelledby="heading"
          >
            <div class="flex min-w-0 flex-1 items-center gap-4">
              <span
                class="grid size-14 shrink-0 place-items-center rounded-xl bg-hero-track"
                aria-hidden="true"
              >
                <LucideTarget class="size-7" />
              </span>
              <div class="flex min-w-0 flex-col gap-0.5">
                <span class="text-base text-hero-muted">{{
                  __("Your targets for")
                }}</span>
                <h2
                  :id="heading"
                  class="text-[28px] font-bold leading-tight tracking-[-0.02em]"
                >
                  {{ monthTitle(month) }}
                </h2>
              </div>
            </div>

            <!-- nothing assigned: every standard target shows at 0 below -->
            <div v-if="!target" class="flex flex-wrap items-center gap-4">
              <p class="text-sm text-hero-muted">
                {{ __("Your Sales Head hasn't assigned targets yet.") }}
              </p>
              <button
                v-if="latestOther"
                type="button"
                class="h-9 rounded-lg bg-surface-base px-3 text-sm font-medium text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                @click="pickMonth(latestOther)"
              >
                {{ __("See {0}", monthTitle(latestOther)) }}
              </button>
            </div>
            <div v-else class="flex flex-wrap items-center gap-x-8 gap-y-4">
              <div class="flex flex-col items-center">
                <span class="text-[40px] font-bold leading-none tabular-nums">
                  {{ target.criteria.length }}
                </span>
                <span class="text-sm text-hero-muted">
                  {{
                    target.criteria.length === 1
                      ? __("target set")
                      : __("targets set")
                  }}
                </span>
              </div>
              <div
                v-if="overall?.percent != null"
                class="flex flex-col items-center"
              >
                <span class="text-[40px] font-bold leading-none tabular-nums">
                  {{ overall.percent }}%
                </span>
                <span class="text-sm text-hero-muted">
                  {{
                    overall.behind
                      ? __("reached · {0} behind", String(overall.behind))
                      : __("reached so far")
                  }}
                </span>
              </div>
              <div
                class="flex min-w-0 items-center gap-3 sm:border-l sm:border-hero-track sm:pl-8"
              >
                <PersonAvatar :name="setBy" size="lg" />
                <div class="flex min-w-0 flex-col">
                  <span class="text-sm text-hero-muted">{{
                    __("Set by")
                  }}</span>
                  <span class="truncate text-base font-semibold">{{
                    setBy
                  }}</span>
                  <span class="text-sm text-hero-muted tabular-nums">
                    {{
                      __(
                        "Last changed {0}",
                        dayjs(target.modified).format("D MMM YYYY, h:mm a")
                      )
                    }}
                  </span>
                </div>
              </div>
            </div>
          </section>

          <!-- every target as a card, in the head's order: figures first, then the written ones -->
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <TargetFigure
              v-for="(criterion, i) in figures"
              :key="criterion.criterion"
              :index="i + 1"
              :criterion="criterion"
              :unassigned="criterion.unassigned"
              :currency="mine.data.currency"
              :progress="progress.data ?? null"
              :owner="auth.userName"
              :link="
                auth.canUseLeads && progress.data
                  ? leadsLink(criterion, progress.data, auth.userId)
                  : null
              "
            />
            <TargetFigure
              v-for="(criterion, i) in written"
              :key="criterion.criterion"
              :index="figures.length + i + 1"
              :criterion="criterion"
              :unassigned="criterion.unassigned"
              :currency="mine.data.currency"
              :progress="null"
              :owner="auth.userName"
              :link="null"
            >
              <!-- information only (Industry, Location) is nothing to tick off -->
              <KpiStatus
                v-if="isKpi(criterion) && !criterion.unassigned"
                :criterion="criterion"
                :month="month"
                mode="person"
                @changed="mine.data.target = $event"
              />
            </TargetFigure>
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
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideLock from "~icons/lucide/lock";
import LucideInfo from "~icons/lucide/info";
import LucideTarget from "~icons/lucide/target";
import KpiStatus from "./KpiStatus.vue";
import {
  isKpi,
  leadsLink,
  monthTitle,
  monthValue,
  overallOf,
  withUnassigned,
  type MyTargets,
  type Progress,
} from "./salesTargets";
import TargetFigure from "./TargetFigure.vue";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const heading = useId();

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
// what was assigned, then each standard target not assigned at 0; figures first, then the
// written targets, each in the head's order
const shown = computed(() =>
  withUnassigned(target.value, mine.data?.defaults ?? [])
);
const figures = computed(() =>
  shown.value.filter((c) => c.value_type !== "Text")
);
const written = computed(() =>
  shown.value.filter((c) => c.value_type === "Text")
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

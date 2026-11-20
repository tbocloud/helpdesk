<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Your sales targets')"
      :subtitle="__('What your Sales Head set for you, month by month.')"
    >
      <template #right-header>
        <MonthStepper
          :model-value="month"
          :options="monthChoices"
          @update:model-value="pickMonth"
        />
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
          <section
            class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-labelledby="heading"
          >
            <!-- the month, and who set its targets -->
            <header
              class="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-4 md:px-5"
            >
              <div class="flex min-w-0 flex-col gap-0.5">
                <h2
                  :id="heading"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ monthTitle(month) }}
                </h2>
                <!-- nothing assigned: every standard target shows at 0 below -->
                <p v-if="!target" class="text-sm text-ink-gray-6">
                  {{ __("Your Sales Head hasn't assigned targets yet.") }}
                </p>
                <p v-else class="text-sm text-ink-gray-6 tabular-nums">
                  {{
                    target.criteria.length === 1
                      ? __("1 target")
                      : __("{0} targets", String(target.criteria.length))
                  }}
                  <template v-if="overall?.percent != null">
                    ·
                    {{
                      __("{0}% of the month reached", String(overall.percent))
                    }}
                    <template v-if="overall.behind">
                      ·
                      {{
                        overall.behind === 1
                          ? __("1 behind")
                          : __("{0} behind", String(overall.behind))
                      }}
                    </template>
                  </template>
                </p>
              </div>
              <Button
                v-if="!target && latestOther"
                :label="__('See {0}', monthTitle(latestOther))"
                @click="pickMonth(latestOther)"
              />
              <div v-else-if="target" class="flex min-w-0 items-center gap-2.5">
                <PersonAvatar :name="setBy" size="lg" />
                <div class="flex min-w-0 flex-col">
                  <span class="truncate text-sm font-medium text-ink-gray-8">
                    {{ __("Set by {0}", setBy) }}
                  </span>
                  <span class="text-xs text-ink-gray-6 tabular-nums">
                    {{
                      __(
                        "Last changed {0}",
                        dayjs(target.modified).format("D MMM YYYY, h:mm a")
                      )
                    }}
                  </span>
                </div>
              </div>
            </header>
          </section>

          <!-- every target as the app's stat card, in the head's order: figures, then the written ones -->
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4"
          >
            <TargetFigure
              v-for="criterion in figures"
              :key="criterion.criterion"
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
            <StatTile
              v-for="criterion in written"
              :key="criterion.criterion"
              :label="criterion.criterion"
              :value="criterion.unassigned ? '—' : String(criterion.target)"
              :sub="criterion.unassigned ? __('Not assigned yet') : undefined"
              :icon="VALUE_TYPE_LOOK.Text.icon"
              :icon-tone="VALUE_TYPE_LOOK.Text.tone"
            >
              <!-- information only (Industry, Location) is nothing to tick off -->
              <KpiStatus
                v-if="isKpi(criterion) && !criterion.unassigned"
                class="mt-1"
                :criterion="criterion"
                :month="month"
                mode="person"
                @changed="mine.data.target = $event"
              />
            </StatTile>
          </div>

          <p class="flex items-center gap-2 text-xs text-ink-gray-6">
            <LucideMessageCircleQuestion
              class="size-3.5 shrink-0"
              aria-hidden="true"
            />
            {{
              setBy
                ? __("Questions about a target? Ask {0}.", setBy)
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
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { useAuthStore } from "@/stores/auth";
import { errorText } from "@/utils";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideLock from "~icons/lucide/lock";
import LucideMessageCircleQuestion from "~icons/lucide/message-circle-question";
import KpiStatus from "./KpiStatus.vue";
import MonthStepper from "./MonthStepper.vue";
import {
  isKpi,
  leadsLink,
  monthTitle,
  monthValue,
  overallOf,
  VALUE_TYPE_LOOK,
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
// what was assigned, then each standard target not assigned at 0; figures go in the grid,
// written targets in a list under it, each in the head's order
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

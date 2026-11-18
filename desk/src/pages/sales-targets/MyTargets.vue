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

        <TaskyState
          v-else-if="!target"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideGoal"
          :title="__('No targets for {0} yet', monthTitle(month))"
          :message="
            __(
              'Your Sales Head hasn\'t set them. They show here as soon as they do.'
            )
          "
        >
          <Button
            v-if="latestOther"
            :label="__('See {0}', monthTitle(latestOther))"
            @click="pickMonth(latestOther)"
          />
        </TaskyState>

        <section
          v-else
          class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
          :aria-labelledby="heading"
        >
          <!-- the month, and who set its targets -->
          <header
            class="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-outline-gray-2 px-4 py-4 md:px-5"
          >
            <div class="flex min-w-0 flex-col gap-0.5">
              <h2 :id="heading" class="text-base font-semibold text-ink-gray-9">
                {{ monthTitle(month) }}
              </h2>
              <p class="text-sm text-ink-gray-6 tabular-nums">
                {{
                  target.criteria.length === 1
                    ? __("1 target")
                    : __("{0} targets", String(target.criteria.length))
                }}
              </p>
            </div>
            <div class="flex min-w-0 items-center gap-2.5">
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

          <!-- the figures; each cell draws its right and bottom hairline, the outer ones clipped -->
          <div
            v-if="figures.length"
            class="-mb-px -mr-px grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4"
          >
            <TargetFigure
              v-for="criterion in figures"
              :key="criterion.criterion"
              :criterion="criterion"
              :currency="mine.data.currency"
            />
          </div>

          <!-- targets written in words, as the Sales Head wrote them -->
          <dl
            v-if="written.length"
            class="divide-y divide-outline-gray-1 border-t border-outline-gray-2"
          >
            <div
              v-for="criterion in written"
              :key="criterion.criterion"
              class="grid gap-1 px-4 py-4 sm:grid-cols-[14rem_minmax(0,1fr)] sm:gap-4 md:px-5"
            >
              <dt class="flex min-w-0 items-center gap-2 self-start">
                <span
                  class="grid size-7 shrink-0 place-items-center rounded-lg bg-surface-gray-2 text-ink-gray-7"
                  aria-hidden="true"
                >
                  <LucideText class="size-3.5" />
                </span>
                <span class="min-w-0 text-sm font-medium text-ink-gray-7">{{
                  criterion.criterion
                }}</span>
              </dt>
              <dd
                class="min-w-0 whitespace-pre-line break-words text-p-base text-ink-gray-9 sm:pt-1"
              >
                {{ criterion.target }}
              </dd>
            </div>
          </dl>

          <p
            class="flex items-center gap-2 border-t border-outline-gray-2 bg-surface-gray-1 px-4 py-3 text-xs text-ink-gray-6 md:px-5"
          >
            <LucideMessageCircleQuestion
              class="size-3.5 shrink-0"
              aria-hidden="true"
            />
            {{ __("Questions about a target? Ask {0}.", setBy) }}
          </p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideGoal from "~icons/lucide/goal";
import LucideLock from "~icons/lucide/lock";
import LucideMessageCircleQuestion from "~icons/lucide/message-circle-question";
import LucideText from "~icons/lucide/text";
import MonthStepper from "./MonthStepper.vue";
import { monthTitle, monthValue, type MyTargets } from "./salesTargets";
import TargetFigure from "./TargetFigure.vue";

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
const setBy = computed(() =>
  target.value ? target.value.assigned_by_name || target.value.assigned_by : ""
);
// figures go in the grid, written targets in a list under it; each keeps the head's order
const figures = computed(
  () => target.value?.criteria.filter((c) => c.value_type !== "Text") ?? []
);
const written = computed(
  () => target.value?.criteria.filter((c) => c.value_type === "Text") ?? []
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

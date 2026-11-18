<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Sales targets')"
      :subtitle="__('What your Sales Head set for you, month by month.')"
    >
      <template #right-header>
        <FormControl
          :model-value="month"
          type="select"
          size="md"
          class="w-44"
          :aria-label="__('Month')"
          :options="monthChoices"
          @update:model-value="pickMonth(String($event))"
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
              ? __('Sales targets isn\'t available to you')
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
          class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div
            v-for="i in 4"
            :key="i"
            class="h-28 animate-pulse rounded-xl bg-surface-gray-3"
          />
        </div>

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

        <template v-else>
          <section class="flex flex-col gap-3" :aria-labelledby="cardsHeading">
            <div class="flex flex-wrap items-baseline justify-between gap-2">
              <h2
                :id="cardsHeading"
                class="text-base font-semibold text-ink-gray-9"
              >
                {{ __("Your targets for {0}", monthTitle(month)) }}
              </h2>
              <span class="text-sm tabular-nums text-ink-gray-6">
                {{
                  target.criteria.length === 1
                    ? __("1 target")
                    : __("{0} targets", String(target.criteria.length))
                }}
              </span>
            </div>
            <div
              class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4"
            >
              <TargetCard
                v-for="(criterion, i) in target.criteria"
                :key="criterion.criterion"
                :criterion="criterion"
                :position="i + 1"
                :currency="mine.data.currency"
              />
            </div>
          </section>

          <p class="text-xs text-ink-gray-6">
            {{
              __(
                "Set by {0} · last changed {1}",
                target.assigned_by_name || target.assigned_by,
                dayjs(target.modified).format("D MMM YYYY, h:mm a")
              )
            }}
          </p>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideGoal from "~icons/lucide/goal";
import LucideLock from "~icons/lucide/lock";
import { monthTitle, monthValue, type MyTargets } from "./salesTargets";
import TargetCard from "./TargetCard.vue";

const route = useRoute();
const router = useRouter();
const cardsHeading = useId();

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

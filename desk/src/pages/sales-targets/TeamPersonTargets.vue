<template>
  <!-- one person's month for a Sales Head: every target with how far they are, their KPIs
       to confirm, and a way to change the targets -->
  <div class="flex min-w-0 flex-col">
    <header
      class="flex min-w-0 flex-wrap items-center gap-3 border-b border-outline-gray-2 p-4"
    >
      <PersonAvatar :name="person.full_name" size="lg" />
      <div class="flex min-w-0 flex-1 flex-col">
        <h2
          :id="headingId"
          class="truncate text-base font-semibold text-ink-gray-9"
          :title="person.full_name"
        >
          {{ person.full_name }}
        </h2>
        <p class="truncate text-xs text-ink-gray-6 tabular-nums">
          <template v-if="target">
            {{
              __("Set by {0}", target.assigned_by_name || target.assigned_by)
            }}
            ·
            {{
              __(
                "last changed {0}",
                dayjs(target.modified).format("D MMM YYYY")
              )
            }}
          </template>
          <template v-else>
            {{ __("No targets for {0} yet", monthTitle(month)) }}
          </template>
        </p>
      </div>
      <Button
        size="md"
        :label="target ? __('Edit targets') : __('Assign targets')"
        :variant="target ? 'subtle' : 'solid'"
        @click="openAssign"
      >
        <template #prefix>
          <LucidePencil v-if="target" class="size-4" />
          <LucideTarget v-else class="size-4" />
        </template>
      </Button>
    </header>

    <TaskyState
      v-if="!target"
      class="px-4 py-10"
      :icon="LucideCircleDashed"
      :title="__('Nothing to track yet')"
      :message="
        __(
          'Give {0} targets for {1} and their progress shows here, counted from their leads.',
          person.full_name,
          monthTitle(month)
        )
      "
    />

    <div v-else class="flex min-w-0 flex-col gap-4 overflow-y-auto p-4">
      <!-- the month overall, or why it isn't counted -->
      <p
        v-if="progress?.state === 'unavailable'"
        class="flex items-start gap-2 text-sm text-warning"
      >
        <LucideTriangleAlert
          class="mt-0.5 size-4 shrink-0"
          aria-hidden="true"
        />
        {{ __("Couldn't count their progress: {0}", progress.reason || "") }}
      </p>
      <p
        v-else-if="progress?.state === 'not_started'"
        class="text-sm text-ink-gray-6"
      >
        {{ __("{0} hasn't begun: nothing is counted yet.", monthTitle(month)) }}
      </p>
      <div
        v-else-if="overall?.percent != null"
        class="flex flex-wrap items-center justify-between gap-2"
      >
        <span class="text-sm text-ink-gray-7">
          {{ __("The month so far") }}
          <span v-if="progress" class="text-ink-gray-5">
            · {{ countedOver(progress) }}
          </span>
        </span>
        <OverallProgress :percent="overall.percent" :behind="overall.behind" />
      </div>

      <div class="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
        <TargetFigure
          v-for="(criterion, i) in figures"
          :key="criterion.criterion"
          :index="i + 1"
          :criterion="criterion"
          :currency="currency"
          :progress="progress"
          :owner="person.full_name"
          :link="
            canUseLeads && progress
              ? leadsLink(criterion, progress, person.user)
              : null
          "
        />
        <TargetFigure
          v-for="(criterion, i) in written"
          :key="criterion.criterion"
          :index="figures.length + i + 1"
          :criterion="criterion"
          :currency="currency"
          :progress="null"
          :owner="person.full_name"
          :link="null"
        >
          <KpiStatus
            v-if="isKpi(criterion)"
            :criterion="criterion"
            :month="month"
            mode="head"
            :employee="person.user"
            @changed="emit('changed', $event)"
          />
        </TargetFigure>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, dayjs } from "frappe-ui";
import { computed } from "vue";
import { useRouter } from "vue-router";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucidePencil from "~icons/lucide/pencil";
import LucideTarget from "~icons/lucide/target";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import KpiStatus from "./KpiStatus.vue";
import OverallProgress from "./OverallProgress.vue";
import TargetFigure from "./TargetFigure.vue";
import {
  countedOver,
  isKpi,
  leadsLink,
  monthTitle,
  overallOf,
  type Progress,
  type Target,
  type TargetPerson,
} from "./salesTargets";

const props = defineProps<{
  person: TargetPerson;
  month: string;
  currency: string;
  /** null while it is being read */
  progress: Progress | null;
  headingId: string;
}>();
const emit = defineEmits<{ changed: [target: Target] }>();

const router = useRouter();
const canUseLeads = computed(() => useAuthStore().canUseLeads);

const target = computed(() => props.person.target);
const overall = computed(() =>
  target.value && props.progress?.state === "counted"
    ? overallOf(target.value, props.progress, props.currency)
    : null
);
// figures first, then the written ones, each in the head's order (as the person's own page)
const figures = computed(() =>
  (target.value?.criteria ?? []).filter((c) => c.value_type !== "Text")
);
const written = computed(() =>
  (target.value?.criteria ?? []).filter((c) => c.value_type === "Text")
);

function openAssign() {
  router.push({
    name: "SalesTargets",
    query: { month: props.month, employee: props.person.user },
  });
}
</script>

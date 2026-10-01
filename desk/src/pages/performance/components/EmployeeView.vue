<template>
  <div class="flex flex-col gap-4">
    <header class="flex items-center gap-3">
      <Avatar
        size="3xl"
        :image="data.person.image"
        :label="data.person.employee_name"
      />
      <div>
        <h2 class="text-xl font-semibold text-ink-gray-9">
          {{ data.person.employee_name }}
        </h2>
        <p class="text-p-sm text-ink-gray-5">
          {{
            [data.person.designation, data.person.department]
              .filter(Boolean)
              .join(" · ")
          }}
          <span class="font-mono text-xs"> · {{ data.person.employee }}</span>
        </p>
      </div>
    </header>

    <section
      class="grid grid-cols-2 gap-3 lg:grid-cols-6"
      :aria-label="__('Summary')"
    >
      <StatTile
        hero
        :icon="LucideClock"
        :label="__('Hours logged')"
        :value="formatHours(s.hours)"
        :sub="
          __(
            'of {0} expected · {1} active days',
            formatHours(s.expected_hours),
            String(s.active_days)
          )
        "
        :meter="s.utilisation"
        :tone="utilTone(s.utilisation)"
      />
      <StatTile
        :icon="LucideGauge"
        :label="__('Utilisation')"
        :value="pctText(s.utilisation)"
        :sub="
          __(
            '{0} per active day',
            formatHours(s.active_days ? s.hours / s.active_days : null)
          )
        "
      />
      <StatTile
        :icon="LucideCircleCheck"
        :label="__('Tasks completed')"
        :value="String(s.tasks_completed)"
        :sub="
          s.on_time_pct == null
            ? __('none completed')
            : __('{0} on time', pctText(s.on_time_pct))
        "
      />
      <StatTile
        :icon="LucideCircleAlert"
        :label="__('Overdue tasks')"
        :value="String(s.tasks_overdue)"
        :sub="__('{0} due in this period', String(s.tasks_due))"
      />
      <StatTile
        :icon="LucideSend"
        :label="__('Content')"
        :value="__('{0} of {1}', String(s.posts_published), String(s.posts))"
        :sub="
          s.posts
            ? __('published · {0} missed', String(s.posts_missed))
            : __('no posts in this period')
        "
      />
    </section>

    <section
      class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    >
      <h3 class="text-base font-semibold text-ink-gray-9">
        {{ __("Hours per day") }}
      </h3>
      <p class="mb-2 text-p-sm text-ink-gray-5">
        {{
          __(
            "Logged time against a {0} working day",
            formatHours(data.hours_per_day)
          )
        }}
      </p>
      <DailyHoursChart :days="data.daily" :target="data.hours_per_day" />
    </section>

    <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section
        class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
      >
        <h3 class="mb-3 text-base font-semibold text-ink-gray-9">
          {{ __("Where the time went") }}
        </h3>
        <p
          v-if="!data.by_activity.length"
          class="py-8 text-center text-p-sm text-ink-gray-5"
        >
          {{ __("No time logged in this period.") }}
        </p>
        <ActivityDonut v-else :items="data.by_activity" />
      </section>
      <section
        class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
      >
        <h3 class="mb-3 text-base font-semibold text-ink-gray-9">
          {{ __("Hours by project") }}
        </h3>
        <p
          v-if="!data.by_project.length"
          class="py-8 text-center text-p-sm text-ink-gray-5"
        >
          {{ __("No time logged in this period.") }}
        </p>
        <ProjectBars v-else :items="data.by_project" />
      </section>
    </div>

    <section
      class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
    >
      <h3 class="px-4 pt-4 text-base font-semibold text-ink-gray-9">
        {{ __("Tasks") }}
      </h3>
      <p
        v-if="!data.tasks.length"
        class="px-4 py-8 text-center text-p-sm text-ink-gray-5"
      >
        {{ __("No tasks were due or completed in this period.") }}
      </p>
      <div v-else class="overflow-x-auto">
        <table class="mt-2 w-full min-w-[760px] text-left text-sm">
          <thead
            class="border-y border-outline-gray-2 bg-surface-gray-1 text-xs text-ink-gray-5"
          >
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">
                {{ __("Task") }}
              </th>
              <th scope="col" class="px-4 py-2 font-medium">
                {{ __("Project") }}
              </th>
              <th scope="col" class="px-4 py-2 font-medium">
                {{ __("Status") }}
              </th>
              <th scope="col" class="px-4 py-2 font-medium">{{ __("Due") }}</th>
              <th scope="col" class="px-4 py-2 text-right font-medium">
                {{ __("Estimated") }}
              </th>
              <th scope="col" class="px-4 py-2 text-right font-medium">
                {{ __("Logged") }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="t in data.tasks"
              :key="t.name"
              class="border-b border-outline-gray-1 last:border-0"
            >
              <td class="max-w-[22rem] px-4 py-2">
                <div class="truncate text-ink-gray-9">{{ t.subject }}</div>
                <div class="font-mono text-xs text-ink-gray-5">
                  {{ t.name }}
                </div>
              </td>
              <td class="max-w-[12rem] truncate px-4 py-2 text-ink-gray-7">
                {{ t.project || "—" }}
              </td>
              <td class="px-4 py-2"><StatePill :state="t.state" /></td>
              <td
                class="whitespace-nowrap px-4 py-2 font-mono text-xs tabular-nums text-ink-gray-7"
              >
                {{ t.due ? dayjs(t.due).format("D MMM") : "—" }}
              </td>
              <td
                class="px-4 py-2 text-right font-mono text-xs tabular-nums text-ink-gray-7"
              >
                {{ t.estimated ? formatHours(t.estimated) : "—" }}
              </td>
              <td
                class="px-4 py-2 text-right font-mono text-xs tabular-nums"
                :class="
                  t.estimated && t.logged > t.estimated
                    ? 'text-danger'
                    : 'text-ink-gray-7'
                "
              >
                {{ t.logged ? formatHours(t.logged) : "—" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section
      v-if="data.posts.length"
      class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
    >
      <h3 class="px-4 pt-4 text-base font-semibold text-ink-gray-9">
        {{ __("Content") }}
      </h3>
      <div class="overflow-x-auto">
        <table class="mt-2 w-full min-w-[640px] text-left text-sm">
          <thead
            class="border-y border-outline-gray-2 bg-surface-gray-1 text-xs text-ink-gray-5"
          >
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">
                {{ __("Post") }}
              </th>
              <th scope="col" class="px-4 py-2 font-medium">
                {{ __("Customer") }}
              </th>
              <th scope="col" class="px-4 py-2 font-medium">
                {{ __("Role") }}
              </th>
              <th scope="col" class="px-4 py-2 font-medium">{{ __("Due") }}</th>
              <th scope="col" class="px-4 py-2 font-medium">
                {{ __("Status") }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in data.posts"
              :key="p.name"
              class="border-b border-outline-gray-1 last:border-0"
            >
              <td class="max-w-[20rem] truncate px-4 py-2 text-ink-gray-9">
                {{ p.title }}
              </td>
              <td class="px-4 py-2 text-ink-gray-7">{{ p.customer }}</td>
              <td class="px-4 py-2 text-ink-gray-7">{{ p.role }}</td>
              <td
                class="whitespace-nowrap px-4 py-2 font-mono text-xs tabular-nums text-ink-gray-7"
              >
                {{ dayjs(p.publish_on).format("D MMM, h:mm A") }}
              </td>
              <td class="px-4 py-2"><StatePill :state="p.state" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Avatar, dayjs } from "frappe-ui";
import { computed } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideGauge from "~icons/lucide/gauge";
import LucideSend from "~icons/lucide/send";
import { formatHours } from "../chartTheme";
import { pctText, utilTone } from "../performanceMeta";
import ActivityDonut from "./ActivityDonut.vue";
import DailyHoursChart from "./DailyHoursChart.vue";
import ProjectBars from "./ProjectBars.vue";
import StatePill from "./StatePill.vue";
import StatTile from "./StatTile.vue";

const props = defineProps<{ data: any }>();
const s = computed(() => props.data.summary);
</script>

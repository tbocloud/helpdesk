<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Sales team dashboard')"
      :subtitle="
        __('How your team\'s leads are moving, and who needs a nudge.')
      "
    >
      <template #right-header>
        <div class="flex items-center gap-2">
          <Button
            size="md"
            :aria-label="__('Refresh')"
            :loading="dash.loading"
            @click="refresh"
          >
            <template #icon>
              <LucideRefreshCw class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            v-if="auth.canAssignSalesTargets"
            size="md"
            :label="__('Set targets')"
            :route="{ name: 'SalesTargets' }"
          />
          <Button
            v-if="canAssign"
            size="md"
            variant="solid"
            :label="__('Assign leads')"
            :route="{ name: 'AssignLeads' }"
          >
            <template #prefix>
              <LucideSend class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <!-- the period, whose leads, the department and the source, in one card -->
        <div
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
        >
          <div class="flex flex-wrap items-center gap-3">
            <TabButtons
              :model-value="period"
              size="md"
              :aria-label="__('Period')"
              :options="PERIODS"
              @update:model-value="setQuery({ period: $event })"
            />
            <label class="sr-only" :for="ownerId">{{
              __("Whose leads")
            }}</label>
            <FormControl
              :id="ownerId"
              type="select"
              class="sm:w-52"
              :model-value="owner"
              :options="ownerOptions"
              @update:model-value="setQuery({ owner: $event || undefined })"
            />
            <FormControl
              v-if="departmentOptions.length"
              type="select"
              class="sm:w-48"
              :aria-label="__('Department')"
              :model-value="department"
              :options="departmentOptions"
              @update:model-value="
                setQuery({ department: $event || undefined })
              "
            />
            <FormControl
              type="select"
              class="sm:w-44"
              :aria-label="__('Source')"
              :model-value="source"
              :options="sourceOptions"
              @update:model-value="setQuery({ source: $event || undefined })"
            />
          </div>
          <p class="text-[12px] text-ink-gray-6">
            <strong class="font-semibold text-ink-gray-9">{{
              dayjs().format("ddd, D MMM YYYY")
            }}</strong>
            · {{ __("tap any number to open those leads") }}
          </p>
        </div>

        <TaskyState
          v-if="dash.error && !data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :error="!isRefusal"
          :icon="isRefusal ? LucideLock : LucideCircleAlert"
          :title="
            isRefusal
              ? __('This dashboard is for managers')
              : __('Couldn\'t load the team dashboard')
          "
          :message="
            errorText(dash.error, __('Check your connection and try again.'))
          "
        >
          <Button v-if="!isRefusal" :label="__('Try again')" @click="refresh" />
        </TaskyState>

        <template v-else-if="!data">
          <div
            v-for="n in 3"
            :key="n"
            class="h-40 animate-pulse rounded-xl bg-surface-gray-3"
            aria-busy="true"
            :aria-label="__('Loading')"
          />
        </template>

        <template v-else>
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4"
          >
            <StatTile
              :label="__('New leads')"
              :value="totals.new"
              :icon="LucidePlus"
              icon-tone="info"
              :sub="periodWord.came"
              :to="metricLink('new', periodQuery)"
            />
            <StatTile
              :label="__('Contacted')"
              :value="totals.contacted"
              :icon="LucideCheck"
              icon-tone="success"
              :sub="
                __(
                  '{0}% of new leads',
                  String(percent(totals.contacted, totals.new))
                )
              "
              :to="metricLink('contacted', periodQuery)"
            />
            <StatTile
              :label="__('Hot leads')"
              :value="totals.hot"
              :icon="LucideFlame"
              icon-tone="hot"
              :sub="__('ready to close')"
              :to="metricLink('hot', ownerQuery)"
            />
            <StatTile
              :label="__('Overdue follow-ups')"
              :value="totals.overdue"
              :icon="LucideAlarmClock"
              icon-tone="danger"
              :value-tone="totals.overdue ? 'danger' : 'neutral'"
              :sub="
                __(
                  '{0} more gone quiet {1}+ days',
                  String(totals.stale),
                  String(overview.stale_days)
                )
              "
              :to="metricLink('overdue', ownerQuery)"
            />
            <StatTile
              :label="__('Open pipeline')"
              :value="totals.open"
              :icon="LucideTrendingUp"
              tint="brand"
              :sub="
                __('open leads · {0}% won', String(Math.round(totals.win_rate)))
              "
              :to="metricLink('open', ownerQuery)"
            />
          </div>

          <div class="grid grid-cols-1 gap-4 lg:grid-cols-5">
            <!-- Team calls this week: each person's calls per day -->
            <section
              class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 lg:col-span-3"
              :aria-labelledby="ids.week"
            >
              <div class="flex flex-col gap-0.5">
                <h2
                  :id="ids.week"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Team calls this week") }}
                </h2>
                <p class="text-xs text-ink-gray-6">
                  {{
                    weekLines.length < weekPeople.length
                      ? __(
                          "Calls per day, the {0} who called most",
                          String(weekLines.length)
                        )
                      : __("Calls per day, person by person")
                  }}
                </p>
              </div>
              <PartError :message="errors.week" />
              <p
                v-if="week && !weekLines.length"
                class="py-10 text-center text-sm text-ink-gray-6"
              >
                {{ __("No calls this week yet.") }}
              </p>
              <WeekLineChart
                v-else-if="week"
                :days="week.days"
                :series="weekLines"
                :label="__('Team calls this week')"
              />
            </section>

            <!-- Pipeline by stage: where the open leads are sitting now -->
            <section
              class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 lg:col-span-2"
              :aria-labelledby="ids.pipeline"
            >
              <div class="flex flex-col gap-0.5">
                <h2
                  :id="ids.pipeline"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Pipeline by stage") }}
                </h2>
                <p class="text-xs tabular-nums text-ink-gray-6">
                  {{
                    __(
                      "Where the {0} open leads are sitting",
                      String(pipelineTotal)
                    )
                  }}
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-5">
                <DonutChart
                  :parts="pipelineParts"
                  :value="pipelineTotal"
                  :caption="__('open')"
                  :label="__('Pipeline by stage')"
                  small
                />
                <ul class="flex min-w-[10rem] flex-1 flex-col gap-1.5">
                  <li v-for="part in pipelineParts" :key="part.label">
                    <component
                      :is="part.stage ? RouterLink : 'span'"
                      v-bind="part.stage ? { to: stageLink(part.stage) } : {}"
                      class="flex items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                    >
                      <span
                        class="size-2.5 shrink-0 rounded-full"
                        :style="{ background: part.color }"
                        aria-hidden="true"
                      />
                      <span class="flex-1 truncate text-ink-gray-7">{{
                        part.label
                      }}</span>
                      <span class="font-semibold tabular-nums text-ink-gray-9">
                        {{ part.value.toLocaleString() }}
                      </span>
                    </component>
                  </li>
                </ul>
              </div>
            </section>
          </div>

          <!-- Your team: calls, contacts and target progress, person by person -->
          <section
            class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-labelledby="ids.team"
          >
            <header
              class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-2 px-4 py-4"
            >
              <div class="flex flex-col gap-0.5">
                <h2
                  :id="ids.team"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ periodWord.team }}
                </h2>
                <p class="text-xs text-ink-gray-6">
                  {{
                    hasTargets
                      ? __(
                          "Calls, contacts and {0} target progress, person by person",
                          monthTitle(monthValue())
                        )
                      : __("Calls and contacts, person by person")
                  }}
                </p>
              </div>
              <div v-if="hasTargets" class="flex gap-1.5">
                <span
                  class="inline-flex items-center gap-1 rounded-full bg-success-soft px-2 py-0.5 text-xs font-medium text-success"
                >
                  <LucideCircleCheck class="size-3" aria-hidden="true" />
                  {{ __("{0} on track", String(standingCount.onTrack)) }}
                </span>
                <span
                  v-if="standingCount.behind"
                  class="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning"
                >
                  <LucideTrendingDown class="size-3" aria-hidden="true" />
                  {{ __("{0} behind", String(standingCount.behind)) }}
                </span>
              </div>
            </header>
            <PartError :message="errors.people" class="m-4" />
            <p
              v-if="people && !people.length"
              class="px-4 py-10 text-center text-sm text-ink-gray-6"
            >
              {{
                __(
                  "No salespeople to show. Pick them in Settings → Agents → Department wall → Sales team."
                )
              }}
            </p>
            <div v-else-if="people" class="overflow-x-auto">
              <table class="w-full min-w-[46rem] text-sm">
                <thead>
                  <tr
                    class="h-11 bg-surface-gray-1 text-left text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
                  >
                    <th scope="col" class="pl-4 pr-3">{{ __("Person") }}</th>
                    <th scope="col" class="px-3">{{ periodWord.calls }}</th>
                    <th scope="col" class="px-3">{{ __("Contacted") }}</th>
                    <th scope="col" class="px-3">{{ __("Contact rate") }}</th>
                    <template v-if="hasTargets">
                      <th scope="col" class="px-3">
                        {{ __("Target progress") }}
                      </th>
                      <th scope="col" class="px-3">{{ __("Status") }}</th>
                    </template>
                    <th scope="col" class="pl-3 pr-4">
                      <span class="sr-only">{{ __("Leads") }}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in people"
                    :key="row.user"
                    class="h-16 border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1"
                  >
                    <th scope="row" class="pl-4 pr-3 text-left font-normal">
                      <span class="flex items-center gap-2.5">
                        <PersonAvatar :name="row.full_name" size="lg" />
                        <span class="font-semibold text-ink-gray-9">{{
                          row.full_name
                        }}</span>
                      </span>
                    </th>
                    <td class="px-3">
                      <span class="tabular-nums text-ink-gray-9">
                        <b>{{ row.called }}</b>
                        <span v-if="row.given" class="text-ink-gray-6">
                          / {{ row.given }}</span
                        >
                      </span>
                      <span
                        v-if="row.given"
                        class="mt-1.5 block h-1.5 w-32 overflow-hidden rounded-full bg-surface-gray-2"
                        role="meter"
                        :aria-valuenow="percent(row.called, row.given)"
                        aria-valuemin="0"
                        aria-valuemax="100"
                        :aria-label="__('Share of handed-out calls made')"
                      >
                        <span
                          class="block h-full rounded-full bg-brand"
                          :style="{
                            width: `${Math.min(
                              percent(row.called, row.given),
                              100
                            )}%`,
                          }"
                        />
                      </span>
                    </td>
                    <td class="px-3 font-semibold tabular-nums text-ink-gray-9">
                      {{ row.contacted }}
                    </td>
                    <td class="px-3 tabular-nums text-ink-gray-8">
                      {{ percent(row.contacted, row.called) }}%
                    </td>
                    <template v-if="hasTargets">
                      <td class="px-3">
                        <span
                          v-if="targetOf(row.user)?.percent != null"
                          class="flex items-center gap-2"
                        >
                          <TargetRing
                            class="!size-10 [&_svg]:!size-10"
                            :actual="targetOf(row.user)!.percent!"
                            :target="100"
                            :tone="targetOf(row.user)!.behind ? 'warning' : 'success'"
                            :status-text="targetOf(row.user)!.behind ? __('behind') : __('on track')"
                            :text="`${targetOf(row.user)!.percent}%`"
                          />
                          <span class="text-xs text-ink-gray-6">
                            {{ __("of {0} targets", monthTitle(monthValue())) }}
                          </span>
                        </span>
                        <span v-else class="text-xs text-ink-gray-5">
                          {{ __("No targets") }}
                        </span>
                      </td>
                      <td class="px-3">
                        <span
                          v-if="targetOf(row.user)?.percent != null"
                          class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
                          :class="
                            targetOf(row.user)!.behind
                              ? 'bg-warning-soft text-warning'
                              : 'bg-success-soft text-success'
                          "
                        >
                          {{
                            targetOf(row.user)!.behind
                              ? __("Behind")
                              : __("On track")
                          }}
                        </span>
                      </td>
                    </template>
                    <td class="pl-3 pr-4 text-right">
                      <CardLink
                        :to="{
                          name: 'Leads',
                          query: {
                            view: 'all',
                            ...narrowQuery,
                            owner: row.user,
                          },
                        }"
                      >
                        {{ __("Leads") }}
                      </CardLink>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <div class="grid grid-cols-1 gap-4 lg:grid-cols-5">
            <!-- Lead funnel: how the period's new leads moved on -->
            <section
              class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 lg:col-span-3"
              :aria-labelledby="ids.funnel"
            >
              <header class="flex items-center justify-between gap-3">
                <h2
                  :id="ids.funnel"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Lead funnel") }}
                </h2>
                <CardLink :to="{ name: 'Leads', query: { view: 'overview' } }">
                  {{ __("Full overview") }}
                </CardLink>
              </header>
              <ol class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
                <li v-for="(step, index) in funnel" :key="step.step">
                  <RouterLink
                    :to="metricLink(step.metric, periodQuery)"
                    class="flex h-full flex-col gap-1.5 rounded-lg border border-outline-gray-2 p-3 hover:border-outline-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  >
                    <span class="text-xs text-ink-gray-6">{{
                      step.label
                    }}</span>
                    <span
                      class="text-xl font-bold tabular-nums text-ink-gray-9"
                      >{{ step.count }}</span
                    >
                    <span
                      class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                    >
                      <span
                        class="block h-full rounded-full bg-brand"
                        :style="{
                          width: `${
                            index ? step.share : step.count ? 100 : 0
                          }%`,
                        }"
                      />
                    </span>
                    <span class="text-2xs tabular-nums text-ink-gray-6">{{
                      index
                        ? __(
                            "{0}% of {1}",
                            String(step.share),
                            funnel[index - 1].label.toLowerCase()
                          )
                        : periodWord.came
                    }}</span>
                  </RouterLink>
                </li>
              </ol>
              <p
                v-if="biggestDrop"
                class="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning"
              >
                <LucideTriangleAlert
                  class="mt-0.5 size-4 shrink-0"
                  aria-hidden="true"
                />
                {{ biggestDrop }}
              </p>
            </section>

            <!-- Calls this week, ranked -->
            <section
              class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 lg:col-span-2"
              :aria-labelledby="ids.board"
            >
              <header class="flex items-center justify-between gap-3">
                <h2
                  :id="ids.board"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Calls this week") }}
                </h2>
                <span class="text-xs text-ink-gray-6">{{
                  __("Leaderboard")
                }}</span>
              </header>
              <p
                v-if="!leaderboard.length"
                class="py-8 text-center text-sm text-ink-gray-6"
              >
                {{ __("No calls this week yet.") }}
              </p>
              <ol v-else class="flex flex-col gap-3">
                <li
                  v-for="(row, index) in leaderboard"
                  :key="row.user"
                  class="flex items-center gap-3"
                >
                  <span
                    class="grid size-6 shrink-0 place-items-center rounded-full bg-surface-gray-2 text-xs font-semibold tabular-nums text-ink-gray-8"
                    >{{ index + 1 }}</span
                  >
                  <PersonAvatar :name="row.full_name" />
                  <span class="flex min-w-0 flex-1 flex-col gap-1">
                    <span
                      class="flex items-center justify-between gap-2 text-sm"
                    >
                      <span class="truncate font-semibold text-ink-gray-9">{{
                        row.full_name
                      }}</span>
                      <b class="tabular-nums text-ink-gray-9">{{
                        row.calls
                      }}</b>
                    </span>
                    <span
                      class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                    >
                      <span
                        class="block h-full rounded-full bg-brand"
                        :style="{
                          width: `${percent(row.calls, leaderboard[0].calls)}%`,
                        }"
                      />
                    </span>
                  </span>
                </li>
              </ol>
            </section>
          </div>

          <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <!-- Leads handed out today, by slot -->
            <section
              class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="ids.handed"
            >
              <header class="flex items-center justify-between gap-3">
                <h2
                  :id="ids.handed"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Leads handed out today") }}
                </h2>
                <CardLink v-if="canAssign" :to="{ name: 'AssignLeads' }">
                  {{ __("Assign") }}
                </CardLink>
              </header>
              <PartError :message="errors.handed_out" />
              <p v-if="source && handedOut" class="text-xs text-ink-gray-6">
                {{ __("All sources: batches aren't counted by source.") }}
              </p>
              <p
                v-if="handedOut && !handedOut.length"
                class="py-8 text-center text-sm text-ink-gray-6"
              >
                {{ __("No call batches handed out yet today.") }}
              </p>
              <ul v-else-if="handedOut" class="divide-y divide-outline-gray-1">
                <li
                  v-for="slot in handedOut"
                  :key="`${slot.slot}-${slot.department}`"
                  class="grid grid-cols-[minmax(8rem,10rem)_1fr_4.5rem] items-center gap-3 py-2.5 text-sm"
                >
                  <span class="truncate">
                    <b class="text-ink-gray-9">{{ slot.slot }}</b>
                    <span class="text-ink-gray-6">
                      · {{ slot.department }}</span
                    >
                  </span>
                  <span
                    class="block h-2 overflow-hidden rounded-full bg-surface-gray-2"
                  >
                    <span
                      class="block h-full rounded-full"
                      :class="
                        slot.called >= slot.size ? 'bg-success' : 'bg-brand'
                      "
                      :style="{ width: `${percent(slot.called, slot.size)}%` }"
                    />
                  </span>
                  <span class="text-right text-xs tabular-nums text-ink-gray-7">
                    <b class="text-ink-gray-9"
                      >{{ slot.called }} / {{ slot.size }}</b
                    >
                    {{ __("called") }}
                  </span>
                </li>
              </ul>
            </section>

            <!-- Needs a nudge: what is waiting on a person -->
            <section
              class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="ids.nudge"
            >
              <h2
                :id="ids.nudge"
                class="text-base font-semibold text-ink-gray-9"
              >
                {{ __("Needs a nudge") }}
              </h2>
              <RouterLink
                :to="metricLink('overdue', ownerQuery)"
                class="flex items-center gap-3 rounded-lg bg-danger-soft px-3 py-3 text-sm text-danger hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >
                <LucideAlarmClock class="size-4 shrink-0" aria-hidden="true" />
                <span class="flex-1">
                  <b class="tabular-nums">{{ totals.overdue }}</b>
                  {{ __("follow-ups overdue") }}
                </span>
                <span class="font-medium">{{ __("Open") }} →</span>
              </RouterLink>
              <RouterLink
                :to="metricLink('stale', ownerQuery)"
                class="flex items-center gap-3 rounded-lg bg-warning-soft px-3 py-3 text-sm text-warning hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >
                <LucideMoon class="size-4 shrink-0" aria-hidden="true" />
                <span class="flex-1">
                  <b class="tabular-nums">{{ totals.stale }}</b>
                  {{
                    __(
                      "leads gone quiet ({0}+ days)",
                      String(overview.stale_days)
                    )
                  }}
                </span>
                <span class="font-medium">{{ __("Re-engage") }} →</span>
              </RouterLink>
              <div v-if="overview.ai.enabled" class="flex flex-wrap gap-1.5">
                <RouterLink
                  v-for="chip in aiChips"
                  :key="chip.metric"
                  :to="metricLink(chip.metric, ownerQuery)"
                  class="rounded-full px-2.5 py-1 text-xs font-medium tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  :class="chip.class"
                >
                  {{ chip.label }}
                </RouterLink>
              </div>
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
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import TargetRing from "@/pages/leads/TargetRing.vue";
import {
  choices,
  leadOptions,
  loadLeadOptions,
  usableDepartments,
  type LeadOptions,
} from "@/pages/leads/leads";
import { useChartColors } from "@/pages/performance/chartTheme";
import {
  monthTitle,
  monthValue,
  overallOf,
  type Progress,
  type TeamTargets,
} from "@/pages/sales-targets/salesTargets";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { useDocumentVisibility, useIntervalFn } from "@vueuse/core";
import { computed, useId, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideFlame from "~icons/lucide/flame";
import LucideLock from "~icons/lucide/lock";
import LucideMoon from "~icons/lucide/moon";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSend from "~icons/lucide/send";
import LucideTrendingDown from "~icons/lucide/trending-down";
import LucideTrendingUp from "~icons/lucide/trending-up";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import CardLink from "./CardLink.vue";
import DonutChart, { type DonutPart } from "./DonutChart.vue";
import PartError from "./PartError.vue";
import {
  metricLink,
  openStages,
  percent,
  total,
  type TeamDashboard,
  type TeamPeriod,
} from "./salesDashboard";
import WeekLineChart, { type WeekLine } from "./WeekLineChart.vue";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const colors = useChartColors();
const ownerId = useId();
const ids = {
  week: useId(),
  pipeline: useId(),
  team: useId(),
  funnel: useId(),
  board: useId(),
  handed: useId(),
  nudge: useId(),
};
loadLeadOptions();

const PERIODS = [
  { label: __("Today"), value: "today" },
  { label: __("This week"), value: "week" },
  { label: __("This month"), value: "month" },
];

// the period, the person, the department and the source are in the URL, so a link or a
// reload opens the same view
const period = computed<TeamPeriod>(() =>
  ["today", "week", "month"].includes(String(route.query.period))
    ? (route.query.period as TeamPeriod)
    : "today"
);
const owner = computed(() => String(route.query.owner || ""));
const department = computed(() => String(route.query.department || ""));
const source = computed(() => String(route.query.source || ""));
function setQuery(query: Record<string, string | undefined>) {
  router.replace({ query: { ...route.query, ...query } });
}
function params() {
  return {
    period: period.value,
    owner: owner.value || null,
    department: department.value || null,
    source: source.value || null,
  };
}

const dash = createResource<TeamDashboard>({
  url: "helpdesk.api.sales_dashboard.get_team_dashboard",
  makeParams: params,
  auto: true,
});
watch([period, owner, department, source], () => dash.reload());
// the day moves on: read again every two minutes and when the person comes back to the tab
useIntervalFn(() => !dash.loading && dash.reload(), 120_000);
const visibility = useDocumentVisibility();
watch(
  visibility,
  (state) => state === "visible" && !dash.loading && dash.reload()
);
function refresh() {
  dash.submit({ ...params(), fresh: 1 });
}
const isRefusal = computed(() => dash.error?.exc_type === "PermissionError");

const data = computed(() => dash.data);
const overview = computed(() => data.value!.overview);
const totals = computed(() => overview.value.totals);
const errors = computed(() => data.value?.errors ?? {});
const people = computed(() => data.value?.people ?? null);
const week = computed(() => data.value?.week ?? null);
const handedOut = computed(() => data.value?.handed_out ?? null);

const canAssign = computed(
  () =>
    !!leadOptions.data?.departments?.some(
      (d: { call_batches_enabled?: boolean }) => d.call_batches_enabled
    )
);

const periodWord = computed(
  () =>
    ({
      today: {
        came: __("came in today"),
        team: __("Your team today"),
        calls: __("Calls today"),
      },
      week: {
        came: __("came in this week"),
        team: __("Your team this week"),
        calls: __("Calls this week"),
      },
      month: {
        came: __("came in this month"),
        team: __("Your team this month"),
        calls: __("Calls this month"),
      },
    }[period.value])
);
// the Leads list opens with the same department, source, period and person; today's state
// needs no period
const narrowQuery = computed(() => ({
  department: department.value || undefined,
  source: source.value || undefined,
}));
const ownerQuery = computed(() => ({
  ...narrowQuery.value,
  owner: owner.value || undefined,
}));
const periodQuery = computed(() => ({
  ...ownerQuery.value,
  period: period.value,
}));
function stageLink(stage: string) {
  return {
    name: "Leads",
    query: { view: "all", stage, ...ownerQuery.value },
  };
}

const options = computed(() => leadOptions.data as LeadOptions | undefined);
// no picker for one department or none: there is nothing to choose between
const departmentOptions = computed(() => {
  const list = usableDepartments(options.value, department.value);
  return list.length > 1
    ? [
        { label: __("Any department"), value: "" },
        ...list.map((d) => ({ label: d.name, value: d.name })),
      ]
    : [];
});
const sourceOptions = computed(() =>
  choices(options.value?.sources, __("Any source"))
);

const ownerOptions = computed(() => [
  {
    label: __(
      "Everyone · {0} people",
      String(data.value?.overview.people.length ?? 0)
    ),
    value: "",
  },
  ...(data.value?.overview.people ?? []).map((p) => ({
    label: p.full_name,
    value: p.user,
  })),
]);

// the four biggest open stages in the categorical colours, in fixed order; the rest as one
const PIPELINE_PARTS = 4;
const pipelineParts = computed<(DonutPart & { stage?: string })[]>(() => {
  const stages = [...openStages(overview.value.pipeline)].sort(
    (a, b) => b.count - a.count
  );
  const top = stages.slice(0, PIPELINE_PARTS).map((row, i) => ({
    stage: row.stage,
    label: row.stage,
    value: row.count,
    color: colors.value.series[i],
  }));
  const rest = total(stages.slice(PIPELINE_PARTS).map((row) => row.count));
  return rest
    ? [
        ...top,
        {
          label: __("Other open stages"),
          value: rest,
          color: colors.value.other,
        },
      ]
    : top;
});
const pipelineTotal = computed(() =>
  total(pipelineParts.value.map((p) => p.value))
);

// each person's line, coloured by their place in the team list so a filter never repaints them
const weekPeople = computed(() =>
  (week.value?.people ?? []).filter((p) => total(p.called) > 0)
);
const weekLines = computed<WeekLine[]>(() =>
  [...weekPeople.value]
    .sort((a, b) => total(b.called) - total(a.called))
    .slice(0, colors.value.series.length)
    .map((p) => {
      const place = (week.value?.people ?? []).findIndex(
        (q) => q.user === p.user
      );
      return {
        name: p.full_name,
        values: p.called,
        color: colors.value.series[place % colors.value.series.length],
      };
    })
);
const leaderboard = computed(() =>
  (week.value?.people ?? [])
    .map((p) => ({
      user: p.user,
      full_name: p.full_name,
      calls: total(p.called),
    }))
    .filter((p) => p.calls > 0)
    .sort((a, b) => b.calls - a.calls)
);

const FUNNEL_STEPS: Record<string, { label: string; metric: string }> = {
  created: { label: __("New leads"), metric: "new" },
  contacted: { label: __("Contacted"), metric: "contacted" },
  meeting: { label: __("Meetings held"), metric: "meetings" },
  proposal: { label: __("Proposals sent"), metric: "quotations" },
  won: { label: __("Won"), metric: "won" },
};
const funnel = computed(() =>
  overview.value.funnel
    .filter((row) => row.step in FUNNEL_STEPS)
    .map((row, index, rows) => ({
      ...row,
      ...FUNNEL_STEPS[row.step],
      share: index ? percent(row.count, rows[index - 1].count) : 100,
    }))
);
// the step where most leads are lost, said in words
const biggestDrop = computed(() => {
  let worst: { from: string; to: string; count: number; of: number } | null =
    null;
  funnel.value.forEach((step, index) => {
    if (!index) return;
    const before = funnel.value[index - 1];
    if (!before.count) return;
    if (!worst || step.count / before.count < worst.count / worst.of)
      worst = {
        from: before.label.toLowerCase(),
        to: step.label.toLowerCase(),
        count: step.count,
        of: before.count,
      };
  });
  if (!worst) return "";
  const { from, to, count, of } = worst as {
    from: string;
    to: string;
    count: number;
    of: number;
  };
  return __(
    "Biggest drop: {0} of {1} {2} reached {3}.",
    String(count),
    String(of),
    from,
    to
  );
});

const aiChips = computed(() => {
  const ai = overview.value.ai;
  return [
    {
      metric: "high_intent",
      label: __("{0} high intent", String(ai.high_intent ?? 0)),
      class: "bg-warning-soft text-hot",
    },
    {
      metric: "unhappy",
      label: __("{0} unhappy", String(ai.unhappy ?? 0)),
      class: "bg-danger-soft text-danger",
    },
    {
      metric: "stage_suggested",
      label: __("{0} stage moves to check", String(ai.stage_suggested ?? 0)),
      class: "bg-info-soft text-info",
    },
  ];
});

// targets: a Sales Head sees each person's month, counted as the Sales targets page counts it
const hasTargets = computed(
  () => auth.canAssignSalesTargets && !!teamTargets.data
);
const teamTargets = createResource<TeamTargets>({
  url: "helpdesk.api.sales_targets.get_team",
  params: { month: monthValue() },
  auto: auth.canAssignSalesTargets,
});
const teamProgress = createResource<Record<string, Progress>>({
  url: "helpdesk.api.sales_targets.get_team_progress",
  params: { month: monthValue() },
  auto: auth.canAssignSalesTargets,
});
const targets = computed(() => {
  const team = teamTargets.data;
  const progress = teamProgress.data;
  const byUser: Record<string, { percent: number | null; behind: number }> = {};
  if (!team || !progress) return byUser;
  for (const person of team.people) {
    const counted = progress[person.user];
    if (person.target && counted?.state === "counted")
      byUser[person.user] = overallOf(person.target, counted, team.currency);
  }
  return byUser;
});
const targetOf = (user: string) => targets.value[user];
const standingCount = computed(() => {
  const rows = (people.value ?? [])
    .map((p) => targetOf(p.user))
    .filter((t) => t && t.percent != null);
  const behind = rows.filter((t) => t!.behind).length;
  return { behind, onTrack: rows.length - behind };
});
</script>

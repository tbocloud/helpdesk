<template>
  <div class="flex flex-col gap-4">
    <!-- the period and whose leads: kept in the URL, so a view can be shared -->
    <div
      class="flex flex-col gap-2 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
      role="group"
      :aria-label="__('Period and owner')"
    >
      <div class="flex flex-wrap items-end gap-3">
        <div class="overflow-x-auto">
          <TabButtons
            :model-value="period"
            size="md"
            :aria-label="__('Period')"
            :options="PERIODS"
            @update:model-value="setPeriod($event as OverviewPeriod)"
          />
        </div>
        <template v-if="period === 'custom'">
          <FormControl
            v-model="custom.from"
            type="date"
            class="w-40"
            :label="__('From')"
          />
          <FormControl
            v-model="custom.to"
            type="date"
            class="w-40"
            :label="__('To')"
          />
        </template>
        <label
          v-if="data && data.scope !== 'own'"
          class="flex items-center gap-2 text-[13px] text-ink-gray-6"
        >
          {{ data.scope === "team" ? __("Team member") : __("Owner") }}
          <FormControl
            v-model="owner"
            type="select"
            class="w-48"
            :options="ownerOptions"
          />
        </label>
      </div>
      <p v-if="data" class="text-right text-[12px] text-ink-gray-6">
        <strong class="font-semibold text-ink-gray-9">{{
          periodParts.range
        }}</strong>
        · {{ periodParts.whose }} ·
        {{ __("tap any number to open those leads") }}
        <span v-if="overviewPage.loading" class="sr-only" aria-live="polite">{{
          __("Updating")
        }}</span>
      </p>
    </div>

    <TaskyState
      v-if="period === 'custom' && !customReady"
      class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
      :icon="LucideCalendarRange"
      :title="__('Pick both dates')"
      :message="__('Choose a from and a to date to see that period.')"
    />

    <TaskyState
      v-else-if="overviewPage.error && !data"
      class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the overview')"
      :message="
        errorText(
          overviewPage.error,
          __('Check your connection and try again.')
        )
      "
    >
      <Button :label="__('Try again')" @click="refresh()" />
    </TaskyState>

    <!-- loading: the tiles' and panels' shape is known -->
    <div
      v-else-if="!data"
      class="flex flex-col gap-5"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="h-[130px] animate-pulse rounded-xl bg-surface-gray-3" />
      <div class="h-[130px] animate-pulse rounded-xl bg-surface-gray-3" />
      <div class="grid gap-5 lg:grid-cols-[3fr_2fr]">
        <div class="h-80 animate-pulse rounded-xl bg-surface-gray-3" />
        <div class="h-80 animate-pulse rounded-xl bg-surface-gray-3" />
      </div>
    </div>

    <template v-else>
      <!-- a failed update keeps the last numbers, and says so -->
      <div
        v-if="overviewPage.error"
        role="alert"
        class="flex flex-wrap items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
      >
        <LucideCircleAlert
          class="size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        <p class="min-w-0 flex-1 text-p-sm text-ink-gray-8">
          {{
            __(
              "Couldn't update the overview: {0} These numbers may be out of date.",
              errorText(overviewPage.error, __("Check your connection."))
            )
          }}
        </p>
        <Button :label="__('Try again')" @click="refresh()" />
      </div>
      <!-- how far the period's new leads got, step by step; each number opens its leads -->
      <section class="panel p-4" :aria-labelledby="ids.progress">
        <header
          class="mb-4 flex flex-wrap items-baseline justify-between gap-2"
        >
          <h2
            :id="ids.progress"
            class="text-base font-semibold text-ink-gray-9"
          >
            {{ __("Pipeline progress") }}
          </h2>
          <span class="text-[12px] text-ink-gray-6">{{
            __("From new lead to won")
          }}</span>
        </header>
        <ol
          class="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 lg:grid-cols-5"
        >
          <li v-for="(step, index) in progress" :key="step.key">
            <router-link
              :to="step.to"
              class="group flex flex-col gap-1.5 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >
              <span
                class="flex items-center gap-2 text-[12.5px] text-ink-gray-7"
              >
                <span
                  class="grid size-5 shrink-0 place-items-center rounded-full bg-surface-gray-3 text-[10.5px] font-semibold tabular-nums text-ink-gray-7"
                  aria-hidden="true"
                  >{{ index + 1 }}</span
                >
                {{ step.label }}
              </span>
              <span
                class="text-[26px] font-bold leading-tight tabular-nums text-ink-gray-9 group-hover:text-brand-ink"
                >{{ step.value }}</span
              >
              <span
                class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-3"
                aria-hidden="true"
              >
                <span
                  class="block h-full rounded-full"
                  :class="step.key === 'won' ? 'bg-success' : 'bg-brand'"
                  :style="{ width: `${step.bar}%` }"
                />
              </span>
              <span class="text-[12px] tabular-nums text-ink-gray-6">{{
                step.note
              }}</span>
            </router-link>
          </li>
        </ol>
      </section>

      <!-- what needs a person now, each with the next move -->
      <section class="flex flex-col gap-3" :aria-labelledby="ids.attention">
        <h2 :id="ids.attention" class="text-base font-semibold text-ink-gray-9">
          {{ __("Needs attention") }}
        </h2>
        <div class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4">
          <StatTile
            v-for="cell in attentionCells"
            :key="cell.key"
            :to="cell.to"
            :label="cell.label"
            :value="cell.value"
            :icon="cell.icon"
            :icon-tone="cell.iconTone"
            :value-tone="cell.tone || 'neutral'"
          >
            <span
              class="mt-1 text-[12px] font-semibold"
              :class="cell.actionInk"
              >{{ cell.action }}</span
            >
          </StatTile>
        </div>
      </section>

      <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div class="flex min-w-0 flex-col gap-4">
          <!-- AI runs leads: the day's plan, picked from Call today, follow-ups and hot leads -->
          <section v-if="ai?.enabled" class="panel" :aria-labelledby="ids.plan">
            <header class="flex flex-col gap-3 px-4 pb-3 pt-4">
              <div class="flex items-start gap-3">
                <span
                  class="grid size-9 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand-ink"
                  aria-hidden="true"
                >
                  <LucideSparkles class="size-4" />
                </span>
                <div class="flex min-w-0 flex-col gap-0.5">
                  <h2
                    :id="ids.plan"
                    class="text-base font-semibold text-ink-gray-9"
                  >
                    {{
                      owner && data.scope !== "own"
                        ? __("Their plan for today")
                        : __("Your plan for today")
                    }}
                  </h2>
                  <span class="text-[12px] text-ink-gray-6">{{
                    __(
                      "Follow-ups due, Call today and hot leads, each with the AI's next step"
                    )
                  }}</span>
                </div>
              </div>
              <nav
                class="flex flex-wrap gap-2"
                :aria-label="__('What the AI sees')"
              >
                <router-link
                  v-for="count in AI_COUNTS"
                  :key="count.metric"
                  :to="list(count.metric, false)"
                  class="inline-flex h-7 items-center rounded-full px-3 text-[12px] font-semibold tabular-nums transition-colors hover:brightness-95"
                  :class="count.tone"
                  >{{ count.label(ai[count.metric] ?? 0) }}</router-link
                >
              </nav>
            </header>
            <p
              v-if="!ai.ai_ready"
              class="border-t border-outline-gray-1 px-4 py-3 text-p-sm text-ink-gray-6"
            >
              {{
                __(
                  "The AI isn't set up on the ERP site, so there are no new next steps. Ask an admin to add a provider in TBO Smart Settings."
                )
              }}
            </p>
            <p
              v-if="!ai.plan?.rows.length"
              class="border-t border-outline-gray-1 px-4 py-4 text-p-sm text-ink-gray-6"
            >
              {{
                __("Nothing due today: no follow-ups and no hot leads waiting.")
              }}
            </p>
            <ol
              v-else
              role="list"
              class="divide-y divide-outline-gray-1 border-t border-outline-gray-1"
            >
              <li
                v-for="row in ai.plan.rows"
                :key="row.name"
                class="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start"
              >
                <div class="flex min-w-0 flex-1 items-start gap-3">
                  <PersonAvatar
                    :name="row.lead_name || row.name"
                    size="lg"
                    neutral
                  />
                  <div class="flex min-w-0 flex-col items-start gap-1.5">
                    <router-link
                      :to="{ name: 'Lead', params: { leadId: row.name } }"
                      class="truncate rounded text-[13px] font-semibold text-ink-gray-9 hover:text-brand-ink"
                      >{{ row.lead_name || row.name }}</router-link
                    >
                    <span
                      v-if="row.why"
                      class="inline-flex h-[22px] items-center rounded-md px-2 text-[11px] font-semibold"
                      :class="
                        /overdue/i.test(row.why)
                          ? 'bg-danger-soft text-danger'
                          : 'bg-surface-gray-3 text-ink-gray-7'
                      "
                      >{{ row.why }}</span
                    >
                    <span
                      v-if="row.tbo_stage"
                      class="inline-flex h-[22px] items-center rounded-md px-2 text-[11px] font-semibold"
                      :class="stagePillClass(leadOptions.data, row.tbo_stage)"
                      >{{ stageLabel(leadOptions.data, row.tbo_stage) }}</span
                    >
                    <Button
                      variant="solid"
                      :label="__('Open')"
                      :route="{ name: 'Lead', params: { leadId: row.name } }"
                      class="mt-1"
                    >
                      <template #prefix>
                        <LucidePhone class="size-3.5" aria-hidden="true" />
                      </template>
                    </Button>
                  </div>
                </div>
                <div
                  class="flex min-w-0 gap-2 rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5 sm:w-[46%] sm:shrink-0"
                >
                  <LucideSparkles
                    class="mt-0.5 size-3.5 shrink-0 text-ink-gray-6"
                    aria-hidden="true"
                  />
                  <div class="flex min-w-0 flex-col gap-0.5">
                    <span
                      class="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-gray-6"
                      >{{ __("Next step") }}</span
                    >
                    <span
                      class="text-[12.5px]"
                      :class="
                        row.next_action ? 'text-ink-gray-8' : 'text-ink-gray-6'
                      "
                    >
                      {{
                        row.next_action || __("No next step from the AI yet")
                      }}
                      <span
                        v-if="row.next_action && row.next_due"
                        class="tabular-nums text-ink-gray-6"
                      >
                        · {{ dayjs(row.next_due).format("D MMM") }}</span
                      >
                    </span>
                  </div>
                </div>
              </li>
            </ol>
          </section>
          <!-- the pipeline now, stage by stage: every open lead where it sits -->
          <section class="panel" :aria-labelledby="ids.pipeline">
            <header class="panel-head">
              <h2
                :id="ids.pipeline"
                class="text-base font-semibold text-ink-gray-9"
              >
                {{ __("Pipeline by stage") }}
              </h2>
              <span class="font-mono text-sm tabular-nums text-ink-gray-7">
                {{ __("{0} open", String(t.open)) }}
                <template v-if="t.open_value">
                  · {{ amount(t.open_value) }}</template
                >
              </span>
            </header>
            <ul role="list" class="flex flex-col py-1">
              <li v-for="row in pipeline" :key="row.stage">
                <router-link
                  :to="stageLink(row.stage)"
                  class="row-link grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-5 py-2 sm:grid-cols-[12rem_minmax(0,1fr)_auto]"
                >
                  <span class="truncate text-sm text-ink-gray-8">{{
                    row.stage
                  }}</span>
                  <span
                    class="order-last col-span-2 block h-1.5 overflow-hidden rounded-full bg-surface-gray-2 sm:order-none sm:col-span-1"
                    aria-hidden="true"
                  >
                    <span
                      class="block h-full rounded-full bg-surface-gray-7"
                      :style="{ width: `${share(row.count, pipelineMax)}%` }"
                    />
                  </span>
                  <span
                    class="text-right font-mono text-sm tabular-nums text-ink-gray-9"
                  >
                    {{ row.count }}
                    <span
                      v-if="row.value"
                      class="block text-xs text-ink-gray-6 sm:ml-2 sm:inline"
                      >{{ amount(row.value) }}</span
                    >
                  </span>
                </router-link>
              </li>
            </ul>
          </section>
        </div>

        <div class="flex min-w-0 flex-col gap-4">
          <!-- who took the period's new leads, the strip the lists show above them -->
          <LeadIntakeStrip
            v-if="intake?.available"
            :intake="intake"
            people-only
          />

          <!-- the pipeline in two numbers, and the way to it -->
          <section
            class="panel flex flex-col gap-3 p-4"
            :aria-labelledby="ids.pipelineNow"
          >
            <h2
              :id="ids.pipelineNow"
              class="text-base font-semibold text-ink-gray-9"
            >
              {{ __("Pipeline now") }}
            </h2>
            <div class="grid grid-cols-2 gap-2.5">
              <router-link
                :to="list('open', false)"
                class="flex flex-col gap-1 rounded-lg bg-surface-gray-2 px-3 py-2.5 transition-colors hover:bg-surface-gray-3"
              >
                <span class="text-[12px] text-ink-gray-6">{{
                  __("Open leads")
                }}</span>
                <span
                  class="text-[22px] font-bold tabular-nums text-ink-gray-9"
                  >{{ t.open.toLocaleString() }}</span
                >
              </router-link>
              <div
                class="flex flex-col gap-1 rounded-lg bg-surface-gray-2 px-3 py-2.5"
                :title="__('Won of the leads closed in this period')"
              >
                <span class="text-[12px] text-ink-gray-6">{{
                  __("Win rate")
                }}</span>
                <span class="text-[22px] font-bold tabular-nums text-ink-gray-9"
                  >{{ t.win_rate }}%</span
                >
              </div>
            </div>
            <a
              :href="`#${ids.pipeline}`"
              class="text-[12px] font-semibold text-brand-ink hover:text-brand-ink-hover"
              >{{ __("Every stage") }} <span aria-hidden="true">↓</span></a
            >
          </section>

          <!-- why leads were lost -->
          <section class="panel" :aria-labelledby="ids.lost">
            <header class="panel-head">
              <h2
                :id="ids.lost"
                class="text-base font-semibold text-ink-gray-9"
              >
                {{ __("Why leads were lost") }}
              </h2>
            </header>
            <p
              v-if="!data.lost_reasons.length"
              class="px-4 py-3 text-p-sm text-ink-gray-6"
            >
              {{ __("No leads lost in this period.") }}
            </p>
            <ul v-else role="list" class="flex flex-col py-1">
              <li
                v-for="r in data.lost_reasons.slice(0, 5)"
                :key="r.reason"
                class="flex items-center justify-between gap-3 px-5 py-1.5 text-sm"
              >
                <span class="truncate text-ink-gray-8">{{ r.reason }}</span>
                <span class="font-mono tabular-nums text-ink-gray-9">{{
                  r.count
                }}</span>
              </li>
            </ul>
          </section>
        </div>
      </div>

      <!-- proposals and the money after them; hidden until the ERP site has it -->
      <LeadsMoney
        v-if="proposalMoney?.available || moneyError"
        :money="proposalMoney ?? undefined"
        :error="moneyError"
        :loading="overviewPage.loading"
        :owner-picked="!!owner || data.scope === 'own'"
        :proposals-link="list('quotations')"
        :won-link="list('won')"
        @retry="refresh()"
      />

      <!-- the hottest leads, to call first -->
      <section
        v-if="data.hot.rows.length"
        class="panel"
        :aria-labelledby="ids.hot"
      >
        <header class="panel-head">
          <h2 :id="ids.hot" class="text-base font-semibold text-ink-gray-9">
            {{ __("Hot leads") }}
          </h2>
          <router-link
            :to="list('hot', false)"
            class="rounded text-sm text-ink-gray-7 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            {{ __("All {0}", String(data.hot.count)) }}
          </router-link>
        </header>
        <ul role="list" class="grid sm:grid-cols-2">
          <li
            v-for="lead in data.hot.rows.slice(0, 6)"
            :key="lead.name"
            class="border-t border-outline-gray-1"
          >
            <router-link
              :to="{ name: 'Lead', params: { leadId: lead.name } }"
              class="row-link flex items-center gap-3 px-5 py-2.5"
            >
              <span class="flex min-w-0 flex-1 flex-col">
                <span class="truncate text-sm text-ink-gray-9">{{
                  lead.lead_name || lead.name
                }}</span>
                <span class="truncate text-xs text-ink-gray-6">
                  {{
                    [lead.organization, lead.status].filter(Boolean).join(" · ")
                  }}
                </span>
              </span>
              <span
                v-if="lead.lead_score != null"
                class="font-mono text-sm tabular-nums text-ink-gray-8"
                :title="__('Lead score')"
              >
                <span class="sr-only">{{ __("Score") }}</span>
                {{ lead.lead_score }}
              </span>
            </router-link>
          </li>
        </ul>
      </section>

      <!-- by owner: who did what this period -->
      <section
        v-if="data.by_owner.length > 1 || data.scope !== 'own'"
        class="panel"
        :aria-labelledby="ids.owners"
      >
        <header class="panel-head">
          <h2 :id="ids.owners" class="text-base font-semibold text-ink-gray-9">
            {{ __("By owner") }}
          </h2>
        </header>
        <p
          v-if="!data.by_owner.length"
          class="px-4 py-3 text-p-sm text-ink-gray-6"
        >
          {{ __("Nobody has leads in this period yet.") }}
        </p>
        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[36rem] text-[13px]">
            <thead>
              <tr
                class="h-11 border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
              >
                <th scope="col" class="pl-4 pr-3 md:pl-4">
                  {{ __("Owner") }}
                </th>
                <th
                  v-for="col in OWNER_COLUMNS"
                  :key="col.key"
                  scope="col"
                  class="px-3 text-right last:pr-4 md:last:pr-5"
                >
                  {{ col.label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in data.by_owner"
                :key="row.user"
                class="border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1"
              >
                <th
                  scope="row"
                  class="max-w-[16rem] py-3 pl-4 pr-3 text-left font-medium text-ink-gray-9 md:pl-4"
                >
                  <span class="flex min-w-0 items-center gap-2.5">
                    <PersonAvatar :name="row.full_name" size="md" />
                    <span class="truncate">{{ row.full_name }}</span>
                  </span>
                </th>
                <td
                  v-for="col in OWNER_COLUMNS"
                  :key="col.key"
                  class="px-3 py-3 text-right last:pr-4 md:last:pr-5"
                >
                  <router-link
                    :to="ownerLink(row.user, col.metric)"
                    class="num-link"
                    >{{ row[col.key] }}</router-link
                  >
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- segments and sources -->
      <div class="grid gap-5 md:grid-cols-2">
        <section
          v-for="block in BREAKDOWNS"
          :key="block.key"
          class="panel"
          :aria-labelledby="`${ids.prefix}-${block.key}`"
        >
          <header class="panel-head">
            <h2
              :id="`${ids.prefix}-${block.key}`"
              class="text-base font-semibold text-ink-gray-9"
            >
              {{ block.title }}
            </h2>
            <span class="text-xs text-ink-gray-6">{{
              __("New · Open · Won")
            }}</span>
          </header>
          <p
            v-if="!data[block.key].length"
            class="px-4 py-3 text-p-sm text-ink-gray-6"
          >
            {{ __("No leads to group yet.") }}
          </p>
          <ul v-else role="list" class="flex flex-col py-1">
            <li
              v-for="row in data[block.key]"
              :key="row.value || '-'"
              class="flex items-center gap-3 px-5 py-1.5 text-sm"
            >
              <span
                class="min-w-0 flex-1 truncate"
                :class="row.value ? 'text-ink-gray-8' : 'text-ink-gray-6'"
                >{{ row.value || block.none }}</span
              >
              <template v-if="row.value">
                <router-link
                  :to="fieldLink(block.field, row.value, 'new')"
                  class="num-link w-10 text-right"
                  :aria-label="__('{0} new', String(row.new))"
                  >{{ row.new }}</router-link
                >
                <router-link
                  :to="fieldLink(block.field, row.value, 'open')"
                  class="num-link w-10 text-right"
                  :aria-label="__('{0} open', String(row.open))"
                  >{{ row.open }}</router-link
                >
                <router-link
                  :to="fieldLink(block.field, row.value, 'won')"
                  class="num-link w-10 text-right"
                  :aria-label="__('{0} won', String(row.won))"
                  >{{ row.won }}</router-link
                >
              </template>
              <span
                v-else
                class="font-mono tabular-nums text-ink-gray-7"
                :aria-label="
                  __(
                    '{0} new, {1} open, {2} won',
                    String(row.new),
                    String(row.open),
                    String(row.won)
                  )
                "
                >{{ row.new }} · {{ row.open }} · {{ row.won }}</span
              >
            </li>
          </ul>
        </section>
      </div>

      <!-- how well people call and which leads pick up; hidden until the ERP site has it -->
      <LeadsAnalysis
        v-if="analysis?.available || analysisError"
        :analysis="analysis ?? undefined"
        :error="analysisError"
        :loading="overviewPage.loading"
        @retry="refresh()"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import PersonAvatar from "@/components/PersonAvatar.vue";
import StatTile from "@/components/StatTile.vue";
import type { Tone } from "@/components/tone";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, reactive, useId, watch, type Component } from "vue";
import { useRoute, useRouter, type RouteLocationRaw } from "vue-router";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFlame from "~icons/lucide/flame";
import LucideMoon from "~icons/lucide/moon";
import LucidePhone from "~icons/lucide/phone";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideTrendingDown from "~icons/lucide/trending-down";
import LeadIntakeStrip from "./LeadIntakeStrip.vue";
import LeadsAnalysis from "./LeadsAnalysis.vue";
import LeadsMoney from "./LeadsMoney.vue";
import { leadOptions, stageLabel, stagePillClass } from "./leads";
import type {
  LeadAnalysis,
  LeadIntake,
  LeadMetric,
  LeadOverview,
  OverviewPage,
  OverviewPeriod,
  ProposalMoney,
} from "./leads";

const PERIODS: { value: OverviewPeriod; label: string }[] = [
  { value: "today", label: __("Today") },
  { value: "yesterday", label: __("Yesterday") },
  { value: "week", label: __("This week") },
  { value: "month", label: __("This month") },
  { value: "quarter", label: __("This quarter") },
  { value: "custom", label: __("Custom") },
];
const OWNER_COLUMNS: {
  key:
    | "new"
    | "contacted"
    | "meetings_held"
    | "quotations_sent"
    | "won"
    | "open";
  label: string;
  metric: LeadMetric;
}[] = [
  { key: "new", label: __("New"), metric: "new" },
  { key: "contacted", label: __("Contacted"), metric: "contacted" },
  { key: "meetings_held", label: __("Meetings"), metric: "meetings" },
  { key: "quotations_sent", label: __("Proposals"), metric: "quotations" },
  { key: "won", label: __("Won"), metric: "won" },
  { key: "open", label: __("Open"), metric: "open" },
];
const AI_COUNTS: {
  metric: "high_intent" | "unhappy" | "stage_suggested";
  label: (n: number) => string;
  /** the chip's colours; its words always say what it counts */
  tone: string;
}[] = [
  {
    metric: "high_intent",
    label: (n) => __("{0} high intent", String(n)),
    tone: "bg-warning-soft text-hot",
  },
  {
    metric: "unhappy",
    label: (n) => __("{0} unhappy", String(n)),
    tone: "bg-danger-soft text-danger",
  },
  {
    metric: "stage_suggested",
    label: (n) => __("{0} stage moves to check", String(n)),
    tone: "bg-info-soft text-info",
  },
];
const BREAKDOWNS = [
  {
    key: "by_segment" as const,
    field: "segment" as const,
    title: __("By segment"),
    none: __("No segment"),
  },
  {
    key: "by_source" as const,
    field: "source" as const,
    title: __("By source"),
    none: __("No source"),
  },
];

const route = useRoute();
const router = useRouter();
const ids = {
  prefix: useId(),
  pipeline: useId(),
  progress: useId(),
  attention: useId(),
  pipelineNow: useId(),
  lost: useId(),
  hot: useId(),
  owners: useId(),
  plan: useId(),
};

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const period = computed<OverviewPeriod>(() => {
  const value = queryValue("period");
  return PERIODS.some((p) => p.value === value)
    ? (value as OverviewPeriod)
    : "month";
});
const custom = reactive({ from: queryValue("from"), to: queryValue("to") });
const customReady = computed(
  () => !!custom.from && !!custom.to && custom.from <= custom.to
);
const owner = computed({
  get: () => queryValue("owner"),
  set: (value: string) => setQuery({ owner: value || undefined }),
});

function setQuery(query: Record<string, string | undefined>) {
  router.replace({ query: { ...route.query, ...query } });
}

function setPeriod(value: OverviewPeriod) {
  setQuery({ period: value === "month" ? undefined : value });
}

watch(
  () => ({ ...custom }),
  (c) => setQuery({ from: c.from || undefined, to: c.to || undefined })
);

// one request for the whole page: the hub and the ERP site share their workers, so
// separate reads at once wait on each other. Money and intake are optional parts.
// set only while Refresh fetches: makeParams overrides whatever is submitted
let fresh = false;
function pageParams() {
  return {
    period: period.value,
    from_date: period.value === "custom" ? custom.from : null,
    to_date: period.value === "custom" ? custom.to : null,
    owner: owner.value || null,
    fresh: fresh ? 1 : 0,
  };
}

const emit = defineEmits<{ intake: [intake: LeadIntake | undefined] }>();

const overviewPage = createResource({
  url: "helpdesk.api.leads.get_overview_page",
  makeParams: pageParams,
  onSuccess(page: OverviewPage) {
    emit("intake", page.intake ?? undefined);
  },
  onError() {
    emit("intake", undefined);
  },
});

// the refresh button and "Try again" ask the ERP site again instead of the 60-second copy
function refresh() {
  fresh = true;
  overviewPage.reload();
  fresh = false;
}

watch(
  [period, owner, () => customReady.value && `${custom.from}:${custom.to}`],
  () => {
    if (period.value !== "custom" || customReady.value) overviewPage.reload();
    // nothing is read until both dates are picked: the strip above must not keep waiting
    else emit("intake", undefined);
  },
  { immediate: true }
);

defineExpose({ reload: refresh });

const data = computed(
  () => overviewPage.data?.overview as LeadOverview | undefined
);
const proposalMoney = computed(
  () => overviewPage.data?.money as ProposalMoney | null | undefined
);
const moneyError = computed(() => {
  const message = overviewPage.data?.errors?.money;
  return message ? { message } : undefined;
});
const analysis = computed(
  () => overviewPage.data?.analysis as LeadAnalysis | null | undefined
);
const analysisError = computed(() => {
  const message = overviewPage.data?.errors?.analysis;
  return message ? { message } : undefined;
});
const t = computed(() => data.value!.totals);
const ai = computed(() => data.value?.ai);

type Cell = {
  key: string;
  label: string;
  value: number;
  tone?: Tone;
  to: RouteLocationRaw;
  icon?: Component;
  iconTone?: Tone | "hot";
  /** the next move, under the number */
  action?: string;
  actionInk?: string;
};

const periodCells = computed<Cell[]>(() => [
  { key: "new", label: __("New leads"), value: t.value.new, to: list("new") },
  {
    key: "contacted",
    label: __("Contacted"),
    value: t.value.contacted,
    to: list("contacted"),
  },
  {
    key: "meetings",
    label: __("Meetings held"),
    value: t.value.meetings,
    to: list("meetings"),
  },
  {
    key: "quotations",
    label: __("Proposals sent"),
    value: t.value.quotations_sent,
    to: list("quotations"),
  },
  {
    key: "won",
    label: __("Won"),
    value: t.value.won,
    tone: t.value.won ? "success" : undefined,
    to: list("won"),
  },
]);
const attentionCells = computed<Cell[]>(() => [
  {
    key: "overdue",
    label: __("Overdue follow-ups"),
    value: t.value.overdue,
    tone: t.value.overdue ? "danger" : undefined,
    to: list("overdue", false),
    icon: LucideAlarmClock,
    iconTone: "danger",
    action: t.value.overdue ? __("Call these first →") : __("All caught up"),
    actionInk: t.value.overdue ? "text-danger" : "text-ink-gray-6",
  },
  {
    key: "stale",
    label: __("Gone quiet ({0}+ days)", String(data.value!.stale_days)),
    value: t.value.stale,
    tone: t.value.stale ? "warning" : undefined,
    to: list("stale", false),
    icon: LucideMoon,
    iconTone: "warning",
    action: t.value.stale ? __("Re-engage →") : __("No one has gone quiet"),
    actionInk: t.value.stale ? "text-warning" : "text-ink-gray-6",
  },
  {
    key: "hot",
    label: __("Hot leads"),
    value: t.value.hot,
    to: list("hot", false),
    icon: LucideFlame,
    iconTone: "hot",
    action: t.value.hot ? __("Close them →") : __("No hot leads yet"),
    actionInk: t.value.hot ? "text-hot" : "text-ink-gray-6",
  },
  {
    key: "lost",
    label: __("Lost this period"),
    value: t.value.lost,
    to: list("lost"),
    icon: LucideTrendingDown,
    action: t.value.lost ? __("See why →") : __("Nothing lost, nice"),
    actionInk: t.value.lost ? "text-ink-gray-7" : "text-ink-gray-6",
  },
]);

// the period's steps as the progress card draws them: each bar is the share of the step before
const PROGRESS_NOTES = [
  () => __("Came in this period"),
  (n: number) => __("{0}% of new leads", String(n)),
  (n: number) => __("{0}% of contacted", String(n)),
  (n: number) => __("{0}% of meetings", String(n)),
  (n: number) => __("{0}% of proposals", String(n)),
];
const progress = computed(() =>
  periodCells.value.map((cell, index, cells) => {
    const rate =
      index === 0
        ? cell.value
          ? 100
          : 0
        : share(cell.value, cells[index - 1].value);
    const note = PROGRESS_NOTES[index]?.(rate) ?? "";
    return {
      ...cell,
      bar: rate,
      note:
        cell.key === "won" && t.value.won_value
          ? `${note} · ${amount(t.value.won_value)}`
          : note,
    };
  })
);

// the day's new leads by person, for the side column
const intake = computed(
  () => overviewPage.data?.intake as LeadIntake | null | undefined
);

const ownerOptions = computed(() => [
  {
    label: data.value?.scope === "team" ? __("My team") : __("Everyone"),
    value: "",
  },
  ...(data.value?.people ?? []).map((p) => ({
    label: p.full_name,
    value: p.user,
  })),
]);

const periodParts = computed(() => {
  const d = data.value!;
  const from = dayjs(d.from_date);
  const to = dayjs(d.to_date);
  const range = from.isSame(to, "day")
    ? to.format("D MMM YYYY")
    : from.isSame(to, "year")
    ? `${from.format("D MMM")} – ${to.format("D MMM YYYY")}`
    : `${from.format("D MMM YYYY")} – ${to.format("D MMM YYYY")}`;
  const whose =
    d.scope === "own"
      ? __("your leads")
      : owner.value
      ? d.people.find((p) => p.user === owner.value)?.full_name || owner.value
      : d.scope === "team"
      ? __("your team's leads")
      : __("everyone's leads");
  return { range, whose };
});

// open stages, then won and lost: the pipeline reads left to right
const pipeline = computed(() =>
  (data.value?.pipeline ?? []).filter(
    (row) => row.count || !["Won", "Lost"].includes(row.type)
  )
);
const pipelineMax = computed(() =>
  Math.max(...pipeline.value.map((row) => row.count), 1)
);

function share(part: number, whole: number) {
  return whole ? Math.round((part / whole) * 100) : 0;
}

function amount(value: number) {
  const currency = data.value?.currency;
  return currency ? money(value, currency) : String(value);
}

/** The list of the leads behind one number. `inPeriod` false for today's state. */
function list(metric: LeadMetric, inPeriod = true): RouteLocationRaw {
  return {
    name: "Leads",
    query: {
      view: "all",
      metric,
      ...(inPeriod ? periodQuery() : {}),
      owner: owner.value || undefined,
    },
  };
}

function periodQuery() {
  return {
    period: period.value,
    from: period.value === "custom" ? custom.from : undefined,
    to: period.value === "custom" ? custom.to : undefined,
  };
}

function stageLink(stage: string): RouteLocationRaw {
  return {
    name: "Leads",
    query: { view: "all", stage, owner: owner.value || undefined },
  };
}

function ownerLink(user: string, metric: LeadMetric): RouteLocationRaw {
  return {
    name: "Leads",
    query: {
      view: "all",
      owner: user,
      metric,
      ...(metric === "open" ? {} : periodQuery()),
    },
  };
}

function fieldLink(
  field: "segment" | "source",
  value: string,
  metric?: LeadMetric
): RouteLocationRaw {
  return {
    name: "Leads",
    query: {
      view: "all",
      [field]: value,
      owner: owner.value || undefined,
      ...(metric
        ? { metric, ...(metric === "open" ? {} : periodQuery()) }
        : {}),
    },
  };
}
</script>

<style scoped>
/* one bordered row of cells, hairlines between them (no tiles) */
.panel {
  @apply min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base;
}
.panel-head {
  @apply flex flex-wrap items-baseline justify-between gap-2 border-b border-outline-gray-2 px-4 py-3;
}
.row-link {
  @apply transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4;
}
.num-link {
  @apply inline-block rounded font-mono tabular-nums text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4;
}
</style>

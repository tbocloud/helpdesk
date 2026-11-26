<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">{{ __("AI models") }}</h1>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="loading"
          @click="load()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div
        class="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-5 md:px-6"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <TabButtons
            :model-value="view"
            :options="views"
            :aria-label="__('View')"
            @update:model-value="go({ view: $event })"
          />
          <TabButtons
            :model-value="String(days)"
            :options="periods"
            :aria-label="__('Period')"
            @update:model-value="go({ days: $event })"
          />
        </div>

        <p
          v-if="error"
          role="alert"
          class="flex flex-wrap items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          {{ errorText(error, __("Couldn't read the AI models.")) }}
          <Button
            variant="ghost"
            size="sm"
            :label="__('Retry')"
            @click="load()"
          />
        </p>

        <div
          v-if="loading && !shown"
          class="h-64 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
          :aria-label="__('Loading')"
        />

        <!-- 1. every model side by side -->
        <template v-else-if="view === 'models' && overview">
          <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile
              :label="__('AI spend, {0} days', String(overview.days))"
              :value="money(overview.totals.cost)"
              :sub="
                overview.budget_usd
                  ? __('monthly budget {0}', money(overview.budget_usd))
                  : ''
              "
            />
            <StatTile
              :label="__('Calls')"
              :value="overview.totals.calls.toLocaleString()"
              :sub="__('{0} models', String(usedModels))"
            />
            <StatTile
              :label="__('Error rate')"
              :value="pct(overview.totals.error_rate)"
              :sub="__('{0} failed calls', String(overview.totals.failed))"
            />
            <StatTile
              :label="__('Needs attention')"
              :value="String(overview.attention.length)"
              :sub="overview.attention.join(', ') || __('all models healthy')"
            />
          </div>

          <p
            v-if="!overview.totals.calls"
            class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-6 text-center text-p-sm text-ink-gray-6"
          >
            {{ __("No AI calls in this period.") }}
          </p>

          <div class="overflow-x-auto rounded-xl border border-outline-gray-2">
            <table class="w-full min-w-[60rem] text-p-sm">
              <thead>
                <tr class="bg-surface-gray-1 text-left text-ink-gray-5">
                  <th scope="col" class="px-4 py-2.5 font-medium">
                    {{ __("Model") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Calls") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Cost") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Speed (median / slow)") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Errors") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Ran as fallback") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Our test set") }}
                  </th>
                  <th scope="col" class="px-4 py-2.5 font-medium">
                    {{ __("Status") }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="m in overview.models"
                  :key="m.model"
                  class="border-t border-outline-gray-1 align-top"
                >
                  <td class="px-4 py-3">
                    <button
                      type="button"
                      class="rounded text-left text-base-medium text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      @click="go({ view: 'model', model: m.model })"
                    >
                      {{ m.model }}
                    </button>
                    <div class="text-ink-gray-5">{{ m.provider }}</div>
                    <div
                      v-if="m.gateway_aliases && m.gateway_aliases.length"
                      class="text-ink-gray-5"
                    >
                      {{
                        __(
                          "Desktop app calls it {0}",
                          m.gateway_aliases.join(", ")
                        )
                      }}
                    </div>
                    <div class="text-ink-gray-5">{{ usedFor(m.used_for) }}</div>
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ m.calls.toLocaleString() }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ money(m.cost) }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ speed(m.p50, m.p95) }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ pct(m.error_rate) }}
                    <div class="text-ink-gray-5">{{ m.failed }}</div>
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ pct(m.fallback_rate) }}
                    <div
                      v-if="m.hub_calls !== undefined && m.hub_calls < m.calls"
                      class="text-ink-gray-5"
                    >
                      {{ __("of TBO Support's calls") }}
                    </div>
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ m.benchmark ? pct(m.benchmark.accuracy) : "-" }}
                    <div v-if="m.benchmark" class="text-ink-gray-5">
                      {{ m.benchmark.ran_on }}
                    </div>
                  </td>
                  <td class="px-4 py-3">
                    <Badge
                      :label="__(m.status)"
                      :theme="STATUS_THEME[m.status] || 'gray'"
                      size="sm"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <SectionCard :title="__('Cost by model')">
              <BarList
                class="px-4 pb-4"
                :rows="bars(overview.models, 'cost', (v) => money(v))"
              />
            </SectionCard>
            <SectionCard :title="__('Error rate by model')">
              <BarList
                class="px-4 pb-4"
                :rows="
                  bars(overview.models, 'error_rate', (v) => pct(v), 'danger')
                "
              />
            </SectionCard>
          </div>
          <p v-if="overview.recorded_since" class="text-p-xs text-ink-gray-5">
            {{
              __(
                "Speed and errors are recorded since {0}; earlier calls show cost only.",
                overview.recorded_since
              )
            }}
          </p>
        </template>

        <!-- 2. one model -->
        <template v-else-if="view === 'model'">
          <div class="flex flex-wrap items-end gap-3">
            <div class="w-full sm:w-72">
              <FormControl
                type="select"
                :label="__('Model')"
                :model-value="model"
                :options="modelOptions"
                @update:model-value="go({ model: $event })"
              />
            </div>
            <template v-if="detail">
              <Badge
                :label="__(detail.status)"
                :theme="STATUS_THEME[detail.status] || 'gray'"
                size="md"
              />
              <span class="text-p-sm text-ink-gray-5">
                {{ detail.provider }} · {{ usedFor(detail.used_for) }}
                <template
                  v-if="detail.gateway_aliases && detail.gateway_aliases.length"
                >
                  ·
                  {{
                    __(
                      "Desktop app calls it {0}",
                      detail.gateway_aliases.join(", ")
                    )
                  }}
                </template>
              </span>
            </template>
            <TabButtons
              class="ml-auto"
              :model-value="tab"
              :options="tabs"
              :aria-label="__('Analysis')"
              @update:model-value="go({ tab: $event })"
            />
          </div>

          <p v-if="!model" class="text-p-sm text-ink-gray-6">
            {{ __("Choose a model.") }}
          </p>
          <div
            v-else-if="loading && !detail"
            class="h-64 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
            :aria-label="__('Loading')"
          />
          <p
            v-if="detail && detail.status === 'Candidate'"
            class="rounded-lg bg-info-soft px-3 py-2 text-p-sm text-info"
          >
            {{
              __(
                "A candidate: no job uses it yet. Ask for a run of the test set on it, then choose it for a job in Model settings."
              )
            }}
          </p>
          <template v-if="detail">
            <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile
                :label="__('Calls')"
                :value="detail.calls.toLocaleString()"
              />
              <StatTile :label="__('Cost')" :value="money(detail.cost)" />
              <StatTile
                :label="__('Speed (median)')"
                :value="seconds(detail.p50)"
                :sub="__('slow end {0}', seconds(detail.p95))"
              />
              <StatTile
                :label="__('Error rate')"
                :value="pct(detail.error_rate)"
                :sub="__('{0} failed calls', String(detail.failed))"
              />
            </div>

            <p
              v-if="
                !detail.calls && (tab === 'performance' || tab === 'errors')
              "
              class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-6 text-center text-p-sm text-ink-gray-6"
            >
              {{ __("No calls to this model in this period.") }}
            </p>

            <template v-else-if="tab === 'performance'">
              <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <SectionCard :title="__('Cost per day (USD)')">
                  <WeekLineChart
                    class="px-4 pb-4"
                    :days="dayLabels"
                    :series="[line(__('Cost'), 'cost')]"
                    :label="__('Cost per day')"
                    area
                  />
                </SectionCard>
                <SectionCard :title="__('Calls per day')">
                  <WeekLineChart
                    class="px-4 pb-4"
                    :days="dayLabels"
                    :series="[line(__('Calls'), 'calls')]"
                    :label="__('Calls per day')"
                    area
                  />
                </SectionCard>
                <SectionCard :title="__('Speed by job (median)')">
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(detail.by_job, 'p50', (v) => seconds(v), '', 'name')
                    "
                  />
                </SectionCard>
                <SectionCard :title="__('Cost by job')">
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(detail.by_job, 'cost', (v) => money(v), '', 'name')
                    "
                  />
                </SectionCard>
                <SectionCard :title="__('Where the calls come from')">
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(
                        detail.by_source,
                        'calls',
                        (v) => String(v),
                        '',
                        'name'
                      )
                    "
                  />
                </SectionCard>
                <SectionCard
                  v-if="detail.by_person && detail.by_person.length"
                  :title="__('Desktop app: cost by person')"
                >
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(
                        detail.by_person,
                        'cost',
                        (v) => money(v),
                        '',
                        'name'
                      )
                    "
                  />
                </SectionCard>
              </div>
              <SectionCard :title="__('Slowest calls')">
                <div class="overflow-x-auto px-4 pb-4">
                  <table class="w-full min-w-[28rem] text-p-sm">
                    <thead>
                      <tr class="text-left text-ink-gray-5">
                        <th scope="col" class="py-1.5 pr-3 font-medium">
                          {{ __("When") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("Job") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("Ticket") }}
                        </th>
                        <th
                          scope="col"
                          class="py-1.5 pl-3 text-right font-medium"
                        >
                          {{ __("Seconds") }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, i) in detail.slowest"
                        :key="i"
                        class="border-t border-outline-gray-1"
                      >
                        <td class="py-1.5 pr-3">{{ row.when }}</td>
                        <td class="px-3 py-1.5">{{ row.job || "-" }}</td>
                        <td class="px-3 py-1.5">
                          <RouterLink
                            v-if="row.ticket"
                            :to="{
                              name: 'TicketAgent',
                              params: { ticketId: row.ticket },
                            }"
                            class="underline underline-offset-2"
                          >
                            #{{ row.ticket }}
                          </RouterLink>
                          <span v-else>-</span>
                        </td>
                        <td class="py-1.5 pl-3 text-right tabular-nums">
                          {{ row.seconds }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </SectionCard>
            </template>

            <template v-else-if="tab === 'errors'">
              <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <SectionCard :title="__('Error rate per day (%)')">
                  <WeekLineChart
                    class="px-4 pb-4"
                    :days="dayLabels"
                    :series="[line(__('Error rate'), 'error_rate')]"
                    :label="__('Error rate per day')"
                  />
                </SectionCard>
                <SectionCard :title="__('Errors by type')">
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(
                        detail.errors_by_kind,
                        'count',
                        (v) => String(v),
                        'danger',
                        'kind'
                      )
                    "
                    :empty="__('No errors in this period.')"
                  />
                </SectionCard>
                <SectionCard :title="__('Errors by job')">
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(
                        detail.errors_by_job,
                        'failed',
                        (v) => String(v),
                        'danger',
                        'name'
                      )
                    "
                    :empty="__('No errors in this period.')"
                  />
                </SectionCard>
              </div>
              <SectionCard :title="__('Latest errors')">
                <div class="overflow-x-auto px-4 pb-4">
                  <p
                    v-if="!detail.latest_errors.length"
                    class="text-p-sm text-ink-gray-6"
                  >
                    {{ __("No errors in this period.") }}
                  </p>
                  <table v-else class="w-full min-w-[44rem] text-p-sm">
                    <thead>
                      <tr class="text-left text-ink-gray-5">
                        <th scope="col" class="py-1.5 pr-3 font-medium">
                          {{ __("When") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("Job") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("Type") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("The provider said") }}
                        </th>
                        <th scope="col" class="py-1.5 pl-3 font-medium">
                          {{ __("Fallback") }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, i) in detail.latest_errors"
                        :key="i"
                        class="border-t border-outline-gray-1 align-top"
                      >
                        <td class="whitespace-nowrap py-1.5 pr-3">
                          {{ row.when }}
                        </td>
                        <td class="px-3 py-1.5">{{ row.job || "-" }}</td>
                        <td class="px-3 py-1.5">{{ row.kind }}</td>
                        <td class="px-3 py-1.5 text-ink-gray-6">
                          {{ row.message || "-" }}
                        </td>
                        <td class="py-1.5 pl-3">
                          <Badge
                            :label="
                              row.fallback_answered
                                ? __('Answered')
                                : __('No answer')
                            "
                            :theme="row.fallback_answered ? 'green' : 'gray'"
                            size="sm"
                          />
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </SectionCard>
            </template>

            <template v-else-if="tab === 'quality' && quality">
              <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
                <SectionCard
                  :title="__('Copilot')"
                  :description="
                    __('{0} runs in this period', String(quality.copilot.runs))
                  "
                >
                  <dl class="flex flex-col gap-2 px-4 pb-4 text-p-sm">
                    <QualityLine
                      :label="__('Fixes approved')"
                      :value="pct(quality.copilot.approval_rate)"
                      :note="
                        __('{0} decided', String(quality.copilot.approvals))
                      "
                    />
                    <QualityLine
                      :label="__('Root cause rated right')"
                      :value="pct(quality.copilot.right_rate)"
                      :note="
                        __('{0} reviewed', String(quality.copilot.reviewed))
                      "
                    />
                    <QualityLine
                      :label="__('Root cause rated wrong')"
                      :value="pct(quality.copilot.wrong_rate)"
                    />
                    <QualityLine
                      :label="__('Explanation changed by the agent')"
                      :value="pct(quality.copilot.avg_edited)"
                      :note="__('average share of the text')"
                    />
                    <QualityLine
                      :label="__('Customer said it is still broken')"
                      :value="pct(quality.copilot.still_broken_rate)"
                      :note="
                        __(
                          '{0} customers answered',
                          String(quality.copilot.customer_answers)
                        )
                      "
                    />
                    <QualityLine
                      :label="__('Runs that failed')"
                      :value="String(quality.copilot.failed)"
                    />
                  </dl>
                </SectionCard>
                <SectionCard
                  :title="__('Chat replies')"
                  :description="
                    __(
                      '{0} replies in this period',
                      String(quality.chat.replies)
                    )
                  "
                >
                  <dl class="flex flex-col gap-2 px-4 pb-4 text-p-sm">
                    <QualityLine
                      :label="__('Answered from an article')"
                      :value="pct(quality.chat.answered_rate)"
                    />
                    <QualityLine
                      :label="__('Handed to a person')"
                      :value="pct(quality.chat.handover_rate)"
                    />
                  </dl>
                </SectionCard>
                <SectionCard
                  :title="__('Draft replies')"
                  :description="
                    __(
                      '{0} drafts made for agents in this period',
                      String(quality.drafts.made)
                    )
                  "
                >
                  <dl class="flex flex-col gap-2 px-4 pb-4 text-p-sm">
                    <QualityLine
                      :label="__('Sent as written')"
                      :value="pct(quality.drafts.used_rate)"
                      :note="__('{0} replies', String(quality.drafts.used))"
                    />
                    <QualityLine
                      :label="__('Sent with changes')"
                      :value="pct(quality.drafts.changed_rate)"
                      :note="__('{0} replies', String(quality.drafts.changed))"
                    />
                    <QualityLine
                      :label="__('Not sent')"
                      :value="String(quality.drafts.not_used)"
                    />
                  </dl>
                </SectionCard>
                <SectionCard
                  :title="__('Hallucination flags')"
                  :description="
                    __('Two separate checks, never one blended number')
                  "
                >
                  <dl class="flex flex-col gap-2 px-4 pb-4 text-p-sm">
                    <QualityLine
                      :label="
                        __('Runs citing a file or field that does not exist')
                      "
                      :value="pct(quality.hallucination.missing_reference_rate)"
                      :note="
                        __(
                          '{0} runs checked, {1} missing references',
                          String(quality.hallucination.runs_checked),
                          String(quality.hallucination.missing_references)
                        )
                      "
                    />
                    <QualityLine
                      :label="__('Chat answers with no article behind them')"
                      :value="pct(quality.hallucination.unsupported_rate)"
                      :note="
                        __(
                          '{0} stopped before the customer saw them',
                          String(quality.hallucination.unsupported)
                        )
                      "
                    />
                    <QualityLine
                      :label="__('Links, prices or promises removed')"
                      :value="String(quality.hallucination.safety_cuts)"
                    />
                    <QualityLine
                      :label="__('Answers in a broken format')"
                      :value="String(quality.hallucination.bad_format)"
                    />
                  </dl>
                </SectionCard>
              </div>
              <p class="text-p-xs text-ink-gray-5">
                {{
                  __(
                    "A dash means nothing was measured yet. The reference check needs the updated Copilot worker. A draft counts as sent as written when nine tenths of it went out, and as changed from four tenths."
                  )
                }}
              </p>
            </template>

            <template v-else-if="tab === 'benchmarks' && bench">
              <p
                v-if="benchNotice"
                role="status"
                class="rounded-lg px-3 py-2 text-p-sm"
                :class="
                  benchNotice.ok
                    ? 'bg-success-soft text-success'
                    : 'bg-warning-soft text-warning'
                "
              >
                {{ benchNotice.text }}
              </p>
              <SectionCard
                :title="__('Our test set')"
                :description="
                  __('Past tickets with known answers. This is what decides.')
                "
              >
                <template #actions>
                  <div v-if="bench.can_change" class="flex flex-wrap gap-2">
                    <Button
                      :label="__('Bring in a report')"
                      :loading="benchBusy"
                      @click="reportInput?.click()"
                    />
                    <Button
                      variant="solid"
                      :label="__('Ask for a run')"
                      :loading="benchBusy"
                      :disabled="
                        bench.requests.some((r) => r.status !== 'Failed')
                      "
                      @click="runEval"
                    />
                    <input
                      ref="reportInput"
                      type="file"
                      accept=".json,application/json"
                      class="hidden"
                      :aria-label="__('Test-set report')"
                      @change="bringReport"
                    />
                  </div>
                </template>
                <div class="flex flex-col gap-4 px-4 pb-4">
                  <p class="text-p-sm text-ink-gray-6">
                    {{
                      __(
                        "The test set runs on the test hub, where its tickets are. The Copilot worker's eval command there sends the scores here, or a System Manager brings its report in."
                      )
                    }}
                  </p>
                  <div
                    v-for="r in bench.requests"
                    :key="r.name"
                    class="flex flex-wrap items-center gap-2 rounded-lg bg-surface-gray-1 px-3 py-2 text-p-sm text-ink-gray-7"
                  >
                    <span>
                      {{
                        r.status === "Failed"
                          ? __("A run failed: {0}", r.error || "")
                          : r.status === "Running"
                          ? __("A run is being done.")
                          : __(
                              "{0} asked for a run on {1}. It shows here when its scores arrive.",
                              r.requested_by,
                              String(r.creation).slice(0, 16)
                            )
                      }}
                    </span>
                    <Button
                      v-if="bench.can_change"
                      variant="ghost"
                      size="sm"
                      :label="__('Take back')"
                      :loading="benchBusy"
                      @click="withdraw(r.name)"
                    />
                  </div>
                  <p
                    v-if="!bench.runs.length"
                    class="text-p-sm text-ink-gray-6"
                  >
                    {{ __("No run of the test set on this model yet.") }}
                  </p>
                  <div v-else class="overflow-x-auto">
                    <table class="w-full min-w-[36rem] text-p-sm">
                      <thead>
                        <tr class="text-left text-ink-gray-5">
                          <th scope="col" class="py-1.5 pr-3 font-medium">
                            {{ __("Ran on") }}
                          </th>
                          <th
                            scope="col"
                            class="px-3 py-1.5 text-right font-medium"
                          >
                            {{ __("Accuracy") }}
                          </th>
                          <th
                            scope="col"
                            class="px-3 py-1.5 text-right font-medium"
                          >
                            {{ __("Right") }}
                          </th>
                          <th
                            scope="col"
                            class="px-3 py-1.5 text-right font-medium"
                          >
                            {{ __("Cost per right case") }}
                          </th>
                          <th
                            scope="col"
                            class="px-3 py-1.5 text-right font-medium"
                          >
                            {{ __("Minutes per case") }}
                          </th>
                          <th scope="col" class="py-1.5 pl-3 font-medium">
                            {{ __("From") }}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="r in bench.runs"
                          :key="r.name"
                          class="border-t border-outline-gray-1"
                        >
                          <td class="py-1.5 pr-3">{{ r.ran_on }}</td>
                          <td class="px-3 py-1.5 text-right tabular-nums">
                            {{ pct(r.accuracy) }}
                          </td>
                          <td class="px-3 py-1.5 text-right tabular-nums">
                            {{ r.cases_right }} / {{ r.cases_total }}
                          </td>
                          <td class="px-3 py-1.5 text-right tabular-nums">
                            {{
                              r.cost_per_right_case === null
                                ? "-"
                                : money(r.cost_per_right_case)
                            }}
                          </td>
                          <td class="px-3 py-1.5 text-right tabular-nums">
                            {{ r.avg_minutes }}
                          </td>
                          <td class="py-1.5 pl-3 text-ink-gray-6">
                            {{ r.source }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <template v-if="bench.cases.length">
                    <CaseGrid
                      :title="__('{0}, latest run', bench.model)"
                      :cases="bench.cases"
                    />
                    <div v-if="bench.others.length" class="flex flex-col gap-2">
                      <div class="w-full sm:w-72">
                        <FormControl
                          type="select"
                          :label="__('Head to head with')"
                          :model-value="bench.against"
                          :options="
                            bench.others.map((o) => ({ label: o, value: o }))
                          "
                          @update:model-value="go({ against: $event })"
                        />
                      </div>
                      <CaseGrid
                        :title="
                          __(
                            '{0}: {1}',
                            bench.against,
                            pct(bench.against_accuracy)
                          )
                        "
                        :cases="bench.against_cases"
                      />
                    </div>
                    <p class="text-p-xs text-ink-gray-5">
                      {{
                        __(
                          "Only case numbers are shown. The questions and the expected answers stay private."
                        )
                      }}
                    </p>
                  </template>
                </div>
              </SectionCard>

              <SectionCard
                :title="__('Public benchmarks')"
                :description="
                  __('For reference only: self-reported and often out of date')
                "
              >
                <div class="flex flex-col gap-3 px-4 pb-4">
                  <ul class="flex flex-col gap-1.5 text-p-sm">
                    <li
                      v-for="b in bench.public"
                      :key="b.name"
                      class="flex flex-wrap items-center gap-x-3 gap-y-1"
                    >
                      <span class="text-base-medium text-ink-gray-9">{{
                        b.benchmark
                      }}</span>
                      <span class="tabular-nums">{{ b.score }}</span>
                      <span class="text-ink-gray-5">{{
                        b.measured_on || __("no date")
                      }}</span>
                      <a
                        v-if="b.source_url"
                        :href="b.source_url"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="underline underline-offset-2"
                      >
                        {{ __("source") }}
                      </a>
                      <span v-if="b.note" class="text-ink-gray-6">{{
                        b.note
                      }}</span>
                      <Button
                        v-if="bench.can_change"
                        variant="ghost"
                        size="sm"
                        :label="__('Remove')"
                        @click="removePublic(b.name)"
                      />
                    </li>
                    <li v-if="!bench.public.length" class="text-ink-gray-5">
                      {{ __("None added yet.") }}
                    </li>
                  </ul>
                  <form
                    v-if="bench.can_change"
                    class="grid grid-cols-1 items-end gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_7rem_10rem_minmax(0,1fr)_auto]"
                    @submit.prevent="addPublic"
                  >
                    <FormControl
                      v-model="pub.benchmark"
                      type="text"
                      :label="__('Benchmark')"
                    />
                    <FormControl
                      v-model="pub.score"
                      type="text"
                      :label="__('Score')"
                    />
                    <FormControl
                      v-model="pub.measured_on"
                      type="date"
                      :label="__('Measured on')"
                    />
                    <FormControl
                      v-model="pub.source_url"
                      type="text"
                      :label="__('Source link')"
                      placeholder="https://"
                    />
                    <Button
                      type="submit"
                      :label="__('Add')"
                      :loading="benchBusy"
                    />
                  </form>
                </div>
              </SectionCard>
            </template>
          </template>
        </template>

        <!-- 3. model settings: providers and keys, the model list, a model and backup per job -->
        <template v-else-if="view === 'settings' && settings">
          <p class="text-p-sm text-ink-gray-6">
            {{
              settings.can_change
                ? __(
                    "Add each AI provider with its own key, allow the models TBO may use, then choose a model and a backup for each purpose of each application."
                  )
                : __("Only System Managers change these.")
            }}
          </p>

          <SectionCard
            :title="__('1. Providers and keys')"
            :description="
              __(
                'One row per provider account. A key is stored encrypted and never shown again; it never reaches the browser or the Copilot worker.'
              )
            "
          >
            <template #actions>
              <Button
                v-if="settings.can_change"
                :label="__('Add a provider')"
                @click="openProvider()"
              >
                <template #prefix>
                  <LucidePlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </template>
            <div class="flex flex-col gap-3 px-4 pb-4">
              <p
                v-if="provNotice"
                role="status"
                class="rounded-lg px-3 py-2 text-p-sm"
                :class="
                  provNotice.ok
                    ? 'bg-success-soft text-success'
                    : 'bg-warning-soft text-warning'
                "
              >
                {{ provNotice.text }}
              </p>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[52rem] text-p-sm">
                  <thead>
                    <tr class="text-left text-ink-gray-5">
                      <th scope="col" class="py-1.5 pr-3 font-medium">
                        {{ __("Provider") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("API style") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Address") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Key") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("On") }}
                      </th>
                      <th
                        scope="col"
                        class="px-3 py-1.5 text-right font-medium"
                      >
                        {{ __("Allowed models") }}
                      </th>
                      <th scope="col" class="py-1.5 pl-3">
                        <span class="sr-only">{{ __("Actions") }}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="p in settings.providers"
                      :key="p.name"
                      class="border-t border-outline-gray-1 align-middle"
                    >
                      <td class="py-2 pr-3">
                        <div class="text-base-medium text-ink-gray-9">
                          {{ p.name }}
                        </div>
                        <div v-if="p.section" class="text-ink-gray-5">
                          {{
                            __(
                              "Today's section, unchanged. Default model: {0}",
                              p.default_model || "-"
                            )
                          }}
                        </div>
                        <div v-if="p.note" class="max-w-xs text-ink-gray-6">
                          {{ p.note }}
                        </div>
                      </td>
                      <td class="px-3 py-2">{{ p.style }}</td>
                      <td class="break-all px-3 py-2 text-ink-gray-6">
                        {{ p.url || __("the SDK's own") }}
                      </td>
                      <td class="px-3 py-2">
                        <Badge
                          :label="keyLabel(p)"
                          :theme="
                            p.ready ? 'green' : p.key_set ? 'orange' : 'gray'
                          "
                          size="sm"
                        />
                      </td>
                      <td class="px-3 py-2">
                        <span v-if="p.section" class="text-ink-gray-5">
                          {{ p.ready ? __("on") : __("no key") }}
                        </span>
                        <Switch
                          v-else
                          :model-value="p.enabled"
                          :disabled="
                            !settings.can_change ||
                            !p.key_set ||
                            switching === p.name
                          "
                          @update:model-value="toggleProvider(p, $event)"
                        >
                          <template #label>
                            <span class="sr-only">{{
                              __("{0} on", p.name)
                            }}</span>
                          </template>
                        </Switch>
                      </td>
                      <td class="px-3 py-2 text-right tabular-nums">
                        {{ p.models }}
                      </td>
                      <td class="py-2 pl-3">
                        <div
                          v-if="settings.can_change"
                          class="flex flex-wrap justify-end gap-1"
                        >
                          <Button
                            variant="ghost"
                            size="sm"
                            :label="__('Test')"
                            :loading="testing === p.name"
                            :disabled="!!testing"
                            @click="testProvider(p.name)"
                          />
                          <Button
                            variant="ghost"
                            size="sm"
                            :label="__('Edit')"
                            @click="openProvider(p)"
                          />
                          <Button
                            v-if="!p.section"
                            variant="ghost"
                            size="sm"
                            :theme="
                              confirming === `provider:${p.name}`
                                ? 'red'
                                : 'gray'
                            "
                            :label="
                              confirming === `provider:${p.name}`
                                ? __('Click again to remove')
                                : __('Remove')
                            "
                            @click="removeProvider(p.name)"
                          />
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            :title="__('2. Models')"
            :description="
              __(
                'Tick a model to allow it: only ticked models can be chosen for a purpose. A monthly token limit is optional; empty means none.'
              )
            "
          >
            <template #actions>
              <Button
                v-if="settings.can_change"
                :label="__('Add a model')"
                @click="openModel()"
              >
                <template #prefix>
                  <LucidePlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </template>
            <div class="flex flex-col gap-3 px-4 pb-4">
              <p
                v-if="listNotice"
                role="status"
                class="rounded-lg px-3 py-2 text-p-sm"
                :class="
                  listNotice.ok
                    ? 'bg-success-soft text-success'
                    : 'bg-warning-soft text-warning'
                "
              >
                {{ listNotice.text }}
              </p>
              <p
                v-if="!settings.catalog.length"
                class="text-p-sm text-ink-gray-6"
              >
                {{ __("No models yet. Add a model for one of the providers.") }}
              </p>
              <div v-else class="overflow-x-auto">
                <table class="w-full min-w-[64rem] text-p-sm">
                  <thead>
                    <tr class="text-left text-ink-gray-5">
                      <th scope="col" class="py-1.5 pr-3 font-medium">
                        {{ __("Model") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Provider") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Tick to allow") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Monthly limit (millions)") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Used this month") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Price per 1M (in / out)") }}
                      </th>
                      <th
                        scope="col"
                        class="px-3 py-1.5 text-right font-medium"
                      >
                        {{ __("Our test set") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Used by") }}
                      </th>
                      <th scope="col" class="py-1.5 pl-3">
                        <span class="sr-only">{{ __("Actions") }}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="m in settings.catalog"
                      :key="`${m.model}-${formKey}`"
                      class="border-t border-outline-gray-1 align-middle"
                    >
                      <td class="py-2 pr-3">
                        <button
                          type="button"
                          class="rounded text-left text-base-medium text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                          @click="
                            go({
                              view: 'model',
                              model: m.model,
                              tab: 'benchmarks',
                            })
                          "
                        >
                          {{ m.name }}
                        </button>
                        <div v-if="m.name !== m.model" class="text-ink-gray-5">
                          {{ m.model }}
                        </div>
                      </td>
                      <td class="px-3 py-2">
                        {{ m.provider }}
                        <div
                          v-if="settings.gateway.for_all && m.listed"
                          :class="
                            m.on_gateway ? 'text-ink-gray-5' : 'text-warning'
                          "
                        >
                          {{
                            m.on_gateway
                              ? __("on the gateway")
                              : __("not on the gateway yet")
                          }}
                        </div>
                        <div v-if="!m.provider_ready" class="text-warning">
                          {{ __("no key yet, or off") }}
                        </div>
                      </td>
                      <td class="px-3 py-2">
                        <FormControl
                          type="checkbox"
                          :model-value="m.listed"
                          :aria-label="__('Allow {0} for jobs', m.model)"
                          :disabled="!settings.can_change || listBusy"
                          @update:model-value="
                            saveModel({
                              model: m.model,
                              listed: $event ? 1 : 0,
                            })
                          "
                        />
                      </td>
                      <td class="px-3 py-2">
                        <FormControl
                          type="number"
                          class="w-28"
                          :model-value="m.limit_m || ''"
                          :placeholder="__('none')"
                          :aria-label="
                            __(
                              'Monthly token limit for {0}, in millions',
                              m.model
                            )
                          "
                          :disabled="!settings.can_change || listBusy"
                          @change="
                            saveModel({
                              model: m.model,
                              limit_m: Number($event.target.value) || 0,
                            })
                          "
                        />
                      </td>
                      <td class="px-3 py-2 tabular-nums">
                        {{
                          m.limit_m
                            ? __(
                                "{0}M of {1}M",
                                String(m.used_m),
                                String(m.limit_m)
                              )
                            : __("{0}M", String(m.used_m))
                        }}
                        <div
                          v-if="m.limit_m"
                          class="mt-1 h-1.5 w-28 overflow-hidden rounded-full bg-surface-gray-2"
                          aria-hidden="true"
                        >
                          <div
                            class="h-full rounded-full"
                            :class="limitTone(m)"
                            :style="{ width: `${limitShare(m)}%` }"
                          />
                        </div>
                      </td>
                      <td class="px-3 py-2 tabular-nums">
                        {{ money(m.input_price) }} / {{ money(m.output_price) }}
                      </td>
                      <td class="px-3 py-2 text-right tabular-nums">
                        {{ m.benchmark ? pct(m.benchmark.accuracy) : "-" }}
                      </td>
                      <td class="min-w-[16rem] px-3 py-2">
                        <template v-if="m.used_by.length">
                          <div
                            v-for="u in m.used_by"
                            :key="u.application"
                            class="leading-5"
                          >
                            <span class="text-base-medium text-ink-gray-8"
                              >{{ __(u.application) }}:</span
                            >
                            {{ usedByLine(u) }}
                          </div>
                        </template>
                        <Badge
                          v-else-if="m.listed"
                          :label="__('Candidate')"
                          theme="blue"
                          size="sm"
                        />
                        <span v-else class="text-ink-gray-5">-</span>
                      </td>
                      <td class="py-2 pl-3">
                        <div
                          v-if="settings.can_change"
                          class="flex flex-wrap justify-end gap-1"
                        >
                          <Button
                            variant="ghost"
                            size="sm"
                            :label="__('Edit')"
                            @click="openModel(m)"
                          />
                          <Button
                            v-if="!m.in_use"
                            variant="ghost"
                            size="sm"
                            :theme="
                              confirming === `model:${m.model}` ? 'red' : 'gray'
                            "
                            :label="
                              confirming === `model:${m.model}`
                                ? __('Click again to remove')
                                : __('Remove')
                            "
                            @click="removeModel(m.model)"
                          />
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            :title="__('3. Model and backup for each purpose')"
            :description="
              __(
                'Every application\'s purposes on one page, each chosen from the same model list. The backup answers only when the first model\'s provider can\'t (no balance, key refused, rate limit, server error, no answer in time). Both empty: the purpose works as today.'
              )
            "
          >
            <div class="flex flex-col gap-3 px-4 pb-4">
              <p
                v-if="notice"
                role="status"
                class="rounded-lg px-3 py-2 text-p-sm"
                :class="
                  notice.ok
                    ? 'bg-success-soft text-success'
                    : 'bg-warning-soft text-warning'
                "
              >
                {{ notice.text }}
              </p>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[60rem] text-p-sm">
                  <thead>
                    <tr class="text-left text-ink-gray-5">
                      <th scope="col" class="py-1.5 pr-3 font-medium">
                        {{ __("Purpose") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Model") }}
                      </th>
                      <th scope="col" class="px-3 py-1.5 font-medium">
                        {{ __("Backup (optional)") }}
                      </th>
                      <th
                        scope="col"
                        class="px-3 py-1.5 text-right font-medium"
                      >
                        {{ __("Calls") }}
                      </th>
                      <th
                        scope="col"
                        class="px-3 py-1.5 text-right font-medium"
                      >
                        {{ __("Errors") }}
                      </th>
                      <th
                        scope="col"
                        class="px-3 py-1.5 text-right font-medium"
                      >
                        {{ __("Backup answered") }}
                      </th>
                      <th
                        scope="col"
                        class="px-3 py-1.5 text-right font-medium"
                      >
                        {{ __("Cost") }}
                      </th>
                      <th scope="col" class="py-1.5 pl-3">
                        <span class="sr-only">{{ __("Test") }}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <template
                      v-for="app in settings.applications"
                      :key="app.name"
                    >
                      <tr
                        class="border-t border-outline-gray-1 bg-surface-gray-1"
                      >
                        <td colspan="8" class="px-3 py-2">
                          <span class="text-base-medium text-ink-gray-9">{{
                            __(app.name)
                          }}</span>
                          <span class="ml-2 text-ink-gray-5">{{
                            app.note
                          }}</span>
                        </td>
                      </tr>
                      <tr
                        v-for="job in jobsOf(app.name)"
                        :key="`${job.job}-${formKey}`"
                        class="border-t border-outline-gray-1 align-top"
                      >
                        <td class="py-2 pr-3">
                          <div class="text-base-medium text-ink-gray-9">
                            {{ __(job.label) }}
                          </div>
                          <div class="text-ink-gray-5">
                            {{ chainText(job) }}
                          </div>
                          <div
                            v-if="settings.guarded_jobs.includes(job.job)"
                            class="text-ink-gray-5"
                          >
                            {{
                              job.score
                                ? __("test set {0}", pct(job.score.accuracy))
                                : __("not run on the test set")
                            }}
                          </div>
                        </td>
                        <td class="w-64 px-3 py-2">
                          <FormControl
                            type="select"
                            :aria-label="__('Model for {0}', __(job.label))"
                            :model-value="job.model"
                            :options="jobModelOptions(job)"
                            :disabled="
                              !settings.can_change || saving || job.coming
                            "
                            @update:model-value="
                              save(job.job, { model: $event })
                            "
                          />
                        </td>
                        <td class="w-64 px-3 py-2">
                          <FormControl
                            type="select"
                            :aria-label="__('Backup for {0}', __(job.label))"
                            :model-value="job.backup_model"
                            :options="backupOptions(job)"
                            :disabled="
                              !settings.can_change ||
                              saving ||
                              !job.model ||
                              job.coming
                            "
                            @update:model-value="
                              save(job.job, { backup_model: $event })
                            "
                          />
                        </td>
                        <template v-if="job.coming">
                          <td
                            v-for="n in 4"
                            :key="n"
                            class="px-3 py-2 text-right text-ink-gray-5"
                          >
                            -
                          </td>
                          <td />
                        </template>
                        <template v-else>
                          <td class="px-3 py-2 text-right tabular-nums">
                            {{ job.calls.toLocaleString() }}
                          </td>
                          <td class="px-3 py-2 text-right tabular-nums">
                            {{ pct(job.error_rate) }}
                          </td>
                          <td class="px-3 py-2 text-right tabular-nums">
                            {{ pct(job.fallback_rate) }}
                          </td>
                          <td class="px-3 py-2 text-right tabular-nums">
                            {{ money(job.cost) }}
                          </td>
                          <td class="py-2 pl-3 text-right">
                            <Button
                              v-if="settings.can_change"
                              :label="__('Try')"
                              :loading="trying === job.job"
                              :disabled="!!trying"
                              @click="tryJob(job.job)"
                            />
                          </td>
                        </template>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>
              <p class="text-p-xs text-ink-gray-5">
                {{
                  __(
                    "Copilot's jobs (investigate, fix, review) run on the Copilot worker, which needs the same provider's key in its own settings. A TBO Support or worker purpose set to As today follows the sections and their fallback, as before."
                  )
                }}
              </p>
            </div>
          </SectionCard>

          <div class="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:items-start">
            <SectionCard
              :title="__('Alerts')"
              :description="__('Checked every hour on the last hour of calls')"
            >
              <div class="flex flex-col gap-3 px-4 pb-4">
                <p class="text-p-sm text-ink-gray-6">
                  {{
                    __(
                      "The managers are told when, in one hour, a model's calls fail at least this share of the time (from 10 calls), or the backup gives at least this share of the answered calls (from 10 answered calls); 0 turns an alert off. They are also told when a model reaches 80% and 100% of its monthly token limit."
                    )
                  }}
                </p>
                <p
                  v-if="alertNotice"
                  role="status"
                  class="rounded-lg px-3 py-2 text-p-sm"
                  :class="
                    alertNotice.ok
                      ? 'bg-success-soft text-success'
                      : 'bg-warning-soft text-warning'
                  "
                >
                  {{ alertNotice.text }}
                </p>
                <form
                  v-if="settings.can_change"
                  class="grid grid-cols-1 items-end gap-3 sm:grid-cols-2"
                  @submit.prevent="saveAlerts"
                >
                  <FormControl
                    v-model="alertForm.error_rate"
                    type="number"
                    :label="__('Errors, % of calls')"
                  />
                  <FormControl
                    v-model="alertForm.fallback_rate"
                    type="number"
                    :label="__('Fallback answers, % of answered calls')"
                  />
                  <div>
                    <Button
                      type="submit"
                      :label="__('Save')"
                      :loading="alertBusy"
                    />
                  </div>
                </form>
                <p v-else class="text-p-sm tabular-nums">
                  {{
                    __(
                      "Errors: {0}. Fallback answers: {1}.",
                      limitText(settings.alerts.error_rate),
                      limitText(settings.alerts.fallback_rate)
                    )
                  }}
                </p>
              </div>
            </SectionCard>
            <SectionCard :title="__('When a monthly limit is used up')">
              <p class="px-4 pb-4 text-p-sm text-ink-gray-6">
                {{
                  __(
                    "That model stops for the rest of the month and the managers are told; the backup is not used, so a limit really caps spending. A System Manager can raise the limit at any time."
                  )
                }}
              </p>
            </SectionCard>
          </div>

          <SectionCard
            :title="__('TBO AI gateway')"
            :description="
              __(
                'TBO\'s own AI gateway on the Copilot worker\'s server. The desktop app\'s AI already goes through it. With every AI call through it, the providers\' keys live there; TBO Support keeps only its OpenAI key, for emergencies.'
              )
            "
          >
            <div class="flex flex-col gap-3 px-4 pb-4">
              <p
                class="rounded-lg px-3 py-2 text-p-sm"
                :class="
                  settings.gateway.for_all && settings.gateway.down_since
                    ? 'bg-warning-soft text-warning'
                    : settings.gateway.for_all
                    ? 'bg-success-soft text-success'
                    : 'bg-surface-gray-1 text-ink-gray-7'
                "
              >
                {{
                  settings.gateway.for_all
                    ? settings.gateway.down_since
                      ? __(
                          "The gateway is not answering since {0}: TBO Support answers with its emergency key, and the managers were told.",
                          settings.gateway.down_since
                        )
                      : __(
                          "Every AI call goes through the gateway. If it stops answering, TBO Support answers with its emergency key and the managers are told."
                        )
                    : __(
                        "TBO Support and the Copilot worker call the providers straight. The desktop app already goes through the gateway."
                      )
                }}
              </p>
              <form
                v-if="settings.can_change"
                class="grid grid-cols-1 items-end gap-3 sm:grid-cols-2 lg:grid-cols-3"
                @submit.prevent="saveGateway"
              >
                <FormControl
                  v-model="gw.url"
                  type="text"
                  :label="__('Gateway address')"
                  placeholder="https://"
                />
                <FormControl
                  v-model="gw.callKey"
                  type="password"
                  :label="__('TBO Support\'s gateway key')"
                  :placeholder="
                    settings.gateway.call_key_set
                      ? __('saved; type to replace')
                      : __('from DevOps')
                  "
                  autocomplete="off"
                />
                <FormControl
                  v-model="gw.adminKey"
                  type="password"
                  :label="__('Admin key (writes the models)')"
                  :placeholder="
                    settings.gateway.admin_key_set
                      ? __('saved; type to replace')
                      : settings.gateway.admin_key_from_desktop
                      ? __('TBO Desktop Settings\' key is used')
                      : ''
                  "
                  autocomplete="off"
                />
                <FormControl
                  v-model="gw.forAll"
                  type="checkbox"
                  :label="__('Use the gateway for every AI call')"
                />
                <FormControl
                  v-model="gw.key"
                  type="password"
                  :label="__('Read-only key (the desktop app\'s usage)')"
                  :placeholder="
                    settings.gateway.key_set ? __('saved; type to replace') : ''
                  "
                  autocomplete="off"
                />
                <FormControl
                  v-model="gw.on"
                  type="checkbox"
                  :label="__('Read the desktop app\'s usage every hour')"
                />
                <div class="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-3">
                  <Button
                    type="submit"
                    variant="solid"
                    :label="__('Save')"
                    :loading="gwBusy"
                  />
                  <Button
                    :label="__('Write all to the gateway')"
                    :loading="gwBusy"
                    :disabled="!settings.gateway.url"
                    @click="writeAll"
                  />
                  <Button
                    :label="__('Read usage now')"
                    :loading="gwBusy"
                    :disabled="!settings.gateway.on"
                    @click="readGateway"
                  />
                </div>
              </form>
              <p
                v-if="gwNotice"
                role="status"
                class="rounded-lg px-3 py-2 text-p-sm"
                :class="
                  gwNotice.ok
                    ? 'bg-success-soft text-success'
                    : 'bg-warning-soft text-warning'
                "
              >
                {{ gwNotice.text }}
              </p>
              <p v-if="usageLine" class="text-p-xs text-ink-gray-5">
                {{ usageLine }}
              </p>
            </div>
          </SectionCard>

          <SectionCard :title="__('Change history')">
            <ul class="flex flex-col gap-1.5 px-4 pb-4 text-p-sm">
              <li v-for="(c, i) in settings.changes" :key="i">
                <span class="text-ink-gray-5">{{
                  String(c.creation).slice(0, 16)
                }}</span>
                · {{ c.changed_by }} ·
                <span class="text-base-medium text-ink-gray-9">{{
                  c.job
                }}</span>
                {{ c.setting }}: {{ c.old_value }} → {{ c.new_value }}
              </li>
              <li v-if="!settings.changes.length" class="text-ink-gray-5">
                {{ __("No changes yet.") }}
              </li>
            </ul>
          </SectionCard>
        </template>
      </div>
    </div>

    <Dialog
      v-model:open="guardOpen"
      :title="__('Change the model for {0}?', pending?.job || '')"
    >
      <template #default>
        <div v-if="pending" class="flex flex-col gap-3 text-p-sm">
          <p class="rounded-lg bg-warning-soft px-3 py-2 text-warning">
            {{ pending.guard.warning }}
          </p>
          <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt class="text-ink-gray-5">{{ __("Now") }}</dt>
            <dd>
              {{ pending.guard.current_model || __("not set up") }} ·
              {{ scoreText(pending.guard.current_score) }}
            </dd>
            <dt class="text-ink-gray-5">{{ __("After the change") }}</dt>
            <dd>
              {{ pending.guard.model }} · {{ scoreText(pending.guard.score) }}
            </dd>
          </dl>
          <p class="text-ink-gray-6">
            {{
              __(
                "Ask for a run of the test set on it first, or change it anyway."
              )
            }}
          </p>
        </div>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Keep it as it is')" @click="guardOpen = false" />
          <Button
            variant="solid"
            theme="red"
            :label="__('Change anyway')"
            @click="confirmGuard"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model:open="provOpen"
      :title="prov.existing ? __('Edit {0}', prov.name) : __('Add a provider')"
    >
      <template #default>
        <form class="flex flex-col gap-3" @submit.prevent="saveProvider">
          <FormControl
            v-if="!prov.existing"
            type="select"
            :label="__('Start from')"
            :model-value="prov.preset"
            :options="presetOptions"
            @update:model-value="usePreset"
          />
          <FormControl
            v-model="prov.name"
            type="text"
            :label="__('Name')"
            :disabled="prov.existing"
            :description="
              __(
                'The Copilot worker finds its own key for this provider by this name.'
              )
            "
          />
          <FormControl
            v-if="!prov.section"
            v-model="prov.style"
            type="select"
            :label="__('API style')"
            :options="STYLE_OPTIONS"
          />
          <FormControl
            v-model="prov.url"
            type="text"
            :label="__('Address')"
            :placeholder="
              prov.style === 'Anthropic'
                ? __('empty: the SDK\'s own')
                : 'https://'
            "
          />
          <FormControl
            v-model="prov.key"
            type="password"
            :label="__('API key')"
            :placeholder="prov.keySet ? __('saved; type to replace') : ''"
            :description="
              settings && settings.gateway.for_all && !prov.section
                ? __('Written to the gateway; TBO Support does not keep it.')
                : ''
            "
            autocomplete="off"
          />
          <FormControl
            v-if="prov.section"
            v-model="prov.defaultModel"
            type="text"
            :label="__('Default model')"
            :description="__('Used by the jobs set to As today.')"
          />
          <FormControl
            v-if="!prov.section && prov.style === 'OpenAI-compatible'"
            v-model="prov.jsonMode"
            type="checkbox"
            :label="__('Supports JSON mode and a token budget')"
          />
          <FormControl
            v-if="!prov.section"
            v-model="prov.note"
            type="textarea"
            :label="__('Note')"
            :description="
              __(
                'Shown under the provider\'s name, for example where its data goes.'
              )
            "
          />
          <FormControl
            v-if="!prov.section"
            v-model="prov.enabled"
            type="checkbox"
            :label="__('On')"
          />
          <p v-if="provError" role="alert" class="text-p-sm text-danger">
            {{ provError }}
          </p>
        </form>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="provOpen = false" />
          <Button
            variant="solid"
            :label="__('Save')"
            :loading="provSaving"
            @click="saveProvider"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model:open="modelOpen"
      :title="mform.existing ? __('Edit {0}', mform.model) : __('Add a model')"
    >
      <template #default>
        <form class="flex flex-col gap-3" @submit.prevent="saveModelDialog">
          <FormControl
            v-model="mform.model"
            type="text"
            :label="__('Model, as the provider writes it')"
            :disabled="mform.existing"
            placeholder="deepseek-chat"
          />
          <FormControl
            v-model="mform.name"
            type="text"
            :label="__('Name to show')"
          />
          <FormControl
            v-model="mform.provider"
            type="select"
            :label="__('Provider')"
            :options="providerOptions"
          />
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormControl
              v-model="mform.input_price"
              type="number"
              :label="__('Input, $ per 1M tokens')"
            />
            <FormControl
              v-model="mform.output_price"
              type="number"
              :label="__('Output, $ per 1M tokens')"
            />
          </div>
          <FormControl
            v-model="mform.limit_m"
            type="number"
            :label="__('Monthly token limit, millions')"
            :description="
              __(
                'Empty: no limit. When it is used up, the jobs that use this model first stop until next month.'
              )
            "
          />
          <FormControl
            v-model="mform.listed"
            type="checkbox"
            :label="__('Allowed for jobs')"
          />
          <p v-if="modelError" role="alert" class="text-p-sm text-danger">
            {{ modelError }}
          </p>
        </form>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="modelOpen = false" />
          <Button
            variant="solid"
            :label="__('Save')"
            :loading="modelSaving"
            @click="saveModelDialog"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import WeekLineChart from "@/pages/sales-dashboard/WeekLineChart.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Badge,
  Button,
  call,
  Dialog,
  FormControl,
  Switch,
  TabButtons,
  usePageMeta,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import BarList from "./BarList.vue";
import CaseGrid from "./CaseGrid.vue";
import QualityLine from "./QualityLine.vue";

const API = "helpdesk.api.ai_models";
const STATUS_THEME: Record<
  string,
  "green" | "orange" | "red" | "gray" | "blue"
> = {
  Healthy: "green",
  Degraded: "orange",
  Paused: "red",
  "Not used": "gray",
  Candidate: "blue",
};
const STYLE_OPTIONS = [
  "OpenAI",
  "OpenAI-compatible",
  "Anthropic",
  "Anthropic-compatible",
].map((style) => ({ label: style, value: style }));
// the changes that can give a Copilot job another first model
const MODEL_FIELDS = [
  "model",
  "primary_section",
  "openai_model",
  "anthropic_model",
];

type Score = { accuracy: number; ran_on: string };

type Figures = {
  calls: number;
  /** TBO Support's own calls: the fallback rate is their share, never the gateway's */
  hub_calls?: number;
  failed: number;
  error_rate: number | null;
  fallback_rate: number | null;
  cost: number;
  p50: number | null;
  p95: number | null;
};
type UsedFor = { primary: string[]; fallback: string[] };
type ModelRow = Figures & {
  benchmark?: { accuracy: number; ran_on: string } | null;
  model: string;
  provider: string;
  gateway_aliases?: string[];
  used_for: UsedFor;
  status: string;
};
type Overview = {
  days: number;
  totals: Figures;
  budget_usd: number;
  models: ModelRow[];
  attention: string[];
  recorded_since: string;
};
type Detail = ModelRow & {
  by_source: (Figures & { name: string })[];
  by_person?: (Figures & { name: string })[];
  series: { day: string; calls: number; cost: number; error_rate: number }[];
  by_job: (Figures & { name: string })[];
  errors_by_kind: { kind: string; count: number }[];
  errors_by_job: (Figures & { name: string })[];
  latest_errors: {
    when: string;
    job: string;
    kind: string;
    message: string;
    fallback_answered: boolean;
  }[];
  slowest: { when: string; job: string; ticket: string; seconds: number }[];
};
type Quality = {
  copilot: {
    runs: number;
    failed: number;
    approvals: number;
    approval_rate: number | null;
    reviewed: number;
    right_rate: number | null;
    wrong_rate: number | null;
    avg_edited: number | null;
    customer_answers: number;
    still_broken: number;
    still_broken_rate: number | null;
  };
  drafts: {
    made: number;
    used: number;
    changed: number;
    not_used: number;
    used_rate: number | null;
    changed_rate: number | null;
  };
  chat: {
    replies: number;
    answered_rate: number | null;
    handover_rate: number | null;
  };
  hallucination: {
    runs_checked: number;
    missing_reference_rate: number | null;
    missing_references: number;
    unsupported_rate: number | null;
    unsupported: number;
    safety_cuts: number;
    bad_format: number;
  };
};
type Case = { case: string; right: boolean };
type Bench = {
  model: string;
  runs: {
    name: string;
    ran_on: string;
    accuracy: number;
    cases_right: number;
    cases_total: number;
    cost_per_right_case: number | null;
    avg_minutes: number;
    source: string;
  }[];
  cases: Case[];
  others: string[];
  against: string;
  against_cases: Case[];
  against_accuracy: number | null;
  public: {
    name: string;
    benchmark: string;
    score: string;
    measured_on: string;
    source_url: string;
    note: string;
  }[];
  requests: {
    name: string;
    status: string;
    error: string;
    requested_by: string;
    creation: string;
  }[];
  can_change: boolean;
};
type Step = { section: string; model: string; ready: boolean };
type JobRow = Figures & {
  job: string;
  primary: Step | null;
  fallback: Step | null;
  primary_section: string;
  allow_fallback: string;
  openai_model: string;
  anthropic_model: string;
  model: string;
  backup_model: string;
  application: string;
  label: string;
  coming: boolean;
  own_only: boolean;
  score: Score | null;
};
type Application = {
  name: string;
  note: string;
  coming: boolean;
  own_only: boolean;
};
type UsedBy = { application: string; first: string[]; backup: string[] };
type Provider = {
  name: string;
  section: boolean;
  style: string;
  url: string;
  key_set: boolean;
  key_on_gateway?: boolean;
  enabled: boolean;
  ready: boolean;
  json_mode: boolean;
  default_model: string;
  models: number;
  note: string;
};
type CatalogModel = {
  model: string;
  name: string;
  provider: string;
  provider_ready: boolean;
  listed: boolean;
  limit_m: number;
  used_m: number;
  input_price: number;
  output_price: number;
  benchmark: Score | null;
  used_for: UsedFor;
  used_by: UsedBy[];
  on_gateway: boolean;
  in_use: boolean;
};
type Preset = {
  name: string;
  style: string;
  url: string;
  note: string;
};
type Guard = {
  job: string;
  model: string;
  score: Score | null;
  current_model: string;
  current_score: Score | null;
  changes_model: boolean;
  warning: string;
};
type Settings = {
  gateway: {
    on: boolean;
    url: string;
    key_set: boolean;
    synced_at: string;
    note: string;
    for_all: boolean;
    call_key_set: boolean;
    admin_key_set: boolean;
    admin_key_from_desktop: boolean;
    down_since: string;
  };
  jobs: JobRow[];
  sections: Step[];
  defaults: { primary_section: string; failover: boolean };
  applications: Application[];
  providers: Provider[];
  catalog: CatalogModel[];
  presets: Preset[];
  alerts: { error_rate: number; fallback_rate: number };
  guarded_jobs: string[];
  can_change: boolean;
  changes: Record<string, string>[];
};

const route = useRoute();
const router = useRouter();
usePageMeta(() => ({ title: __("AI models") }));

const VIEWS = ["models", "model", "settings"];
const view = computed(() =>
  VIEWS.includes(route.query.view as string)
    ? (route.query.view as string)
    : "models"
);
const days = computed(() =>
  [7, 30, 90].includes(Number(route.query.days)) ? Number(route.query.days) : 30
);
const model = computed(() => (route.query.model as string) || "");
const TABS = ["performance", "errors", "quality", "benchmarks"];
const tab = computed(() =>
  TABS.includes(route.query.tab as string)
    ? (route.query.tab as string)
    : "performance"
);
const against = computed(() => (route.query.against as string) || "");
const views = [
  { label: __("Models"), value: "models" },
  { label: __("One model"), value: "model" },
  { label: __("Model settings"), value: "settings" },
];
const periods = [
  { label: __("7 days"), value: "7" },
  { label: __("30 days"), value: "30" },
  { label: __("90 days"), value: "90" },
];
const tabs = [
  { label: __("Performance"), value: "performance" },
  { label: __("Errors"), value: "errors" },
  { label: __("Quality"), value: "quality" },
  { label: __("Benchmarks"), value: "benchmarks" },
];

function go(change: Record<string, string>) {
  router.replace({ query: { ...route.query, ...change } });
}

const overview = ref<Overview | null>(null);
const detail = ref<Detail | null>(null);
const quality = ref<Quality | null>(null);
const bench = ref<Bench | null>(null);
const settings = ref<Settings | null>(null);
const loading = ref(false);
const error = ref<unknown>(null);
let latest = 0;

// only the newest request fills the page: an older one's answer is dropped after every wait
async function load() {
  const mine = ++latest;
  loading.value = true;
  error.value = null;
  try {
    // the model list (for the picker) comes with every view
    const o = (await call(`${API}.overview`, { days: days.value })) as Overview;
    if (mine !== latest) return;
    overview.value = o;
    if (view.value === "model") {
      const name = model.value || o.models[0]?.model || "";
      if (name && !model.value) return go({ model: name });
      const d = name
        ? ((await call(`${API}.detail`, {
            model: name,
            days: days.value,
          })) as Detail)
        : null;
      if (mine !== latest) return;
      detail.value = d;
      if (name && tab.value === "quality") {
        const q = (await call(`${API}.quality`, {
          model: name,
          days: days.value,
        })) as Quality;
        if (mine !== latest) return;
        quality.value = q;
      } else if (name && tab.value === "benchmarks") {
        const b = (await call(`${API}.benchmarks`, {
          model: name,
          against: against.value || undefined,
        })) as Bench;
        if (mine !== latest) return;
        bench.value = b;
      }
    } else if (view.value === "settings") {
      const s = (await call(`${API}.job_settings`, {
        days: days.value,
      })) as Settings;
      if (mine !== latest) return;
      settings.value = s;
    }
  } catch (err) {
    if (mine === latest) error.value = err;
  } finally {
    if (mine === latest) loading.value = false;
  }
}
watch([view, days, model, tab, against], load, { immediate: true });
// another model's figures and controls never stay on the page while this one loads, or fails
watch(model, () => {
  detail.value = null;
  quality.value = null;
  bench.value = null;
  benchNotice.value = null;
});

// one model's view keeps its picker on screen while another model loads
const shown = computed(() =>
  view.value === "settings" ? settings.value : overview.value
);
const usedModels = computed(
  () => (overview.value?.models || []).filter((m) => m.calls).length
);
const modelOptions = computed(() =>
  (overview.value?.models || []).map((m) => ({
    label: m.model,
    value: m.model,
  }))
);

function money(v: number | null | undefined) {
  return `$${(v || 0).toFixed(2)}`;
}
function pct(v: number | null | undefined) {
  return v === null || v === undefined ? "-" : `${v}%`;
}
function seconds(v: number | null | undefined) {
  return v === null || v === undefined ? "-" : `${v} s`;
}
function speed(p50: number | null, p95: number | null) {
  return p50 === null ? "-" : `${p50} s / ${p95} s`;
}
function usedFor(used: UsedFor) {
  const parts = [];
  if (used.primary.length)
    parts.push(__("First for: {0}", used.primary.join(", ")));
  if (used.fallback.length)
    parts.push(__("Fallback for: {0}", used.fallback.join(", ")));
  return parts.join(" · ") || __("No job uses it");
}

function bars<T extends Record<string, any>>(
  rows: T[],
  key: string,
  text: (v: number) => string,
  tone = "",
  name = "model"
) {
  const withValue = rows.filter((r) => r[key]);
  const max = Math.max(0, ...withValue.map((r) => r[key] as number));
  return withValue.map((r) => ({
    label: String(r[name]),
    share: max ? (r[key] / max) * 100 : 0,
    text: text(r[key]),
    tone,
  }));
}

const dayLabels = computed(() =>
  (detail.value?.series || []).map((d) => d.day.slice(5))
);
function line(
  name: string,
  key: "cost" | "calls" | "error_rate",
  color = "--brand"
) {
  return {
    name,
    color,
    values: (detail.value?.series || []).map((d) => d[key] || 0),
  };
}

// --- model settings ---------------------------------------------------------------------------

const saving = ref(false);
const trying = ref("");
const notice = ref<{ ok: boolean; text: string } | null>(null);
function allowedModels() {
  return (settings.value?.catalog || []).filter((m) => m.listed);
}
function jobLabel(job: string) {
  const row = (settings.value?.jobs || []).find((j) => j.job === job);
  return row ? __(row.label) : job;
}
function jobsOf(app: string) {
  return (settings.value?.jobs || []).filter((j) => j.application === app);
}
function jobModelOptions(job: JobRow) {
  const empty = job.coming
    ? __("Chosen in its phase")
    : job.own_only
    ? __("As today (the gateway's own models)")
    : __("As today (the sections)");
  return [
    { label: empty, value: "" },
    ...allowedModels().map((m) => ({
      label: `${m.name} · ${m.provider}`,
      value: m.model,
    })),
  ];
}
function backupOptions(job: JobRow) {
  return [
    { label: __("No backup"), value: "" },
    ...allowedModels()
      .filter((m) => m.model !== job.model)
      .map((m) => ({ label: `${m.name} · ${m.provider}`, value: m.model })),
  ];
}
function chainText(job: JobRow) {
  if (job.coming) return __("comes with its phase");
  if (!job.primary && job.own_only)
    return __("the gateway's own models, as today");
  if (!job.primary) return __("not set up");
  return job.fallback
    ? `${job.primary.model} → ${job.fallback.model}`
    : job.primary.model;
}

// a refused or cancelled change puts the row's fields back by making them again
const formKey = ref(0);
const guardOpen = ref(false);
const pending = ref<{
  job: string;
  values: Record<string, string>;
  guard: Guard;
} | null>(null);

// Copilot's jobs show the new model's test-set score first when it has none or a lower one
async function save(job: string, values: Record<string, string>) {
  const guarded =
    settings.value?.guarded_jobs.includes(job) &&
    Object.keys(values).some((field) => MODEL_FIELDS.includes(field));
  let expected: string | undefined;
  if (guarded) {
    saving.value = true;
    notice.value = null;
    try {
      const guard = (await call(`${API}.guard`, {
        job,
        values: JSON.stringify(values),
      })) as Guard;
      if (guard.changes_model && guard.warning) {
        pending.value = { job, values, guard };
        guardOpen.value = true;
        return;
      }
      // the save is refused if the job's model changed after this comparison
      expected = guard.current_model || "";
    } catch (err) {
      notice.value = { ok: false, text: errorText(err, __("Not saved")) };
      formKey.value++;
      return;
    } finally {
      saving.value = false;
    }
  }
  await store(job, values, expected);
}
watch(guardOpen, (open) => {
  if (!open && pending.value) {
    pending.value = null;
    formKey.value++;
  }
});
function confirmGuard() {
  const change = pending.value;
  if (!change) return;
  pending.value = null;
  guardOpen.value = false;
  store(change.job, change.values, change.guard.current_model || "");
}
function scoreText(score: Score | null) {
  return score
    ? __("test set {0} on {1}", pct(score.accuracy), score.ran_on)
    : __("not run on the test set");
}

async function store(
  job: string,
  values: Record<string, string>,
  expectedModel?: string
) {
  saving.value = true;
  notice.value = null;
  try {
    const sent =
      expectedModel === undefined
        ? values
        : { ...values, expected_model: expectedModel };
    await call(`${API}.save_job`, { job, values: JSON.stringify(sent) });
    notice.value = { ok: true, text: __("Saved: {0}", jobLabel(job)) };
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not saved")) };
    formKey.value++;
  } finally {
    saving.value = false;
    load();
  }
}

async function tryJob(job: string) {
  trying.value = job;
  notice.value = null;
  try {
    const r = (await call(`${API}.try_job`, { job })) as {
      ok: boolean;
      message: string;
    };
    notice.value = { ok: r.ok, text: `${jobLabel(job)}: ${r.message}` };
  } catch (err) {
    notice.value = {
      ok: false,
      text: errorText(err, __("The test call failed")),
    };
  } finally {
    trying.value = "";
  }
}

// --- benchmarks ---------------------------------------------------------------------------------

const benchBusy = ref(false);
const benchNotice = ref<{ ok: boolean; text: string } | null>(null);
const pub = reactive({
  benchmark: "",
  score: "",
  measured_on: "",
  source_url: "",
});

// A write's answer is not put on the page as it is: the page is read again, with the comparison
// in the address, and that newer read drops any older one still on its way.
async function benchCall(
  method: string,
  args: Record<string, unknown>,
  done: string
) {
  const target = model.value;
  const say = (ok: boolean, text: string) => {
    benchNotice.value = {
      ok,
      text: model.value === target ? text : __("{0}: {1}", target, text),
    };
  };
  benchBusy.value = true;
  benchNotice.value = null;
  try {
    await call(`${API}.${method}`, args);
    say(true, done);
    return true;
  } catch (err) {
    say(false, errorText(err, __("Not saved")));
    return false;
  } finally {
    // the buttons wait for the panel read after the write
    await load();
    benchBusy.value = false;
  }
}
function runEval() {
  benchCall(
    "request_eval",
    { model: model.value },
    __(
      "Asked. When the eval command has run on the test hub, its scores show here as a new run."
    )
  );
}
function withdraw(name: string) {
  benchCall("withdraw_eval_request", { name }, __("Taken back."));
}

// A report is read here and only case numbers and scores are sent: Copilot's own summaries,
// the tickets and the expected answers in the worker's full report never leave the browser.
const reportInput = ref<HTMLInputElement | null>(null);
type CaseScore = Record<string, string | number | boolean | null>;

function caseScore(item: unknown): CaseScore | null {
  if (!item || typeof item !== "object") return null;
  const row = item as Record<string, any>;
  const id = row.case && typeof row.case === "object" ? row.case.id : row.case;
  if (!id) return null;
  const found = row.filesFound;
  return {
    case: String(id),
    right: Boolean(row.right),
    confidence: typeof row.confidence === "number" ? row.confidence : null,
    filesFound: Array.isArray(found) ? found.length : Number(found) || 0,
    tokens: Number(row.tokens) || 0,
    costUsd: Number(row.costUsd) || 0,
    minutes: Number(row.minutes) || 0,
    outcome: typeof row.outcome === "string" ? row.outcome.slice(0, 40) : "",
  };
}

function readReport(
  data: unknown,
  name: string,
  fileDate: string
): { cases: CaseScore[]; ranOn: string } | string {
  const notReport = __("This file is not a test-set report.");
  // the scores file the worker writes beside its report: {ranOn, models: {model: [...]}}
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const file = data as { ranOn?: string; models?: Record<string, unknown> };
    if (!file.models || typeof file.models !== "object") return notReport;
    const mine = file.models[name];
    if (!Array.isArray(mine))
      return __(
        "This report has no scores for {0}. It has: {1}",
        name,
        Object.keys(file.models).join(", ")
      );
    return {
      cases: mine.map(caseScore).filter((c): c is CaseScore => !!c),
      ranOn: file.ranOn || fileDate,
    };
  }
  if (!Array.isArray(data)) return notReport;
  // the full report: one row per case, with the models that answered it
  const named = data.filter(
    (row) => row && typeof row === "object" && typeof row.model === "string"
  );
  const rows = named.length
    ? named.filter((row) => row.model.split(", ").includes(name))
    : data;
  if (!rows.length)
    return __("No case in this report was answered by {0}.", name);
  return {
    cases: rows.map(caseScore).filter((c): c is CaseScore => !!c),
    ranOn: fileDate,
  };
}

async function bringReport(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  // the scores go to the model shown when the file was picked, never one chosen while it is read
  const target = model.value;
  benchNotice.value = null;
  let data: unknown;
  try {
    data = JSON.parse(await file.text());
  } catch {
    benchNotice.value = {
      ok: false,
      text: __("This file is not a test-set report."),
    };
    return;
  }
  if (model.value !== target) {
    benchNotice.value = {
      ok: false,
      text: __(
        "Another model was chosen while the file was read, so nothing was brought in. Bring the report in again."
      ),
    };
    return;
  }
  const fileDate = new Date(file.lastModified).toISOString().slice(0, 10);
  const report = readReport(data, target, fileDate);
  if (typeof report === "string" || !report.cases.length) {
    benchNotice.value = {
      ok: false,
      text:
        typeof report === "string"
          ? report
          : __("This file is not a test-set report."),
    };
    return;
  }
  benchCall(
    "import_eval",
    {
      model: target,
      report: JSON.stringify(report.cases),
      ran_on: report.ranOn,
    },
    report.cases.length === 1
      ? __("Brought in 1 case. Only case numbers and scores were sent.")
      : __(
          "Brought in {0} cases. Only case numbers and scores were sent.",
          String(report.cases.length)
        )
  );
}
async function addPublic() {
  const ok = await benchCall(
    "add_public_benchmark",
    { model: model.value, values: JSON.stringify(pub) },
    __("Added.")
  );
  if (ok)
    Object.assign(pub, {
      benchmark: "",
      score: "",
      measured_on: "",
      source_url: "",
    });
}
function removePublic(name: string) {
  benchCall("remove_public_benchmark", { name }, __("Removed."));
}

// --- providers and the model list ----------------------------------------------------------

// a remove asks for a second click on the same row within 5 seconds; the key names the kind of
// record too ("provider:x", "model:x"), as a model and a provider can share a name
const confirming = ref("");
let confirmTimer: ReturnType<typeof setTimeout> | undefined;
function askTwice(key: string) {
  clearTimeout(confirmTimer);
  if (confirming.value === key) {
    confirming.value = "";
    return true;
  }
  confirming.value = key;
  confirmTimer = setTimeout(() => (confirming.value = ""), 5000);
  return false;
}
function keyLabel(p: Provider) {
  if (!p.key_set) return __("none yet");
  const where = p.key_on_gateway ? __("on the gateway") : __("saved");
  return p.enabled ? where : __("{0}, off", where);
}

const provOpen = ref(false);
const provSaving = ref(false);
const provError = ref("");
const provNotice = ref<{ ok: boolean; text: string } | null>(null);
const testing = ref("");
// each opening of the dialog: a late answer for an earlier opening leaves this one alone
let provOpening = 0;
const prov = reactive({
  existing: false,
  section: false,
  preset: "",
  name: "",
  style: "OpenAI-compatible",
  url: "",
  key: "",
  keySet: false,
  defaultModel: "",
  jsonMode: true,
  enabled: true,
  note: "",
});
const presetOptions = computed(() => [
  ...(settings.value?.presets || []).map((p) => ({
    label: p.name,
    value: p.name,
  })),
  { label: __("Other"), value: "" },
]);
function usePreset(name: string) {
  const preset = (settings.value?.presets || []).find((p) => p.name === name);
  Object.assign(prov, {
    preset: name,
    name: preset ? preset.name : "",
    style: preset ? preset.style : "OpenAI-compatible",
    url: preset ? preset.url : "",
    note: preset ? preset.note : "",
  });
}
function openProvider(p?: Provider) {
  provOpening++;
  provError.value = "";
  Object.assign(prov, {
    existing: !!p,
    section: !!p?.section,
    key: "",
    keySet: !!p?.key_set,
    defaultModel: p?.default_model || "",
    jsonMode: p ? p.json_mode : true,
    enabled: p ? p.enabled : true,
  });
  if (p)
    Object.assign(prov, {
      preset: "",
      name: p.name,
      style: p.style,
      url: p.url,
      note: p.note,
    });
  else usePreset(settings.value?.presets[0]?.name || "");
  provOpen.value = true;
}
// the key never stays in the page after the dialog closes
watch(provOpen, (open) => {
  if (!open) prov.key = "";
});
async function saveProvider() {
  const at = provOpening;
  provSaving.value = true;
  provError.value = "";
  const values: Record<string, unknown> = prov.section
    ? { name: prov.name, url: prov.url, default_model: prov.defaultModel }
    : {
        name: prov.name.trim(),
        style: prov.style,
        url: prov.url,
        enabled: prov.enabled ? 1 : 0,
        json_mode: prov.jsonMode ? 1 : 0,
        note: prov.note,
        new: prov.existing ? 0 : 1,
      };
  if (prov.key) values.key = prov.key;
  try {
    await call(`${API}.save_provider`, { values: JSON.stringify(values) });
    provNotice.value = {
      ok: true,
      text: __("{0} saved.", String(values.name)),
    };
    if (at === provOpening) provOpen.value = false;
  } catch (err) {
    if (at === provOpening) provError.value = errorText(err, __("Not saved"));
  } finally {
    provSaving.value = false;
    load();
  }
}
// the On switch of a provider account: its other settings stay as they are
const switching = ref("");
async function toggleProvider(p: Provider, on: boolean) {
  switching.value = p.name;
  provNotice.value = null;
  try {
    await call(`${API}.save_provider`, {
      values: JSON.stringify({
        name: p.name,
        style: p.style,
        url: p.url,
        enabled: on ? 1 : 0,
        json_mode: p.json_mode ? 1 : 0,
      }),
    });
    provNotice.value = {
      ok: true,
      text: on
        ? __("{0} is on.", p.name)
        : __(
            "{0} is off: the purposes using its models go to their backup.",
            p.name
          ),
    };
  } catch (err) {
    provNotice.value = { ok: false, text: errorText(err, __("Not saved")) };
  } finally {
    switching.value = "";
    load();
  }
}
async function testProvider(name: string) {
  testing.value = name;
  provNotice.value = null;
  try {
    const r = (await call(`${API}.test_provider`, { name })) as {
      ok: boolean;
      message: string;
    };
    provNotice.value = { ok: r.ok, text: r.message };
  } catch (err) {
    provNotice.value = {
      ok: false,
      text: errorText(err, __("The test call failed")),
    };
  } finally {
    testing.value = "";
  }
}
async function removeProvider(name: string) {
  if (!askTwice(`provider:${name}`)) return;
  provNotice.value = null;
  try {
    await call(`${API}.remove_provider`, { name });
    provNotice.value = {
      ok: true,
      text: __("{0} removed, with its key.", name),
    };
  } catch (err) {
    provNotice.value = { ok: false, text: errorText(err, __("Not removed")) };
  } finally {
    load();
  }
}

const listBusy = ref(false);
const listNotice = ref<{ ok: boolean; text: string } | null>(null);
const modelOpen = ref(false);
const modelSaving = ref(false);
const modelError = ref("");
let modelOpening = 0;
const mform = reactive({
  existing: false,
  model: "",
  name: "",
  provider: "",
  input_price: "" as string | number,
  output_price: "" as string | number,
  limit_m: "" as string | number,
  listed: true,
});
const providerOptions = computed(() =>
  (settings.value?.providers || []).map((p) => ({
    label: p.ready ? p.name : __("{0} (no key yet, or off)", p.name),
    value: p.name,
  }))
);
function openModel(m?: CatalogModel) {
  modelOpening++;
  modelError.value = "";
  Object.assign(
    mform,
    m
      ? {
          existing: true,
          model: m.model,
          name: m.name,
          provider: m.provider,
          input_price: m.input_price,
          output_price: m.output_price,
          limit_m: m.limit_m || "",
          listed: m.listed,
        }
      : {
          existing: false,
          model: "",
          name: "",
          provider:
            settings.value?.providers.find((p) => !p.section)?.name || "",
          input_price: "",
          output_price: "",
          limit_m: "",
          listed: true,
        }
  );
  modelOpen.value = true;
}
async function saveModelDialog() {
  const at = modelOpening;
  modelSaving.value = true;
  modelError.value = "";
  const values = {
    model: mform.model.trim(),
    name: mform.name.trim(),
    provider: mform.provider,
    input_price: Number(mform.input_price) || 0,
    output_price: Number(mform.output_price) || 0,
    limit_m: Number(mform.limit_m) || 0,
    listed: mform.listed ? 1 : 0,
    new: mform.existing ? 0 : 1,
  };
  try {
    await call(`${API}.save_model`, { values: JSON.stringify(values) });
    listNotice.value = { ok: true, text: __("{0} saved.", values.model) };
    if (at === modelOpening) modelOpen.value = false;
  } catch (err) {
    if (at === modelOpening) modelError.value = errorText(err, __("Not saved"));
  } finally {
    modelSaving.value = false;
    load();
  }
}
async function saveModel(values: Record<string, unknown>) {
  listBusy.value = true;
  listNotice.value = null;
  try {
    await call(`${API}.save_model`, { values: JSON.stringify(values) });
    listNotice.value = {
      ok: true,
      text: __("{0} saved.", String(values.model)),
    };
  } catch (err) {
    listNotice.value = { ok: false, text: errorText(err, __("Not saved")) };
    formKey.value++;
  } finally {
    listBusy.value = false;
    load();
  }
}
async function removeModel(name: string) {
  if (!askTwice(`model:${name}`)) return;
  listNotice.value = null;
  try {
    await call(`${API}.remove_model`, { model: name });
    listNotice.value = {
      ok: true,
      text: __("{0} removed from the list.", name),
    };
  } catch (err) {
    listNotice.value = { ok: false, text: errorText(err, __("Not removed")) };
  } finally {
    load();
  }
}
function limitShare(m: CatalogModel) {
  return m.limit_m
    ? Math.max(2, Math.min(100, (m.used_m / m.limit_m) * 100))
    : 0;
}
function limitTone(m: CatalogModel) {
  const share = m.limit_m ? (m.used_m / m.limit_m) * 100 : 0;
  if (share >= 100) return "bg-danger";
  return share >= 80 ? "bg-warning" : "bg-surface-gray-7";
}
function usedByLine(u: UsedBy) {
  return [
    u.first.map((label) => __(label)).join(", "),
    u.backup.length
      ? __("backup for {0}", u.backup.map((label) => __(label)).join(", "))
      : "",
  ]
    .filter(Boolean)
    .join("; ");
}

// a refresh fills only the fields nobody changed since the last one: a draft being typed stays
function refill<T extends object>(
  form: T,
  before: Partial<T> | null,
  now: Partial<T>
) {
  for (const field of Object.keys(now) as (keyof T)[]) {
    if (!before || String(form[field]) === String(before[field]))
      form[field] = now[field] as T[keyof T];
  }
}

const alertForm = reactive({ error_rate: 0, fallback_rate: 0 });
const alertBusy = ref(false);
const alertNotice = ref<{ ok: boolean; text: string } | null>(null);
// after a save that went through, the server's values win (as it stored them); the flag
// lasts only for the reload that save starts
let alertsSaved = false;
watch(
  () => settings.value?.alerts,
  (limits, old) => {
    if (limits) refill(alertForm, alertsSaved ? null : old || null, limits);
  },
  { flush: "sync" }
);
function limitText(limit: number) {
  return limit ? `${limit}%` : __("off");
}
async function saveAlerts() {
  alertBusy.value = true;
  alertNotice.value = null;
  try {
    await call(`${API}.save_alerts`, {
      values: JSON.stringify({
        error_rate: Number(alertForm.error_rate) || 0,
        fallback_rate: Number(alertForm.fallback_rate) || 0,
      }),
    });
    alertNotice.value = { ok: true, text: __("Alert limits saved.") };
    alertsSaved = true;
  } catch (err) {
    alertNotice.value = { ok: false, text: errorText(err, __("Not saved")) };
  } finally {
    alertBusy.value = false;
    await load();
    alertsSaved = false;
  }
}

// --- the AI gateway ---------------------------------------------------------------------------

const gw = reactive({
  url: "",
  key: "",
  on: false,
  callKey: "",
  adminKey: "",
  forAll: false,
});
const gwBusy = ref(false);
// the gateway's own results, shown in its card
const gwNotice = ref<{ ok: boolean; text: string } | null>(null);
// the typed keys are never read back: they stay until saved, so a refused save can be corrected
// after a save of these settings, the server's values win: all of them when it went through,
// the switches when it was refused (so the card never shows a state the server didn't keep; a
// typed address stays for correction). It lasts only for the reload that save starts.
let gwTake: "all" | "switches" | null = null;
watch(
  () => settings.value?.gateway,
  (g, old) => {
    if (!g) return;
    const before = old
      ? { url: old.url, on: old.on, forAll: old.for_all }
      : null;
    if (gwTake === "all") {
      refill(gw, null, { url: g.url, on: g.on, forAll: g.for_all });
    } else if (gwTake === "switches") {
      refill(gw, null, { on: g.on, forAll: g.for_all });
      refill(gw, before, { url: g.url });
    } else {
      refill(gw, before, { url: g.url, on: g.on, forAll: g.for_all });
    }
  },
  { flush: "sync" }
);
async function gatewayCall(
  method: string,
  args: Record<string, unknown>,
  done: string,
  saving = false
) {
  gwBusy.value = true;
  gwNotice.value = null;
  let ok = false;
  try {
    const r = (await call(`${API}.${method}`, args)) as {
      ok?: boolean;
      note?: string;
    };
    gwNotice.value = {
      ok: r.ok !== false,
      text: r.note ? __("AI gateway: {0}", r.note) : done,
    };
    ok = true;
  } catch (err) {
    gwNotice.value = { ok: false, text: errorText(err, __("Not saved")) };
  } finally {
    gwBusy.value = false;
  }
  // only a save of these settings takes the server's values (a read of usage leaves a draft)
  if (saving) gwTake = ok ? "all" : "switches";
  await load();
  gwTake = null;
  return ok;
}
async function saveGateway() {
  const values: Record<string, unknown> = {
    url: gw.url,
    on: gw.on ? 1 : 0,
    for_all: gw.forAll ? 1 : 0,
  };
  if (gw.key) values.key = gw.key;
  if (gw.callKey) values.call_key = gw.callKey;
  if (gw.adminKey) values.admin_key = gw.adminKey;
  // what was sent: a key typed while the save is on its way is a new one, and stays
  const sent = { key: gw.key, callKey: gw.callKey, adminKey: gw.adminKey };
  const ok = await gatewayCall(
    "save_gateway",
    { values: JSON.stringify(values) },
    __("AI gateway saved."),
    true
  );
  if (!ok) return;
  for (const field of ["key", "callKey", "adminKey"] as const) {
    if (gw[field] === sent[field]) gw[field] = "";
  }
}
function readGateway() {
  gatewayCall("sync_gateway", {}, __("Read."));
}
// when the desktop app's usage was last read from the gateway
const usageLine = computed(() => {
  const g = settings.value?.gateway;
  if (!g || !g.on) return "";
  return g.synced_at
    ? __("Usage last read {0}. {1}", g.synced_at, g.note)
    : g.note || __("Usage not read yet.");
});
async function writeAll() {
  gwBusy.value = true;
  gwNotice.value = null;
  try {
    const r = (await call(`${API}.write_all_to_gateway`)) as Settings & {
      written: { keys: number; models: number };
    };
    gwNotice.value = {
      ok: true,
      text: __(
        "Written to the gateway: {0} keys and {1} models.",
        String(r.written.keys),
        String(r.written.models)
      ),
    };
  } catch (err) {
    gwNotice.value = { ok: false, text: errorText(err, __("Not written")) };
  } finally {
    gwBusy.value = false;
    load();
  }
}
</script>

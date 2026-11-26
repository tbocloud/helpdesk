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
          <template v-else-if="detail">
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

        <!-- 3. which model each job uses -->
        <template v-else-if="view === 'settings' && settings">
          <p class="text-p-sm text-ink-gray-6">
            {{
              settings.can_change
                ? __(
                    "Each job has its own first model and its own fallback. Turn the fallback off where a weaker answer is worse than no answer."
                  )
                : __("Only System Managers change these.")
            }}
          </p>
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
          <div class="overflow-x-auto rounded-xl border border-outline-gray-2">
            <table class="w-full min-w-[68rem] text-p-sm">
              <thead>
                <tr class="bg-surface-gray-1 text-left text-ink-gray-5">
                  <th scope="col" class="px-4 py-2.5 font-medium">
                    {{ __("Job") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 font-medium">
                    {{ __("Tries first") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 font-medium">
                    {{ __("Fallback") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 font-medium">
                    {{ __("OpenAI model") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 font-medium">
                    {{ __("Anthropic-compatible model") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Calls") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Errors") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Cost") }}
                  </th>
                  <th scope="col" class="px-4 py-2.5">
                    <span class="sr-only">{{ __("Test") }}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="job in settings.jobs"
                  :key="`${job.job}-${formKey}`"
                  class="border-t border-outline-gray-1 align-top"
                >
                  <td class="px-4 py-3">
                    <div class="text-base-medium text-ink-gray-9">
                      {{ job.job }}
                    </div>
                    <div class="text-ink-gray-5">
                      {{ job.primary ? job.primary.model : __("not set up") }}
                      <template v-if="job.fallback">
                        → {{ job.fallback.model }}
                      </template>
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
                  <td class="px-3 py-3">
                    <FormControl
                      type="select"
                      :aria-label="__('First section for {0}', job.job)"
                      :model-value="job.primary_section"
                      :options="sectionOptions"
                      :disabled="!settings.can_change || saving"
                      @update:model-value="
                        save(job.job, { primary_section: $event })
                      "
                    />
                  </td>
                  <td class="px-3 py-3">
                    <FormControl
                      type="select"
                      :aria-label="__('Fallback for {0}', job.job)"
                      :model-value="job.allow_fallback"
                      :options="fallbackOptions"
                      :disabled="!settings.can_change || saving"
                      @update:model-value="
                        save(job.job, { allow_fallback: $event })
                      "
                    />
                  </td>
                  <td class="px-3 py-3">
                    <FormControl
                      type="text"
                      :aria-label="__('OpenAI model for {0}', job.job)"
                      :model-value="job.openai_model"
                      :placeholder="sectionModel('OpenAI')"
                      :disabled="!settings.can_change || saving"
                      @change="
                        save(job.job, { openai_model: $event.target.value })
                      "
                    />
                  </td>
                  <td class="px-3 py-3">
                    <FormControl
                      type="text"
                      :aria-label="
                        __('Anthropic-compatible model for {0}', job.job)
                      "
                      :model-value="job.anthropic_model"
                      :placeholder="sectionModel('Anthropic-compatible')"
                      :disabled="!settings.can_change || saving"
                      @change="
                        save(job.job, { anthropic_model: $event.target.value })
                      "
                    />
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ job.calls.toLocaleString() }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ pct(job.error_rate) }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ money(job.cost) }}
                  </td>
                  <td class="px-4 py-3 text-right">
                    <Button
                      v-if="settings.can_change"
                      :label="__('Try')"
                      :loading="trying === job.job"
                      :disabled="!!trying"
                      @click="tryJob(job.job)"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-p-xs text-ink-gray-5">
            {{
              __(
                "Blank model: the section's own model. Keys and the sections themselves are in Settings → AI providers."
              )
            }}
          </p>

          <SectionCard
            :title="__('Candidates')"
            :description="
              __('Models added to be tested before a job uses them')
            "
          >
            <div class="flex flex-col gap-3 px-4 pb-4">
              <p
                v-if="candNotice"
                role="status"
                class="rounded-lg px-3 py-2 text-p-sm"
                :class="
                  candNotice.ok
                    ? 'bg-success-soft text-success'
                    : 'bg-warning-soft text-warning'
                "
              >
                {{ candNotice.text }}
              </p>
              <ul class="flex flex-col gap-1.5 text-p-sm">
                <li
                  v-for="c in settings.candidates"
                  :key="c.model"
                  class="flex flex-wrap items-center gap-x-3 gap-y-1"
                >
                  <button
                    type="button"
                    class="rounded text-base-medium text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    @click="
                      go({ view: 'model', model: c.model, tab: 'benchmarks' })
                    "
                  >
                    {{ c.model }}
                  </button>
                  <span class="text-ink-gray-5">{{ c.section }}</span>
                  <span class="tabular-nums text-ink-gray-6">
                    {{
                      __(
                        "{0} in, {1} out per million tokens",
                        money(c.input_price),
                        money(c.output_price)
                      )
                    }}
                  </span>
                  <span class="tabular-nums">
                    {{
                      c.benchmark
                        ? __(
                            "test set {0} on {1}",
                            pct(c.benchmark.accuracy),
                            c.benchmark.ran_on
                          )
                        : __("not run on the test set")
                    }}
                  </span>
                  <Badge
                    v-if="c.in_use"
                    :label="__('A job uses it')"
                    theme="green"
                    size="sm"
                  />
                  <span v-if="c.note" class="text-ink-gray-6">{{
                    c.note
                  }}</span>
                  <Button
                    v-if="settings.can_change"
                    variant="ghost"
                    size="sm"
                    :label="__('Remove')"
                    :loading="candBusy"
                    @click="removeCandidate(c.model)"
                  />
                </li>
                <li v-if="!settings.candidates.length" class="text-ink-gray-5">
                  {{ __("None yet.") }}
                </li>
              </ul>
              <form
                v-if="settings.can_change"
                class="grid grid-cols-1 items-end gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_12rem_8rem_8rem_minmax(0,1fr)_auto]"
                @submit.prevent="addCandidate"
              >
                <FormControl
                  v-model="cand.model"
                  type="text"
                  :label="__('Model name')"
                  :placeholder="__('as the provider writes it')"
                />
                <FormControl
                  v-model="cand.section"
                  type="select"
                  :label="__('Called through')"
                  :options="SECTIONS"
                />
                <FormControl
                  v-model="cand.input_price"
                  type="number"
                  :label="__('Input, $ per 1M')"
                />
                <FormControl
                  v-model="cand.output_price"
                  type="number"
                  :label="__('Output, $ per 1M')"
                />
                <FormControl
                  v-model="cand.note"
                  type="text"
                  :label="__('Note')"
                />
                <Button type="submit" :label="__('Add')" :loading="candBusy" />
              </form>
              <p class="text-p-xs text-ink-gray-5">
                {{
                  __(
                    "A candidate is called with its section's key. To use it, type its name as a job's model above."
                  )
                }}
              </p>
            </div>
          </SectionCard>

          <SectionCard
            :title="__('Alerts')"
            :description="__('Checked every hour on the last hour of calls')"
          >
            <div class="flex flex-col gap-3 px-4 pb-4">
              <p class="text-p-sm text-ink-gray-6">
                {{
                  __(
                    "The System and Agent Managers are told when a model fails, or the fallback gives the answer, at least this share of the time in an hour (from 10 calls). 0 turns an alert off. A model alerts at most once in 6 hours."
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
                class="grid grid-cols-1 items-end gap-3 sm:grid-cols-[12rem_12rem_auto]"
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
                  :label="__('Fallback answers, %')"
                />
                <Button
                  type="submit"
                  :label="__('Save')"
                  :loading="alertBusy"
                />
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

          <SectionCard
            :title="__('AI gateway (desktop app)')"
            :description="
              __(
                'Read every hour with a read-only key, as totals per day. A message is never read.'
              )
            "
          >
            <div class="flex flex-col gap-3 px-4 pb-4">
              <p class="text-p-sm text-ink-gray-6">
                {{
                  settings.gateway.on
                    ? settings.gateway.synced_at
                      ? __(
                          "Last read {0}. {1}",
                          settings.gateway.synced_at,
                          settings.gateway.note
                        )
                      : settings.gateway.note || __("Not read yet.")
                    : __("Off: the desktop app's models are not shown.")
                }}
              </p>
              <form
                v-if="settings.can_change"
                class="grid grid-cols-1 items-end gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto_auto]"
                @submit.prevent="saveGateway"
              >
                <FormControl
                  v-model="gw.url"
                  type="text"
                  :label="__('Gateway address')"
                  placeholder="https://"
                />
                <FormControl
                  v-model="gw.key"
                  type="password"
                  :label="__('Read-only key')"
                  :placeholder="
                    settings.gateway.key_set ? __('saved; type to replace') : ''
                  "
                  autocomplete="off"
                />
                <FormControl
                  v-model="gw.on"
                  type="checkbox"
                  :label="__('Read it')"
                />
                <Button type="submit" :label="__('Save')" :loading="gwBusy" />
                <Button
                  :label="__('Read now')"
                  :loading="gwBusy"
                  :disabled="!settings.gateway.on"
                  @click="readGateway"
                />
              </form>
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
  TabButtons,
  usePageMeta,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
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
const SECTIONS = [
  { label: "OpenAI", value: "OpenAI" },
  { label: "Anthropic-compatible", value: "Anthropic-compatible" },
];
const MODEL_FIELDS = ["primary_section", "openai_model", "anthropic_model"];

type Score = { accuracy: number; ran_on: string };

type Figures = {
  calls: number;
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
  public: Record<string, string>[];
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
  score: Score | null;
};
type Candidate = {
  model: string;
  section: string;
  input_price: number;
  output_price: number;
  note: string;
  benchmark: Score | null;
  in_use: boolean;
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
  };
  jobs: JobRow[];
  sections: Step[];
  defaults: { primary_section: string; failover: boolean };
  candidates: Candidate[];
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

// only the newest request fills the page
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
      detail.value = name
        ? ((await call(`${API}.detail`, {
            model: name,
            days: days.value,
          })) as Detail)
        : null;
      if (name && tab.value === "quality") {
        quality.value = (await call(`${API}.quality`, {
          model: name,
          days: days.value,
        })) as Quality;
      } else if (name && tab.value === "benchmarks") {
        bench.value = (await call(`${API}.benchmarks`, {
          model: name,
          against: against.value || undefined,
        })) as Bench;
      }
    } else if (view.value === "settings") {
      settings.value = (await call(`${API}.job_settings`, {
        days: days.value,
      })) as Settings;
    }
  } catch (err) {
    if (mine === latest) error.value = err;
  } finally {
    if (mine === latest) loading.value = false;
  }
}
watch([view, days, model, tab, against], load, { immediate: true });

const shown = computed(() =>
  view.value === "models"
    ? overview.value
    : view.value === "model"
    ? detail.value || !model.value
    : settings.value
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
const sectionOptions = computed(() => [
  {
    label: __("Default ({0})", settings.value?.defaults.primary_section || ""),
    value: "",
  },
  { label: "OpenAI", value: "OpenAI" },
  { label: "Anthropic-compatible", value: "Anthropic-compatible" },
]);
const fallbackOptions = computed(() => [
  {
    label: __(
      "Default ({0})",
      settings.value?.defaults.failover ? __("On") : __("Off")
    ),
    value: "",
  },
  { label: __("On"), value: "On" },
  { label: __("Off"), value: "Off" },
]);
function sectionModel(section: string) {
  return (
    settings.value?.sections.find((s) => s.section === section)?.model || ""
  );
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
    } catch (err) {
      notice.value = { ok: false, text: errorText(err, __("Not saved")) };
      formKey.value++;
      return;
    } finally {
      saving.value = false;
    }
  }
  await store(job, values);
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
  store(change.job, change.values);
}
function scoreText(score: Score | null) {
  return score
    ? __("test set {0} on {1}", pct(score.accuracy), score.ran_on)
    : __("not run on the test set");
}

async function store(job: string, values: Record<string, string>) {
  saving.value = true;
  notice.value = null;
  try {
    await call(`${API}.save_job`, { job, values: JSON.stringify(values) });
    notice.value = { ok: true, text: __("Saved: {0}", job) };
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
    notice.value = { ok: r.ok, text: `${job}: ${r.message}` };
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

async function benchCall(
  method: string,
  args: Record<string, unknown>,
  done: string
) {
  benchBusy.value = true;
  benchNotice.value = null;
  try {
    bench.value = (await call(`${API}.${method}`, args)) as Bench;
    benchNotice.value = { ok: true, text: done };
    return true;
  } catch (err) {
    benchNotice.value = { ok: false, text: errorText(err, __("Not saved")) };
    return false;
  } finally {
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
  const fileDate = new Date(file.lastModified).toISOString().slice(0, 10);
  const report = readReport(data, model.value, fileDate);
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
      model: model.value,
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

// --- candidates and alerts --------------------------------------------------------------------

const cand = reactive({
  model: "",
  section: "Anthropic-compatible",
  input_price: "",
  output_price: "",
  note: "",
});
const candBusy = ref(false);
const candNotice = ref<{ ok: boolean; text: string } | null>(null);
async function candidateCall(
  method: string,
  args: Record<string, unknown>,
  done: string
) {
  candBusy.value = true;
  candNotice.value = null;
  try {
    await call(`${API}.${method}`, args);
    candNotice.value = { ok: true, text: done };
    return true;
  } catch (err) {
    candNotice.value = { ok: false, text: errorText(err, __("Not saved")) };
    return false;
  } finally {
    candBusy.value = false;
    load();
  }
}
async function addCandidate() {
  const name = cand.model.trim();
  const ok = await candidateCall(
    "add_model",
    { values: JSON.stringify({ ...cand, model: name }) },
    __("{0} added. Ask for a run of the test set on its page.", name)
  );
  if (ok)
    Object.assign(cand, {
      model: "",
      input_price: "",
      output_price: "",
      note: "",
    });
}
function removeCandidate(name: string) {
  candidateCall("remove_candidate", { model: name }, __("{0} removed.", name));
}

const alertForm = reactive({ error_rate: 0, fallback_rate: 0 });
const alertBusy = ref(false);
const alertNotice = ref<{ ok: boolean; text: string } | null>(null);
watch(
  () => settings.value?.alerts,
  (limits) => {
    if (limits) Object.assign(alertForm, limits);
  }
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
  } catch (err) {
    alertNotice.value = { ok: false, text: errorText(err, __("Not saved")) };
  } finally {
    alertBusy.value = false;
    load();
  }
}

// --- the AI gateway ---------------------------------------------------------------------------

const gw = reactive({ url: "", key: "", on: false });
const gwBusy = ref(false);
watch(
  () => settings.value?.gateway,
  (g) => {
    if (g) Object.assign(gw, { url: g.url, key: "", on: g.on });
  }
);
async function gatewayCall(
  method: string,
  args: Record<string, unknown>,
  done: string
) {
  gwBusy.value = true;
  notice.value = null;
  try {
    const r = (await call(`${API}.${method}`, args)) as {
      ok?: boolean;
      note?: string;
    };
    notice.value = {
      ok: r.ok !== false,
      text: r.note ? __("AI gateway: {0}", r.note) : done,
    };
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not saved")) };
  } finally {
    gwBusy.value = false;
    load();
  }
}
function saveGateway() {
  const values: Record<string, unknown> = { url: gw.url, on: gw.on ? 1 : 0 };
  if (gw.key) values.key = gw.key;
  gatewayCall(
    "save_gateway",
    { values: JSON.stringify(values) },
    __("AI gateway saved.")
  );
}
function readGateway() {
  gatewayCall("sync_gateway", {}, __("Read."));
}
</script>

<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">{{ __("Leads") }}</h1>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="isList && leads.loading && !!data"
          :aria-label="__('Refresh')"
          @click="refresh"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="options?.can_find_prospects && !isBd"
          :label="__('Find prospects')"
          :route="{ name: 'FindProspects' }"
        >
          <template #prefix>
            <LucideRadar class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button variant="solid" :label="__('New lead')" @click="showNew = true">
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <div class="flex flex-col gap-3">
          <div class="overflow-x-auto">
            <TabButtons
              :model-value="view"
              size="md"
              :aria-label="__('Which leads')"
              :options="tabs"
              @update:model-value="
                view = $event as LeadTab;
                picked = true;
              "
            />
          </div>
          <!-- the Daily report has the day's new leads itself, and loads in one request -->
          <template
            v-if="
              view !== 'daily' &&
              view !== 'today' &&
              view !== 'business' &&
              view !== 'outreach' &&
              view !== 'commission'
            "
          >
            <!-- hidden quietly until the ERP site's TBO Smart counts it, and on a failed read -->
            <div
              v-if="!intakeData && intakeLoading"
              class="h-[118px] animate-pulse rounded-xl bg-surface-gray-2 md:h-[94px]"
              aria-hidden="true"
            />
            <LeadIntakeStrip v-else-if="intakeOn" :intake="intakeData!" />
          </template>
        </div>

        <!-- the batch of calls for this slot; it replaces Call today for those who have it -->
        <TodaysCalls v-if="view === 'today'" ref="todayPanel" class="mt-4" />

        <LeadsOverview
          v-else-if="view === 'overview'"
          ref="overviewPanel"
          class="mt-4"
          @intake="takeOverviewIntake"
        />

        <!-- the Daily Sales Performance Report; only when the ERP site has it -->
        <LeadsDailyReport
          v-else-if="view === 'daily'"
          ref="dailyPanel"
          class="mt-4"
        />

        <!-- management only: the ERP site decides who (System Manager or TBO Management) -->
        <template v-else-if="view === 'business'">
          <LeadsBusiness
            v-if="canViewBusiness"
            ref="businessPanel"
            class="mt-4"
            :options="options"
          />
        </template>

        <!-- each person's commission on money collected, per project; what a person may see is decided on the ERP site -->
        <LeadsCommission
          v-else-if="view === 'commission'"
          ref="commissionPanel"
          class="mt-4"
        />

        <!-- first messages the AI drafted, for a person to approve; only while Outreach is on -->
        <LeadsOutreach
          v-else-if="view === 'outreach'"
          ref="outreachPanel"
          class="mt-4"
          :options="options"
        />

        <div v-else class="mt-3 flex flex-col gap-3">
          <!-- what they called: today, this week, this month, all time, and by day -->
          <MyCallCounts v-if="view === 'mine'" ref="callCounts" />
          <!-- overdue, today, tomorrow, the week, later: a card lists its leads -->
          <FollowUpCards
            v-if="view === 'follow_up'"
            ref="followUpCards"
            v-model="filters.due"
            :owner="filters.owner"
          />
          <!-- one toolbar: search, the filters people use most, the rest behind More filters -->
          <div
            class="flex flex-wrap items-center gap-2"
            role="group"
            :aria-label="__('Filter the leads')"
          >
            <FormControl
              v-model="search"
              type="search"
              class="w-full sm:w-72"
              :aria-label="__('Search')"
              :placeholder="__('Name, company, email or mobile')"
              autocomplete="off"
            >
              <template #prefix>
                <LucideSearch
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
              </template>
            </FormControl>
            <FormControl
              v-model="filters.stage"
              type="select"
              class="w-36"
              :aria-label="__('Stage')"
              :options="stageOptions"
            />
            <FormControl
              v-if="!isBd"
              v-model="filters.owner"
              type="select"
              class="w-40"
              :aria-label="__('Owner')"
              :options="ownerOptions"
            />
            <FormControl
              v-if="isBd || view === 'mine'"
              v-model="filters.created_by"
              type="select"
              class="w-44"
              :aria-label="__('Created by')"
              :options="CREATED_BY"
            />
            <FormControl
              v-if="view === 'called'"
              v-model="filters.called"
              type="select"
              class="w-40"
              :aria-label="__('Last called')"
              :options="LAST_CALLED"
            />
            <LeadCategoryFilters
              ref="productPanel"
              v-model="categories"
              class="w-44"
              :options="options"
              :only="['product']"
              bare
            />
            <Button
              :label="
                hiddenChips.length
                  ? __('More filters ({0})', String(hiddenChips.length))
                  : __('More filters')
              "
              :aria-expanded="showMore"
              @click="showMore = true"
            >
              <template #prefix>
                <LucideSlidersHorizontal class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <div class="ml-auto flex flex-wrap items-center gap-2">
              <Button
                v-if="canCategorise"
                :label="selecting ? __('Done') : __('Select leads')"
                @click="toggleSelecting"
              >
                <template #prefix>
                  <LucideListChecks class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </div>
          <div
            v-if="created === 'custom'"
            class="flex flex-wrap items-end gap-3"
            role="group"
            :aria-label="__('Created between')"
          >
            <FormControl
              v-model="extra.from"
              type="date"
              class="w-40"
              :label="__('From')"
            />
            <FormControl
              v-model="extra.to"
              type="date"
              class="w-40"
              :label="__('To')"
            />
          </div>
          <!-- bulk actions, once Select leads is on -->
          <div
            v-if="canCategorise && selecting"
            class="flex flex-wrap items-center gap-2"
          >
            <span
              class="mr-auto font-mono text-p-sm tabular-nums text-ink-gray-7"
              aria-live="polite"
              >{{ __("{0} selected", String(selected.size)) }}</span
            >
            <Button :label="__('Select this page')" @click="selectPage" />
            <Button
              :label="__('Merge')"
              :disabled="selected.size !== 2"
              :tooltip="
                selected.size === 2 ? '' : __('Pick the two leads to merge.')
              "
              @click="showMerge = true"
            >
              <template #prefix>
                <LucideMerge class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <Button
              variant="solid"
              :label="__('Set category')"
              :disabled="!selected.size"
              @click="showSet = true"
            />
          </div>
          <!-- what narrows the list beyond the toolbar, each one removable -->
          <div
            v-if="hasFilters"
            class="flex flex-wrap items-center gap-2"
            role="group"
            :aria-label="__('Active filters')"
          >
            <button
              v-for="chip in hiddenChips"
              :key="chip.key"
              type="button"
              class="inline-flex h-8 items-center gap-1.5 rounded-full border border-brand bg-brand-soft px-3 text-sm text-brand-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              :aria-label="__('Remove filter: {0}', chip.label)"
              @click="chip.remove()"
            >
              {{ chip.label }}
              <LucideX class="size-3.5" aria-hidden="true" />
            </button>
            <Button
              variant="ghost"
              :label="__('Clear all')"
              @click="clearFilters"
            />
          </div>
        </div>

        <template v-if="isList">
          <TaskyState
            v-if="waitingForDates"
            class="mt-6"
            :icon="LucideCalendarRange"
            :title="__('Pick both dates')"
            :message="
              __('Choose a from and a to date to see the leads created then.')
            "
          />
          <TaskyState
            v-else-if="leads.error && !data"
            class="mt-6"
            error
            :icon="LucideCircleAlert"
            :title="__('Couldn\'t load the leads')"
            :message="
              errorText(leads.error, __('Check your connection and try again.'))
            "
          >
            <Button :label="__('Try again')" @click="leads.reload()" />
          </TaskyState>

          <!-- loading: the rows' shape is known -->
          <div
            v-else-if="!data"
            class="mt-4 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-busy="true"
            :aria-label="__('Loading')"
          >
            <div
              v-for="i in 6"
              :key="i"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-4 last:border-b-0"
            >
              <div class="flex flex-1 flex-col gap-2">
                <div
                  class="h-3.5 w-1/3 animate-pulse rounded bg-surface-gray-2"
                />
                <div
                  class="h-3 w-1/2 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
              <div class="h-5 w-20 animate-pulse rounded bg-surface-gray-2" />
            </div>
          </div>

          <TaskyState
            v-else-if="!data.total && (hasFilters || view !== 'all')"
            class="mt-6"
            :icon="LucideSearchX"
            :title="__('No leads match')"
            :message="
              __(
                'Nothing in this view with these filters. Try All, or clear the filters.'
              )
            "
          >
            <Button :label="__('Show all leads')" @click="showAll" />
          </TaskyState>

          <TaskyState
            v-else-if="!data.total"
            class="mt-6"
            :icon="LucideUserPlus"
            :title="__('No leads yet')"
            :message="
              __(
                'Leads you can see on the ERP site show up here. Add the first one when someone shows interest.'
              )
            "
          >
            <Button
              variant="solid"
              :label="__('New lead')"
              @click="showNew = true"
            />
          </TaskyState>

          <template v-else>
            <div
              class="mt-4 overflow-x-auto rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-busy="leads.loading"
            >
              <table class="w-full text-sm" :aria-label="__('Leads')">
                <thead>
                  <tr
                    class="border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs text-ink-gray-6"
                  >
                    <th v-if="selecting" scope="col" class="w-10 py-2.5 pl-4">
                      <span class="sr-only">{{ __("Select") }}</span>
                    </th>
                    <th scope="col" class="px-4 py-2.5 font-medium">
                      {{ __("Lead") }}
                    </th>
                    <th
                      scope="col"
                      class="hidden px-3 py-2.5 font-medium md:table-cell"
                    >
                      {{ __("Stage") }}
                    </th>
                    <th
                      scope="col"
                      class="hidden px-3 py-2.5 font-medium md:table-cell"
                    >
                      {{ __("Owner") }}
                    </th>
                    <th
                      scope="col"
                      class="hidden px-3 py-2.5 font-medium lg:table-cell"
                    >
                      {{ __("Product") }}
                    </th>
                    <th
                      scope="col"
                      class="hidden px-3 py-2.5 font-medium lg:table-cell"
                    >
                      {{ __("Last call") }}
                    </th>
                    <th
                      scope="col"
                      class="hidden px-3 py-2.5 font-medium lg:table-cell"
                    >
                      {{ __("Next follow-up") }}
                    </th>
                    <th
                      scope="col"
                      class="hidden px-3 py-2.5 text-right font-medium xl:table-cell"
                    >
                      {{ __("Updated") }}
                    </th>
                    <th scope="col" class="w-12 py-2.5 pr-3">
                      <span class="sr-only">{{ __("Call") }}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in data.rows"
                    :key="row.name"
                    class="border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1"
                  >
                    <td v-if="selecting" class="w-10 py-3 pl-4 align-middle">
                      <Checkbox
                        :model-value="selected.has(row.name)"
                        :label="__('Select {0}', row.lead_name || row.name)"
                        @update:model-value="toggleRow(row.name)"
                      />
                    </td>
                    <td class="min-w-64 px-4 py-3 align-middle">
                      <router-link
                        :to="{ name: 'Lead', params: { leadId: row.name } }"
                        class="block rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                      >
                        <span
                          class="block truncate text-base-medium text-ink-gray-9"
                          :title="row.lead_name || row.name"
                          >{{ row.lead_name || row.name }}</span
                        >
                        <span
                          class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-6"
                        >
                          <span v-if="row.company_name" class="truncate">{{
                            row.company_name
                          }}</span>
                          <template v-if="departmentLabel(row)">
                            <span aria-hidden="true">·</span>
                            <span>
                              <span class="sr-only">{{
                                __("Department")
                              }}</span>
                              {{ departmentLabel(row) }}
                            </span>
                          </template>
                          <template v-if="row.segment">
                            <span aria-hidden="true">·</span>
                            <span>{{ row.segment }}</span>
                          </template>
                          <template v-if="categoryLabel(row)">
                            <span aria-hidden="true">·</span>
                            <span>
                              <span class="sr-only">{{ __("Category") }}</span>
                              {{ categoryLabel(row) }}
                            </span>
                          </template>
                          <template v-if="row.mobile_no || row.email_id">
                            <span aria-hidden="true">·</span>
                            <span class="truncate font-mono tabular-nums">{{
                              row.mobile_no || row.email_id
                            }}</span>
                          </template>
                          <template
                            v-if="row.score !== null && row.score !== undefined"
                          >
                            <span aria-hidden="true">·</span>
                            <span
                              class="font-mono tabular-nums"
                              :title="__('Lead score')"
                              >{{ __("Score {0}", String(row.score)) }}</span
                            >
                          </template>
                        </span>
                      </router-link>
                      <!-- on a phone the columns fold in under the name -->
                      <div
                        class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 md:hidden"
                      >
                        <TaskyBadge
                          v-if="row.tbo_stage"
                          :label="stageLabel(options, row.tbo_stage)"
                          :tone="stageTone(options, row.tbo_stage)"
                          :icon="stageIcon(row.tbo_stage)"
                        />
                        <span
                          v-if="row.next_follow_up"
                          class="text-xs tabular-nums"
                          :class="
                            followUpLate(row)
                              ? 'font-medium text-danger'
                              : 'text-ink-gray-7'
                          "
                          >{{ followUpText(row) }}</span
                        >
                        <span class="text-xs text-ink-gray-6">{{
                          row.owner_name ||
                          ownerName(options, row.lead_owner) ||
                          __("No owner")
                        }}</span>
                      </div>
                      <div
                        v-if="
                          createdNotOwned(row) ||
                          quiet.get(row.name) ||
                          statuses.get(row.name)
                        "
                        class="mt-1.5 flex flex-wrap items-center gap-1.5"
                      >
                        <!-- one they created and handed on: they read it, its owner works it -->
                        <TaskyBadge
                          v-if="createdNotOwned(row)"
                          :icon="LucideUserPlus"
                          :label="__('Created by you')"
                          :title="
                            __(
                              'You created this lead; {0} owns it now',
                              row.owner_name || row.lead_owner || ''
                            )
                          "
                          class="font-normal"
                        />
                        <!-- gone quiet: no activity for longer than its department allows -->
                        <TaskyBadge
                          v-if="quiet.get(row.name)"
                          tone="warning"
                          :icon="LucideClock"
                          :label="
                            __(
                              'No activity {0} days',
                              String(quiet.get(row.name))
                            )
                          "
                          class="font-normal tabular-nums"
                        />
                        <!-- where it stands with the client: the proposal or quotation -->
                        <TaskyBadge
                          v-if="statuses.get(row.name)"
                          :label="statuses.get(row.name)!.label"
                          :tone="statuses.get(row.name)!.tone"
                          :title="statuses.get(row.name)!.title"
                          class="font-normal tabular-nums"
                        />
                      </div>
                    </td>
                    <td class="hidden px-3 py-3 align-middle md:table-cell">
                      <TaskyBadge
                        v-if="row.tbo_stage"
                        :label="stageLabel(options, row.tbo_stage)"
                        :tone="stageTone(options, row.tbo_stage)"
                        :icon="stageIcon(row.tbo_stage)"
                      />
                    </td>
                    <td
                      class="hidden max-w-44 truncate px-3 py-3 align-middle text-ink-gray-8 md:table-cell"
                    >
                      {{
                        row.owner_name ||
                        ownerName(options, row.lead_owner) ||
                        __("No owner")
                      }}
                    </td>
                    <td
                      class="hidden max-w-40 truncate px-3 py-3 align-middle text-ink-gray-7 lg:table-cell"
                    >
                      {{ row.product }}
                    </td>
                    <td class="hidden px-3 py-3 align-middle lg:table-cell">
                      <div class="flex flex-col items-start gap-1">
                        <TaskyBadge
                          v-if="lastCall(row)"
                          :label="lastCall(row)!.label"
                          :tone="lastCall(row)!.tone"
                          :icon="lastCall(row)!.icon"
                          :title="__('Last call')"
                          class="font-normal tabular-nums"
                        />
                        <span
                          v-if="row.call_count"
                          class="font-mono text-xs tabular-nums text-ink-gray-6"
                          :title="__('Calls made to this lead')"
                          >{{
                            row.call_count === 1
                              ? __("1 call")
                              : __("{0} calls", String(row.call_count))
                          }}</span
                        >
                      </div>
                    </td>
                    <td
                      class="hidden whitespace-nowrap px-3 py-3 align-middle text-xs tabular-nums lg:table-cell"
                      :class="
                        followUpLate(row)
                          ? 'font-medium text-danger'
                          : 'text-ink-gray-7'
                      "
                    >
                      <template v-if="row.next_follow_up">
                        <LucideCalendarX
                          v-if="followUpLate(row)"
                          class="mr-1 inline size-3.5 align-text-bottom"
                          aria-hidden="true"
                        />
                        {{ followUpText(row) }}
                      </template>
                    </td>
                    <td
                      class="hidden whitespace-nowrap px-3 py-3 text-right align-middle font-mono text-xs tabular-nums text-ink-gray-6 xl:table-cell"
                    >
                      <time
                        v-if="row.modified"
                        :datetime="row.modified"
                        :title="
                          dayjs(row.modified).format('D MMM YYYY, h:mm a')
                        "
                        >{{ dayjs(row.modified).fromNow() }}</time
                      >
                    </td>
                    <td class="w-12 py-2 pr-3 align-middle">
                      <Button
                        v-if="options?.can_call && row.mobile_no"
                        variant="ghost"
                        :label="__('Call {0}', row.lead_name || row.name)"
                        :tooltip="
                          __('MyOperator rings your phone, then the lead')
                        "
                        :loading="
                          clickToCall.loading &&
                          clickToCall.params?.name === row.name
                        "
                        :disabled="clickToCall.loading"
                        @click="clickToCall.submit({ name: row.name })"
                      >
                        <template #icon>
                          <LucidePhone class="size-4" aria-hidden="true" />
                        </template>
                      </Button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <nav
              class="mt-3 flex flex-wrap items-center justify-between gap-2"
              :aria-label="__('Pages')"
            >
              <span
                class="font-mono text-p-sm tabular-nums text-ink-gray-6"
                aria-live="polite"
              >
                {{ rangeText }}
              </span>
              <div class="flex gap-2">
                <Button
                  :label="__('Previous')"
                  :disabled="page === 1 || leads.loading"
                  @click="page--"
                >
                  <template #prefix>
                    <LucideChevronLeft class="size-4" aria-hidden="true" />
                  </template>
                </Button>
                <Button
                  :label="__('Next')"
                  :disabled="page >= pageCount || leads.loading"
                  @click="page++"
                >
                  <template #suffix>
                    <LucideChevronRight class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </div>
            </nav>
          </template>
        </template>
      </div>
    </div>

    <Dialog v-model:open="showMore" :title="__('More filters')" size="2xl">
      <div class="flex flex-col gap-4">
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FormControl
            v-model="filters.segment"
            type="select"
            :label="__('Segment')"
            :options="choices(options?.segments, __('Any segment'))"
          />
          <FormControl
            v-if="departmentFilter.length"
            v-model="filters.department"
            type="select"
            :label="__('Department')"
            :options="departmentFilter"
          />
          <FormControl
            v-if="intakeOn"
            v-model="created"
            type="select"
            :label="__('Created')"
            :options="CREATED"
          />
        </div>
        <LeadCategoryFilters
          ref="categoryPanel"
          v-model="categories"
          :options="options"
          :except="['product']"
        />
      </div>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button
            v-if="hasFilters"
            :label="__('Clear all')"
            @click="clearFilters"
          />
          <Button variant="solid" :label="__('Show leads')" @click="close" />
        </div>
      </template>
    </Dialog>

    <LeadFormDialog v-model:open="showNew" @saved="openLead" />
    <MergeLeadsDialog
      v-if="selected.size === 2"
      v-model:open="showMerge"
      :first="[...selected][0]"
      :second="[...selected][1]"
      @merged="mergedLeads"
    />
    <LeadSetCategoryDialog
      v-model:open="showSet"
      :leads="[...selected]"
      @saved="categorised"
    />
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { watchDebounced } from "@vueuse/core";
import {
  Button,
  Checkbox,
  createResource,
  dayjs,
  Dialog,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClock from "~icons/lucide/clock";
import LucidePhone from "~icons/lucide/phone";
import LucidePlus from "~icons/lucide/plus";
import LucideRadar from "~icons/lucide/radar";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideListChecks from "~icons/lucide/list-checks";
import LucideMerge from "~icons/lucide/merge";
import LucideSearch from "~icons/lucide/search";
import LucideSlidersHorizontal from "~icons/lucide/sliders-horizontal";
import LucideSearchX from "~icons/lucide/search-x";
import LucideUserPlus from "~icons/lucide/user-plus";
import LucideX from "~icons/lucide/x";
import LeadCategoryFilters from "./LeadCategoryFilters.vue";
import LeadFormDialog from "./LeadFormDialog.vue";
import LeadSetCategoryDialog from "./LeadSetCategoryDialog.vue";
import MergeLeadsDialog from "./MergeLeadsDialog.vue";
import FollowUpCards from "./FollowUpCards.vue";
import MyCallCounts from "./MyCallCounts.vue";
import LeadIntakeStrip from "./LeadIntakeStrip.vue";
import LeadsBusiness from "./LeadsBusiness.vue";
import LeadsCommission from "./LeadsCommission.vue";
import LeadsOutreach from "./LeadsOutreach.vue";
import LeadsDailyReport from "./LeadsDailyReport.vue";
import LeadsOverview from "./LeadsOverview.vue";
import TodaysCalls from "./TodaysCalls.vue";
import { batchesOn, OUTCOMES } from "./callBatches";
import { REPLY_LOOK, type ReplyClass } from "./outreach";
import {
  categoryLabel,
  choices,
  clientStatus,
  departmentLabel,
  lastCall,
  LEAD_VIEWS,
  loadLeadOptions,
  useClickToCall,
  leadOptions,
  METRIC_LABELS,
  ownerName,
  stageIcon,
  stageLabel,
  stageTone,
  staleLeads,
  usableDepartments,
  type LeadIntake,
  type StaleLead,
  type LeadCategories,
  type LeadOptions,
  type LeadRow,
  type LeadMetric,
  type LeadView,
} from "./leads";

const PAGE_LENGTH = 20;
// the Overview comes first and is where the page opens (docs/leads.md)
// and the Daily report sits next to it, once the ERP site has it
type LeadTab =
  | LeadView
  | "overview"
  | "daily"
  | "business"
  | "today"
  | "outreach"
  | "commission";
const TABS: { value: LeadTab; label: string }[] = [
  { value: "today", label: __("Today's calls") },
  { value: "overview", label: __("Overview") },
  { value: "daily", label: __("Daily report") },
  { value: "outreach", label: __("Outreach") },
  { value: "commission", label: __("Commission") },
  { value: "business", label: __("Business") },
  ...LEAD_VIEWS,
];
// what a BD may open; Commission is their own, the ERP site shows them nobody else's
const BD_TABS: LeadTab[] = [
  "today",
  "call_today",
  "mine",
  "follow_up",
  "called",
  "commission",
];
const PERIOD_LABELS: Record<string, string> = {
  today: __("today"),
  yesterday: __("yesterday"),
  week: __("this week"),
  month: __("this month"),
  quarter: __("this quarter"),
};
// the Created filter: leads taken in a period (the ERP site's "intake" metric)
const CREATED = [
  { label: __("Any time"), value: "" },
  { label: __("Today"), value: "today" },
  { label: __("Yesterday"), value: "yesterday" },
  { label: __("This week"), value: "week" },
  { label: __("This month"), value: "month" },
  { label: __("Custom"), value: "custom" },
];
const overviewPanel = ref<InstanceType<typeof LeadsOverview> | null>(null);
const dailyPanel = ref<InstanceType<typeof LeadsDailyReport> | null>(null);
const todayPanel = ref<InstanceType<typeof TodaysCalls> | null>(null);
const businessPanel = ref<InstanceType<typeof LeadsBusiness> | null>(null);
const outreachPanel = ref<InstanceType<typeof LeadsOutreach> | null>(null);
const commissionPanel = ref<InstanceType<typeof LeadsCommission> | null>(null);
const callCounts = ref<InstanceType<typeof MyCallCounts> | null>(null);
const followUpCards = ref<InstanceType<typeof FollowUpCards> | null>(null);

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();
const showNew = ref(false);

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

// a salesperson whose department hands out call batches opens on them, anyone else on
// the Overview
function defaultTab(): LeadTab {
  const loaded = leadOptions.data as LeadOptions | undefined;
  // a BD never opens on the team's figures; before the options arrive they get Today's calls
  if (authStore.isSalesBd && (!loaded || !loaded.departments)) return "today";
  if (loaded?.is_bd ?? authStore.isSalesBd)
    return batchesOn(loaded) ? "today" : "call_today";
  return authStore.isSalesEmployee && batchesOn(loaded) ? "today" : "overview";
}

function queryView(): LeadTab {
  const value = queryValue("view");
  return TABS.some((v) => v.value === value)
    ? (value as LeadTab)
    : defaultTab();
}

function queryPage() {
  return Math.max(Math.floor(Number(queryValue("page"))) || 1, 1);
}

// the view, search, filters and page live in the URL, so a view can be shared
const view = ref<LeadTab>(queryView());
// a list of leads, not one of the two report tabs
const isList = computed(
  () =>
    view.value !== "overview" &&
    view.value !== "daily" &&
    view.value !== "today" &&
    view.value !== "business" &&
    view.value !== "outreach" &&
    view.value !== "commission"
);
const search = ref(queryValue("q"));
// what the list is searched for: the box, once typing pauses
const appliedSearch = ref(search.value);
watchDebounced(search, (q) => (appliedSearch.value = q), { debounce: 300 });
const filters = reactive({
  stage: queryValue("stage"),
  owner: queryValue("owner"),
  segment: queryValue("segment"),
  department: queryValue("department"),
  // "me": only the leads they created, whoever owns them now
  created_by: queryValue("created_by"),
  // the Called tab: when the lead was last called
  called: queryValue("called"),
  // the Follow-up card picked: when the follow-ups are due ("" overdue and today)
  due: queryValue("due"),
});
const CREATED_BY = [
  { label: __("Owned or created"), value: "" },
  { label: __("Created by me"), value: "me" },
];
const LAST_CALLED = [
  { label: __("Any time"), value: "" },
  { label: __("Today"), value: "today" },
  { label: __("Yesterday"), value: "yesterday" },
  { label: __("This week"), value: "week" },
  { label: __("This month"), value: "month" },
];
/** The days the Called tab's "Last called" keeps: [from, to] as YYYY-MM-DD, or nulls. */
function calledRange(value: string): [string | null, string | null] {
  const today = dayjs();
  const day = (d: typeof today) => d.format("YYYY-MM-DD");
  if (value === "today") return [day(today), day(today)];
  if (value === "yesterday")
    return [day(today.subtract(1, "day")), day(today.subtract(1, "day"))];
  if (value === "week") return [day(today.startOf("week")), day(today)];
  if (value === "month") return [day(today.startOf("month")), day(today)];
  return [null, null];
}
// Industry, State, District, Organisation size and Last call: each any of its values, kept in the
// URL as repeated keys (?industry=Resorts&industry=Hotels…)
const CATEGORY_KEYS = [
  "industry",
  "state",
  "district",
  "org_size",
  "product",
  "last_call_result",
  "last_reply_class",
] as const;
function queryList(key: string) {
  const value = route.query[key];
  return (Array.isArray(value) ? value : [value]).filter(
    (v): v is string => typeof v === "string" && !!v
  );
}
function queryCategories(): LeadCategories {
  return Object.fromEntries(
    CATEGORY_KEYS.map((key) => [key, queryList(key)])
  ) as unknown as LeadCategories;
}
const categories = ref<LeadCategories>(queryCategories());
const categoryPanel = ref<InstanceType<typeof LeadCategoryFilters> | null>(
  null
);
const productPanel = ref<InstanceType<typeof LeadCategoryFilters> | null>(null);
// the toolbar's Product and the filters in More filters count the same leads
function reloadCategories() {
  categoryPanel.value?.reload();
  productPanel.value?.reload();
}
const showMore = ref(false);
const hasCategories = computed(() =>
  CATEGORY_KEYS.some((key) => categories.value[key].length)
);
const emptyCategories = (): LeadCategories => ({
  industry: [],
  state: [],
  district: [],
  org_size: [],
  product: [],
  last_call_result: [],
  last_reply_class: [],
});

// managers pick many leads and set their category at once
const canCategorise = computed(
  () => authStore.isManager && !!options.value?.org_sizes
);
const selecting = ref(false);
const selected = ref(new Set<string>());
const showSet = ref(false);
const showMerge = ref(false);
function toggleSelecting() {
  selecting.value = !selecting.value;
  selected.value = new Set();
}
function toggleRow(name: string) {
  const next = new Set(selected.value);
  if (!next.delete(name)) next.add(name);
  selected.value = next;
}
function selectPage() {
  selected.value = new Set([
    ...selected.value,
    ...(data.value?.rows ?? []).map((r) => r.name),
  ]);
}
function categorised() {
  leads.reload();
  reloadCategories();
  leadOptions.reload();
  toggleSelecting();
}

function mergedLeads() {
  leads.reload();
  reloadCategories();
  toggleSelecting();
}

// set by a number on the Overview: the leads it counts, and its period
function queryExtra() {
  return {
    source: queryValue("source"),
    temperature: queryValue("temperature"),
    metric: queryValue("metric"),
    period: queryValue("period"),
    from: queryValue("from"),
    to: queryValue("to"),
  };
}
const extra = reactive(queryExtra());
// what the Overview opened this list with, each one removable
const extraChips = computed(() => {
  const chips: { key: string; label: string; remove: () => void }[] = [];
  if (extra.metric && extra.metric !== "intake") {
    const label = METRIC_LABELS[extra.metric as LeadMetric] || extra.metric;
    const when =
      extra.period === "custom" && extra.from && extra.to
        ? `${dayjs(extra.from).format("D MMM")} – ${dayjs(extra.to).format(
            "D MMM"
          )}`
        : PERIOD_LABELS[extra.period || "month"];
    chips.push({
      key: "metric",
      label: [
        "stale",
        "overdue",
        "hot",
        "open",
        "high_intent",
        "unhappy",
        "stage_suggested",
      ].includes(extra.metric)
        ? label
        : `${label}, ${when}`,
      remove: () =>
        Object.assign(extra, { metric: "", period: "", from: "", to: "" }),
    });
  }
  if (extra.source)
    chips.push({
      key: "source",
      label: __("Source: {0}", extra.source),
      remove: () => (extra.source = ""),
    });
  if (extra.temperature)
    chips.push({
      key: "temperature",
      label: extra.temperature,
      remove: () => (extra.temperature = ""),
    });
  return chips;
});
const CATEGORY_LABELS: Record<string, string> = {
  industry: __("Industry"),
  state: __("State"),
  district: __("District"),
  org_size: __("Organisation size"),
  last_call_result: __("Last call"),
  last_reply_class: __("Replied"),
};
function categoryValueLabel(key: string, value: string) {
  if (key === "last_call_result")
    return OUTCOMES.find((o) => o.value === value)?.label || value;
  if (key === "last_reply_class")
    return REPLY_LOOK[value as ReplyClass]?.label || value;
  return value;
}
// the filters that live in More filters, as chips under the toolbar
const hiddenChips = computed(() => {
  const chips = [...extraChips.value];
  if (filters.segment)
    chips.push({
      key: "segment",
      label: __("Segment: {0}", filters.segment),
      remove: () => (filters.segment = ""),
    });
  if (filters.department)
    chips.push({
      key: "department",
      label: __("Department: {0}", filters.department),
      remove: () => (filters.department = ""),
    });
  if (created.value)
    chips.push({
      key: "created",
      label: __(
        "Created: {0}",
        CREATED.find((c) => c.value === created.value)?.label || created.value
      ),
      remove: () => (created.value = ""),
    });
  for (const [key, label] of Object.entries(CATEGORY_LABELS))
    for (const value of categories.value[key as keyof LeadCategories])
      chips.push({
        key: `${key}:${value}`,
        label: `${label}: ${categoryValueLabel(key, value)}`,
        remove: () =>
          (categories.value = {
            ...categories.value,
            [key]: categories.value[key as keyof LeadCategories].filter(
              (v) => v !== value
            ),
          }),
      });
  return chips;
});
const page = ref(queryPage());

const hasFilters = computed(
  () =>
    !!(
      search.value.trim() ||
      filters.stage ||
      filters.owner ||
      filters.segment ||
      filters.department ||
      filters.created_by ||
      filters.called ||
      hasCategories.value ||
      extra.metric ||
      extraChips.value.length
    )
);

const created = computed({
  get: () => (extra.metric === "intake" ? extra.period || "month" : ""),
  set: (value: string) => {
    if (!value) {
      if (extra.metric === "intake")
        Object.assign(extra, { metric: "", period: "", from: "", to: "" });
      return;
    }
    const custom = value === "custom";
    Object.assign(extra, {
      metric: "intake",
      period: value,
      from: custom ? extra.from : "",
      to: custom ? extra.to : "",
    });
  },
});
// a custom period waits for both dates before the list asks for it
const waitingForDates = computed(
  () =>
    !!extra.metric &&
    extra.period === "custom" &&
    !(extra.from && extra.to && extra.from <= extra.to)
);

function clearFilters() {
  search.value = "";
  Object.assign(filters, {
    stage: "",
    owner: "",
    segment: "",
    department: "",
    created_by: "",
    called: "",
    due: "",
  });
  categories.value = emptyCategories();
  Object.assign(extra, {
    source: "",
    temperature: "",
    metric: "",
    period: "",
    from: "",
    to: "",
  });
}

function showAll() {
  clearFilters();
  view.value = "all";
}

loadLeadOptions();
const options = computed(() => leadOptions.data as LeadOptions | undefined);
const hasDaily = computed(() => !!options.value?.has_daily_report);
const canViewBusiness = computed(() => !!options.value?.can_view_business);
const hasBatches = computed(() => batchesOn(options.value));
const hasOutreach = computed(() => !!options.value?.outreach);
// a BD (a salesperson who is no manager or head) sees Today's calls, their own leads and
// follow-ups, nothing of the team's: another BD may be calling the same lead (docs/leads.md)
const isBd = computed(() => options.value?.is_bd ?? authStore.isSalesBd);
// Today's calls is the Call today list for people who get call batches: one place
const tabs = computed(() =>
  TABS.filter((tab) => {
    if (isBd.value && !BD_TABS.includes(tab.value)) return false;
    if (tab.value === "daily") return hasDaily.value;
    if (tab.value === "business") return canViewBusiness.value;
    if (tab.value === "outreach") return hasOutreach.value;
    if (tab.value === "today") return hasBatches.value;
    if (tab.value === "call_today") return !hasBatches.value;
    return true;
  })
);
const homeTab = computed<LeadTab>(defaultTab);
// the tab was picked by hand: the options arriving later don't move it
const picked = ref(false);
// an old link to a tab this person or the ERP site doesn't have
watch(options, (value) => {
  if (!value) return;
  if (!picked.value && !queryValue("view") && view.value === "overview")
    view.value = homeTab.value;
  if (!value.has_daily_report && view.value === "daily")
    view.value = "overview";
  if (!hasBatches.value && view.value === "today")
    view.value = isBd.value ? "call_today" : "overview";
  if (hasBatches.value && view.value === "call_today") view.value = "today";
  // a link to a tab the person may not open
  if (value && !value.can_view_business && view.value === "business")
    view.value = "overview";
  if (!value.outreach && view.value === "outreach") view.value = "overview";
  // an old link to a tab a BD doesn't have
  if (isBd.value && !BD_TABS.includes(view.value)) view.value = homeTab.value;
});
const clickToCall = useClickToCall();

const stageOptions = computed(() => [
  { label: __("Any stage"), value: "" },
  ...(options.value?.stages ?? []).map((s) => ({
    label: s.label || s.name,
    value: s.name,
  })),
]);
// only once the ERP site has departments; an older TBO Smart leaves the filter out
const departmentFilter = computed(() => {
  const list = usableDepartments(options.value, filters.department);
  return list.length
    ? [
        { label: __("Any department"), value: "" },
        ...list.map((d) => ({ label: d.name, value: d.name })),
      ]
    : [];
});
const ownerOptions = computed(() => [
  { label: __("Anyone"), value: "" },
  ...(options.value?.owners ?? []).map((o) => ({
    label: o.full_name || o.email,
    value: o.email,
  })),
]);

const leads = createResource({
  url: "helpdesk.api.leads.list_leads",
  makeParams: () => ({
    search: appliedSearch.value.trim() || null,
    stage: filters.stage || null,
    owner: filters.owner || null,
    segment: filters.segment || null,
    department: filters.department || null,
    ...categories.value,
    source: extra.source || null,
    temperature: extra.temperature || null,
    metric: extra.metric || null,
    period: extra.metric ? extra.period || "month" : null,
    from_date: extra.metric
      ? extra.from || null
      : view.value === "called"
      ? calledRange(filters.called)[0]
      : null,
    to_date: extra.metric
      ? extra.to || null
      : view.value === "called"
      ? calledRange(filters.called)[1]
      : null,
    // only where its control shows, so it never narrows another tab unseen
    created_by_me:
      (isBd.value || view.value === "mine") && filters.created_by === "me"
        ? 1
        : null,
    due: view.value === "follow_up" ? filters.due || null : null,
    view: isList.value ? view.value : "all",
    start: (page.value - 1) * PAGE_LENGTH,
    page_length: PAGE_LENGTH,
  }),
  auto: isList.value && !waitingForDates.value,
});

// new leads taken today and yesterday; quiet on failure (the strip just stays out). The
// Overview brings it with its own request, so only the list asks for it here.
const intake = createResource({
  url: "helpdesk.api.leads.get_lead_intake",
  auto: isList.value && !authStore.isSalesBd,
  onSuccess(data: LeadIntake) {
    intakeData.value = data;
  },
  onError() {},
});
const intakeData = ref<LeadIntake>();
const overviewSettled = ref(false);
const intakeLoading = computed(
  () => intake.loading || (view.value === "overview" && !overviewSettled.value)
);
const intakeOn = computed(() => !!intakeData.value?.available);

function takeOverviewIntake(value: LeadIntake | undefined) {
  overviewSettled.value = true;
  if (value) intakeData.value = value;
}

// the cached answer shows at once, and is asked again each time the page opens
if (isList.value) staleLeads.fetch();

watch(view, (tab) => {
  if (isList.value && !intakeData.value && !isBd.value) intake.fetch();
  if (isList.value && !staleLeads.data && !staleLeads.loading)
    staleLeads.fetch();
});

function refresh() {
  if (view.value === "today") todayPanel.value?.reload();
  else if (view.value === "overview") overviewPanel.value?.reload();
  else if (view.value === "daily") dailyPanel.value?.reload();
  else if (view.value === "business") businessPanel.value?.reload();
  else if (view.value === "outreach") outreachPanel.value?.reload();
  else if (view.value === "commission") commissionPanel.value?.reload();
  else {
    intake.submit({ fresh: 1 });
    staleLeads.submit({ fresh: 1 });
    callCounts.value?.reload();
    followUpCards.value?.reload();
    if (!waitingForDates.value) reloadLeads();
  }
}

// an older answer must not land over a newer one (a quick tab or filter change)
function reloadLeads() {
  leads.abort();
  leads.reload();
}

const data = computed(
  () => leads.data as { rows: LeadRow[]; total: number } | undefined
);
// idle days by lead name; empty while the ERP site's TBO Smart is older than this
const quiet = computed(
  () =>
    new Map(
      ((staleLeads.data?.leads ?? []) as StaleLead[]).map((l) => [
        l.name,
        l.idle_days,
      ])
    )
);
const statuses = computed(
  () => new Map((data.value?.rows ?? []).map((r) => [r.name, clientStatus(r)]))
);
const pageCount = computed(() =>
  Math.max(Math.ceil((data.value?.total ?? 0) / PAGE_LENGTH), 1)
);
const rangeText = computed(() => {
  const total = data.value?.total ?? 0;
  const first = (page.value - 1) * PAGE_LENGTH + 1;
  const last = Math.min(page.value * PAGE_LENGTH, total);
  return __("{0}–{1} of {2}", String(first), String(last), String(total));
});

// an old link, or leads removed on the ERP site: go to the last page there is
watch(data, (d) => {
  if (d && page.value > pageCount.value) page.value = pageCount.value;
});

// the URL changed from outside (the sidebar, back and forward): take its state,
// page included, without the reset to page 1 below
let fromRoute = false;
watch(
  () => route.query,
  () => {
    if (route.name !== "Leads") return;
    const wanted = {
      view: queryView(),
      q: queryValue("q"),
      stage: queryValue("stage"),
      owner: queryValue("owner"),
      segment: queryValue("segment"),
      department: queryValue("department"),
      created_by: queryValue("created_by"),
      called: queryValue("called"),
      due: queryValue("due"),
      page: queryPage(),
      extra: queryExtra(),
      categories: queryCategories(),
    };
    if (
      JSON.stringify({ ...extra }) === JSON.stringify(wanted.extra) &&
      JSON.stringify(categories.value) === JSON.stringify(wanted.categories) &&
      view.value === wanted.view &&
      appliedSearch.value.trim() === wanted.q.trim() &&
      filters.stage === wanted.stage &&
      filters.owner === wanted.owner &&
      filters.segment === wanted.segment &&
      filters.department === wanted.department &&
      filters.created_by === wanted.created_by &&
      filters.called === wanted.called &&
      (wanted.view !== "follow_up" || filters.due === wanted.due) &&
      page.value === wanted.page
    )
      return;
    fromRoute = true;
    view.value = wanted.view;
    search.value = appliedSearch.value = wanted.q;
    Object.assign(filters, {
      stage: wanted.stage,
      owner: wanted.owner,
      segment: wanted.segment,
      department: wanted.department,
      created_by: wanted.created_by,
      called: wanted.called,
      due: wanted.due,
    });
    Object.assign(extra, wanted.extra);
    categories.value = wanted.categories;
    page.value = wanted.page;
  }
);

// a new view, search or filter starts again at page 1
watch(
  [
    view,
    appliedSearch,
    () => ({ ...filters }),
    () => ({ ...extra }),
    categories,
  ],
  () => {
    if (!fromRoute) page.value = 1;
  }
);

watch(
  [
    view,
    appliedSearch,
    () => ({ ...filters }),
    () => ({ ...extra }),
    page,
    categories,
  ],
  ([v, q, f, x, p, c]) => {
    fromRoute = false;
    router.replace({
      query: {
        ...route.query,
        view: v === homeTab.value ? undefined : v,
        q: q.trim() || undefined,
        stage: f.stage || undefined,
        owner: f.owner || undefined,
        segment: f.segment || undefined,
        department: f.department || undefined,
        created_by: f.created_by || undefined,
        called: f.called || undefined,
        due: v === "follow_up" ? f.due || undefined : undefined,
        industry: c.industry.length ? c.industry : undefined,
        state: c.state.length ? c.state : undefined,
        district: c.district.length ? c.district : undefined,
        org_size: c.org_size.length ? c.org_size : undefined,
        product: c.product.length ? c.product : undefined,
        last_call_result: c.last_call_result.length
          ? c.last_call_result
          : undefined,
        last_reply_class: c.last_reply_class.length
          ? c.last_reply_class
          : undefined,
        source: x.source || undefined,
        temperature: x.temperature || undefined,
        metric: x.metric || undefined,
        // the Overview keeps its own period in the URL too
        period: x.period || undefined,
        from: x.from || undefined,
        to: x.to || undefined,
        page: p > 1 ? String(p) : undefined,
      },
    });
    if (isList.value && !waitingForDates.value) reloadLeads();
  }
);

function createdNotOwned(row: LeadRow) {
  const me = authStore.userId;
  return !!row.created_by && row.created_by === me && row.lead_owner !== me;
}

function followUpLate(row: LeadRow) {
  return (
    !!row.next_follow_up &&
    dayjs(row.next_follow_up).isBefore(dayjs().startOf("day"))
  );
}

function followUpText(row: LeadRow) {
  const day = dayjs(row.next_follow_up);
  if (day.isSame(dayjs(), "day")) return __("Follow up today");
  if (followUpLate(row))
    return __("Follow-up was due {0}", day.format("D MMM"));
  return __("Follow up {0}", day.format("D MMM"));
}

function openLead(name: string) {
  if (name) router.push({ name: "Lead", params: { leadId: name } });
  else leads.reload();
}
</script>

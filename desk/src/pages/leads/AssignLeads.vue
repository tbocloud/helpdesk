<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex min-w-0 flex-col gap-1">
          <nav
            class="flex items-center gap-1 text-sm text-ink-gray-6"
            :aria-label="__('Breadcrumb')"
          >
            <router-link
              :to="{ name: 'Leads' }"
              class="rounded hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >{{ __("Leads") }}</router-link
            >
            <LucideChevronRight class="size-3.5 shrink-0" aria-hidden="true" />
            <span aria-current="page">{{ __("Assign leads") }}</span>
          </nav>
          <h1
            class="truncate text-lg font-bold text-ink-gray-9 md:text-[22px] md:leading-[1.25] md:tracking-[-0.01em]"
          >
            {{ __("Assign leads") }}
          </h1>
          <p class="text-sm text-ink-gray-6">
            {{
              canEdit
                ? __(
                    "Pick people on the left, then choose what to do on the right."
                  )
                : __("You can watch the plans, today's calls and leads.")
            }}
          </p>
        </div>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="plans.error && !plans.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :error="!isRefusal"
          :icon="isRefusal ? LucideLock : LucideCircleAlert"
          :title="
            isRefusal
              ? __('Assign leads isn\'t available to you')
              : __('Couldn\'t load the plans')
          "
          :message="
            errorText(plans.error, __('Check your connection and try again.'))
          "
        >
          <Button
            v-if="!isRefusal"
            :label="__('Try again')"
            @click="plans.reload()"
          />
          <Button
            v-else
            :label="__('Back to leads')"
            :route="{ name: 'Leads' }"
          />
        </TaskyState>

        <div
          v-else-if="!plans.data"
          class="flex flex-col gap-4"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="h-24 animate-pulse rounded-xl bg-surface-gray-3" />
          <div class="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_26rem]">
            <div class="h-96 animate-pulse rounded-xl bg-surface-gray-3" />
            <div class="h-80 animate-pulse rounded-xl bg-surface-gray-3" />
          </div>
        </div>

        <TaskyState
          v-else-if="!plans.data.available"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideCloudOff"
          :title="__('The ERP site can\'t assign leads yet')"
          :message="
            __('It needs the latest TBO Smart. Ask an admin to update it.')
          "
        />

        <TaskyState
          v-else-if="!plans.data.departments.length"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucidePhoneOff"
          :title="__('No department hands out daily calls')"
          :message="
            __(
              'Turn on daily call batches for a department in Settings, CRM, Lead departments. Then plan its people here.'
            )
          "
        />

        <template v-else-if="current">
          <!-- the department first, on the left: everything below is its own -->
          <FormControl
            :model-value="current.department"
            type="select"
            size="md"
            class="w-full sm:w-72"
            :label="__('Department')"
            :options="departmentOptions"
            @update:model-value="pickDepartment(String($event))"
          />

          <div
            v-if="stuck"
            class="flex flex-wrap items-center gap-3 rounded-xl border border-outline-gray-2 bg-warning-soft px-4 py-3"
            role="alert"
          >
            <LucideTriangleAlert
              class="size-4 shrink-0 text-warning"
              aria-hidden="true"
            />
            <p class="min-w-0 flex-1 text-sm text-ink-gray-9">
              {{
                stuck === "zero"
                  ? __(
                      "No one in {0} gets calls from the pool: everyone's plan is 0. {1} leads are waiting.",
                      current.department,
                      String(waiting)
                    )
                  : __(
                      "{0} doesn't hand out pool leads, so the {1} waiting leads stay there. Turn it on in Settings, CRM, Lead departments.",
                      current.department,
                      String(waiting)
                    )
              }}
            </p>
            <Button
              v-if="stuck === 'zero' && canEdit"
              :label="__('Set a daily plan')"
              @click="planEveryone"
            />
          </div>

          <!-- today at a glance: one strip of four numbers -->
          <section
            class="grid grid-cols-2 rounded-xl border border-outline-gray-2 bg-surface-base lg:grid-cols-4"
            :aria-label="__('Today at a glance')"
          >
            <div
              v-for="(stat, i) in stats"
              :key="stat.label"
              class="flex min-w-0 flex-col gap-1 border-outline-gray-2 px-5 py-4"
              :class="STAT_BORDERS[i]"
            >
              <span
                class="text-[22px] font-bold leading-none tracking-[-0.02em] tabular-nums"
                :class="stat.warn ? 'text-warning' : 'text-ink-gray-9'"
                >{{ stat.value }}
                <span
                  v-if="stat.of"
                  class="ml-1 text-sm font-medium tracking-normal text-ink-gray-6"
                  >{{ stat.of }}</span
                ></span
              >
              <span class="text-sm text-ink-gray-6">{{ stat.label }}</span>
              <span v-if="stat.warn" class="text-xs text-warning">{{
                stat.warn
              }}</span>
            </div>
          </section>

          <div
            class="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_26rem] lg:items-start"
          >
            <!-- the people, and what each is handed -->
            <section
              class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="peopleHeading"
            >
              <div
                class="flex flex-wrap items-center gap-3 border-b border-outline-gray-2 px-4 py-4"
              >
                <h2
                  :id="peopleHeading"
                  class="text-base font-semibold text-ink-gray-9 tabular-nums"
                >
                  {{
                    picked.length
                      ? __("People · {0} selected", String(picked.length))
                      : __("People")
                  }}
                </h2>
                <FormControl
                  v-model="search"
                  type="search"
                  size="md"
                  class="ml-auto w-full sm:w-64"
                  :placeholder="__('Search people')"
                  :aria-label="__('Search people')"
                >
                  <template #prefix>
                    <LucideSearch
                      class="size-4 text-ink-gray-5"
                      aria-hidden="true"
                    />
                  </template>
                </FormControl>
              </div>

              <TaskyState
                v-if="!current.members.length"
                class="py-10"
                :icon="LucideUsers"
                :title="__('{0} has no members', current.department)"
                :message="
                  __(
                    'Add the people who call for it in Settings, CRM, Lead departments.'
                  )
                "
              />
              <TaskyState
                v-else-if="!shown.length"
                class="py-10"
                :icon="LucideSearch"
                :title="__('No one matches “{0}”', search)"
                :message="__('Check the spelling, or clear the search.')"
              >
                <Button :label="__('Clear search')" @click="search = ''" />
              </TaskyState>

              <template v-else>
                <div
                  class="hidden h-11 items-center gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6 md:grid"
                  :class="rowColumns"
                >
                  <span v-if="canEdit" class="flex">
                    <Checkbox
                      :model-value="allPicked"
                      :indeterminate="!!picked.length && !allPicked"
                      :aria-label="__('Pick everyone')"
                      @update:model-value="pickAll(!!$event)"
                    />
                  </span>
                  <span aria-hidden="true">{{ __("Person") }}</span>
                  <span aria-hidden="true">{{ __("Daily plan") }}</span>
                  <span aria-hidden="true">{{ __("Called today") }}</span>
                  <span aria-hidden="true" class="text-right">{{
                    __("Leads they own")
                  }}</span>
                </div>
                <ul class="divide-y divide-outline-gray-1">
                  <li
                    v-for="member in shown"
                    :key="member.user"
                    class="grid items-start gap-x-3 gap-y-2 px-4 py-3"
                    :class="[
                      rowColumns,
                      canEdit
                        ? 'cursor-pointer grid-cols-[2rem_minmax(0,1fr)] hover:bg-surface-gray-1'
                        : 'grid-cols-[minmax(0,1fr)]',
                      isPicked(member.user) &&
                        'bg-brand-soft hover:bg-brand-soft',
                    ]"
                    @click="canEdit && pickOnly(member.user)"
                  >
                    <!-- the box adds or drops one person; a click on the row picks only them -->
                    <span v-if="canEdit" class="pt-1.5" @click.stop>
                      <Checkbox
                        :model-value="isPicked(member.user)"
                        :aria-label="__('Pick {0}', member.full_name)"
                        @update:model-value="toggle(member.user, !!$event)"
                      />
                    </span>
                    <span class="flex min-w-0 items-center gap-2.5 md:pt-0.5">
                      <PersonAvatar :name="member.full_name" size="md" />
                      <span
                        class="truncate text-[13px] font-semibold text-ink-gray-9"
                      >
                        {{ member.full_name }}
                      </span>
                    </span>
                    <span
                      class="flex min-w-0 flex-col items-start gap-1"
                      :class="canEdit && 'col-start-2 md:col-start-auto'"
                    >
                      <span
                        class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium"
                        :class="PILL[planKind(current, member)]"
                      >
                        <span
                          class="size-1.5 rounded-full bg-current"
                          aria-hidden="true"
                        />
                        {{ pillText(member) }}
                      </span>
                      <span
                        v-for="line in planLines(member)"
                        :key="line"
                        class="text-xs text-ink-gray-6 tabular-nums"
                        >{{ line }}</span
                      >
                    </span>
                    <!-- on a phone, today's calls and their leads share one line -->
                    <span
                      class="flex items-start justify-between gap-3 md:contents"
                      :class="canEdit && 'col-start-2'"
                    >
                      <!-- their Today's calls, read-only -->
                      <button
                        type="button"
                        class="flex flex-col items-start gap-1 justify-self-start rounded px-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                        :aria-label="
                          __(
                            'See today\'s calls of {0}: {1} of {2} called',
                            member.full_name,
                            String(member.today.called),
                            String(member.today.size)
                          )
                        "
                        @click.stop="openCalls(member)"
                      >
                        <template v-if="member.today.size">
                          <span
                            class="block h-1.5 w-28 overflow-hidden rounded-full bg-surface-gray-3"
                            aria-hidden="true"
                          >
                            <span
                              class="block h-full rounded-full bg-success"
                              :style="{
                                width: `${Math.min(
                                  (member.today.called / member.today.size) *
                                    100,
                                  100
                                )}%`,
                              }"
                            />
                          </span>
                          <span
                            class="text-xs text-ink-gray-7 tabular-nums underline-offset-2 hover:text-ink-gray-9 hover:underline"
                            >{{
                              __(
                                "{0} of {1} called",
                                String(member.today.called),
                                String(member.today.size)
                              )
                            }}</span
                          >
                        </template>
                        <span
                          v-else
                          class="text-xs text-ink-gray-6 underline-offset-2 hover:text-ink-gray-8 hover:underline"
                          >{{ __("Nothing handed out yet") }}</span
                        >
                      </button>
                      <button
                        type="button"
                        class="shrink-0 rounded px-1 text-sm text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight md:justify-self-end"
                        :aria-label="
                          canEdit
                            ? __(
                                'See and move the leads of {0}',
                                member.full_name
                              )
                            : __('See the leads of {0}', member.full_name)
                        "
                        @click.stop="openLeads(member)"
                      >
                        <span class="font-mono font-semibold tabular-nums">{{
                          member.leads.toLocaleString()
                        }}</span>
                        <span class="ml-1 md:hidden">{{ __("leads") }}</span>
                      </button>
                    </span>
                  </li>
                </ul>
              </template>
              <p
                class="flex flex-wrap gap-x-5 gap-y-2 border-t border-outline-gray-2 px-4 py-3.5 text-xs text-ink-gray-6"
              >
                <span
                  v-for="kind in LEGEND"
                  :key="kind.kind"
                  class="flex items-center gap-1.5"
                >
                  <span
                    class="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-medium"
                    :class="PILL[kind.kind]"
                  >
                    <span
                      class="size-1.5 rounded-full bg-current"
                      aria-hidden="true"
                    />
                    {{ kind.label }}
                  </span>
                  {{ kind.help }}
                </span>
              </p>
            </section>

            <!-- a viewer watches: nothing to act on -->
            <section
              v-if="!canEdit"
              class="flex flex-col gap-2 rounded-xl border border-outline-gray-2 bg-surface-base p-4 lg:sticky lg:top-0"
              :aria-labelledby="panelHeading"
            >
              <h2
                :id="panelHeading"
                class="flex items-center gap-2 text-base font-semibold text-ink-gray-9"
              >
                <LucideEye class="size-4 text-ink-gray-6" aria-hidden="true" />
                {{ __("View only") }}
              </h2>
              <p class="text-p-sm text-ink-gray-7">
                {{
                  __(
                    "You can watch {0}: plans, today's calls and leads. Ask a Sales Manager or the department head to change them.",
                    current.department
                  )
                }}
              </p>
              <p class="text-xs text-ink-gray-5 tabular-nums" aria-live="off">
                {{ updatedText }}
              </p>
            </section>

            <!-- what to do for the people picked -->
            <section
              v-else
              class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto"
              :aria-labelledby="panelHeading"
            >
              <TaskyState
                v-if="!pickedMembers.length"
                class="px-4 py-12"
                :icon="LucideMousePointerClick"
                :title="__('Pick someone to start')"
                :message="
                  __(
                    'Pick one or more people on the list. Then give them leads now, set their daily plan, or take leads back.'
                  )
                "
              >
                <h2 :id="panelHeading" class="sr-only">
                  {{ __("Assign leads") }}
                </h2>
              </TaskyState>
              <template v-else>
                <div class="flex flex-col gap-3 px-4 pt-4">
                  <div class="flex min-w-0 items-center gap-3">
                    <PersonAvatar
                      v-if="pickedMembers.length === 1"
                      :name="pickedMembers[0].full_name"
                      size="lg"
                    />
                    <span
                      v-else
                      class="grid size-9 shrink-0 place-items-center rounded-full bg-surface-gray-3 text-sm font-semibold text-ink-gray-8 tabular-nums"
                      aria-hidden="true"
                      >{{ pickedMembers.length }}</span
                    >
                    <div class="min-w-0">
                      <h2
                        :id="panelHeading"
                        class="truncate text-base font-semibold text-ink-gray-9"
                      >
                        {{ pickedLabel }}
                      </h2>
                      <p class="truncate text-sm text-ink-gray-6 tabular-nums">
                        {{ pickedLine }}
                      </p>
                    </div>
                  </div>
                  <div
                    class="grid grid-cols-3 gap-1 rounded-lg bg-surface-gray-2 p-1"
                    role="group"
                    :aria-label="__('What to do')"
                  >
                    <button
                      v-for="option in TABS"
                      :key="option.value"
                      type="button"
                      class="h-9 rounded-md text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                      :class="
                        tab === option.value
                          ? 'bg-surface-base text-ink-gray-9 shadow-sm'
                          : 'text-ink-gray-6 hover:text-ink-gray-9'
                      "
                      :aria-pressed="tab === option.value"
                      @click="tab = option.value"
                    >
                      {{ option.label }}
                    </button>
                  </div>
                  <p class="text-p-sm text-ink-gray-6">
                    {{ TAB_HINTS[tab] }}
                  </p>
                </div>
                <AssignGiveNow
                  v-if="tab === 'give'"
                  :key="`give|${current.department}`"
                  :department="current"
                  :people="pickedMembers"
                  @changed="plans.reload()"
                  @pick-leads="openPool"
                />
                <AssignDailyPlan
                  v-else-if="tab === 'plan'"
                  :key="`plan|${current.department}`"
                  :department="current"
                  :people="pickedMembers"
                  @saved="replaceDepartment"
                />
                <AssignTakeBack
                  v-else
                  :key="`back|${current.department}`"
                  :department="current"
                  :people="pickedMembers"
                  @changed="plans.reload()"
                />
              </template>
            </section>
          </div>
        </template>
      </div>
    </div>
  </div>
  <MemberLeadsDialog
    v-if="current"
    v-model:open="showLeads"
    :department="current"
    :read-only="!canEdit"
    :member="leadsOf"
    :start-on-pool="leadsOnPool"
    :start-product="leadsProduct"
    :start-district="leadsDistrict"
    @changed="plans.reload()"
  />
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDocumentVisibility, useIntervalFn } from "@vueuse/core";
import { Button, Checkbox, createResource, FormControl } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCloudOff from "~icons/lucide/cloud-off";
import LucideEye from "~icons/lucide/eye";
import LucideLock from "~icons/lucide/lock";
import LucideMousePointerClick from "~icons/lucide/mouse-pointer-click";
import LucidePhoneOff from "~icons/lucide/phone-off";
import LucideSearch from "~icons/lucide/search";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUsers from "~icons/lucide/users";
import AssignDailyPlan from "./AssignDailyPlan.vue";
import AssignGiveNow from "./AssignGiveNow.vue";
import AssignTakeBack from "./AssignTakeBack.vue";
import MemberLeadsDialog from "./MemberLeadsDialog.vue";
import {
  byIndustry,
  leadsReady,
  memberShares,
  planKind,
  poolStuck,
  sharesText,
  type CallPlans,
  type PlanDepartment,
  type PlanKind,
  type PlanMember,
} from "./callPlans";

type Tab = "give" | "plan" | "back";

const TABS: { label: string; value: Tab }[] = [
  { label: __("Give now"), value: "give" },
  { label: __("Daily plan"), value: "plan" },
  { label: __("Take back"), value: "back" },
];
const TAB_HINTS: Record<Tab, string> = {
  give: __("Hand over waiting leads right now. They own them at once."),
  plan: __(
    "Set how many calls they get in each slot, and from which districts."
  ),
  back: __("Return leads they own to the pool, for others to get."),
};
// a status says what it is in words too: the pill's text, not only its colour
const PILL: Record<PlanKind, string> = {
  default: "bg-surface-gray-2 text-ink-gray-7",
  custom: "bg-brand-soft text-brand-ink",
  hand: "bg-warning-soft text-warning",
};
const LEGEND: { kind: PlanKind; label: string; help: string }[] = [
  {
    kind: "default",
    label: __("Default"),
    help: __("uses the department plan"),
  },
  { kind: "custom", label: __("Custom"), help: __("has their own plan") },
  { kind: "hand", label: __("No plan"), help: __("gets leads only by hand") },
];

const route = useRoute();
const router = useRouter();
const peopleHeading = useId();
const panelHeading = useId();

const plans = createResource<CallPlans>({
  url: "helpdesk.api.call_batches.get_call_plans",
  auto: true,
});

// a refusal (not a manager or head) is no failure to retry
const isRefusal = computed(
  () => plans.error?.exc_type === "LeadsForbiddenError"
);

// the department is in the URL, so a link or a reload opens the same one
const current = computed<PlanDepartment | undefined>(() => {
  const departments = plans.data?.departments ?? [];
  return (
    departments.find((d) => d.department === route.query.department) ??
    departments[0]
  );
});

const stuck = computed(() => (current.value ? poolStuck(current.value) : null));

// a department's viewer sees the page but changes nothing; an older ERP site sends no can_edit
const canEdit = computed(() => current.value?.can_edit !== false);
const rowColumns = computed(() =>
  canEdit.value
    ? "md:grid-cols-[2rem_minmax(0,1fr)_minmax(0,16rem)_9rem_6rem]"
    : "md:grid-cols-[minmax(0,1fr)_minmax(0,16rem)_9rem_6rem]"
);

// live: today's calls and the leads move all day, so the page reads again every 15 seconds
// while it is in view, and at once when it comes back into view
const LIVE_EVERY = 15_000;
const visibility = useDocumentVisibility();
const updatedAt = ref<Date>();
watch(
  () => plans.data,
  () => (updatedAt.value = new Date())
);
useIntervalFn(() => {
  if (visibility.value === "visible" && !plans.loading) plans.reload();
}, LIVE_EVERY);
watch(visibility, (state) => {
  if (state === "visible" && !plans.loading) plans.reload();
});
const updatedText = computed(() =>
  updatedAt.value
    ? __(
        "Updates by itself. Last updated {0}.",
        updatedAt.value.toLocaleTimeString()
      )
    : ""
);

const departmentOptions = computed(() =>
  (plans.data?.departments ?? []).map((d) => ({
    label: d.department,
    value: d.department,
  }))
);

function pickDepartment(name: string) {
  router.replace({ query: { ...route.query, department: name } });
}

/** The panel's tab, in the URL so a reload keeps it. */
const tab = computed<Tab>({
  get: () =>
    (["give", "plan", "back"] as Tab[]).includes(route.query.tab as Tab)
      ? (route.query.tab as Tab)
      : "give",
  set: (value) => router.replace({ query: { ...route.query, tab: value } }),
});

function openCalls(member: PlanMember) {
  router.push({
    name: "MemberCalls",
    params: { user: member.user },
    query: { name: member.full_name, department: current.value?.department },
  });
}

/** A department's saved plans, as the ERP site answered the save. */
function replaceDepartment(department: PlanDepartment) {
  if (!plans.data) return;
  plans.data.departments = plans.data.departments.map((d) =>
    d.department === department.department ? { ...d, ...department } : d
  );
}

// ---------- today at a glance ----------

const waiting = computed(() =>
  current.value ? leadsReady(current.value, null) : 0
);
const plannedPerDay = computed(() =>
  (current.value?.members ?? []).reduce((sum, m) => sum + m.total, 0)
);
const poolShort = computed(
  () =>
    !!current.value?.pull_unassigned &&
    plannedPerDay.value > 0 &&
    waiting.value < plannedPerDay.value
);
const calledToday = computed(() =>
  (current.value?.members ?? []).reduce((sum, m) => sum + m.today.called, 0)
);
const handedToday = computed(() =>
  (current.value?.members ?? []).reduce((sum, m) => sum + m.today.size, 0)
);
// a 2 × 2 grid on a phone, one row of four on a wide screen
const STAT_BORDERS = [
  "border-b border-r lg:border-b-0",
  "border-b lg:border-b-0 lg:border-r",
  "border-r",
  "",
];
const stats = computed(() => [
  {
    label: __("Leads waiting in the pool"),
    value: waiting.value.toLocaleString(),
    warn: poolShort.value ? __("Less than a day of planned calls") : "",
  },
  {
    label: __("Calls planned per day"),
    value: plannedPerDay.value.toLocaleString(),
  },
  {
    label: __("Called today"),
    value: calledToday.value.toLocaleString(),
    of: __("of {0}", handedToday.value.toLocaleString()),
  },
  {
    label: __("People on a daily plan"),
    value: __(
      "{0} of {1}",
      String(onPlan.value),
      String(current.value?.members.length ?? 0)
    ),
  },
]);
const onPlan = computed(
  () =>
    (current.value?.members ?? []).filter(
      (m) => planKind(current.value!, m) !== "hand"
    ).length
);

// ---------- the people ----------

const search = ref("");
const shown = computed(() => {
  const text = search.value.trim().toLowerCase();
  const members = current.value?.members ?? [];
  return text
    ? members.filter((m) => m.full_name.toLowerCase().includes(text))
    : members;
});

/** "Default · 100 a day", "Custom · 70 a day", "No plan". */
function pillText(member: PlanMember) {
  const kind = planKind(current.value!, member);
  if (kind === "hand") return __("No plan");
  const day = __("{0} a day", String(member.total));
  return kind === "default"
    ? __("Default · {0}", day)
    : __("Custom · {0}", day);
}

/** The plan spelled out: the product (or industry), then each slot's districts. */
function planLines(member: PlanMember) {
  const department = current.value!;
  if (planKind(department, member) === "hand")
    return [__("Gets leads only when given")];
  const what = byIndustry(department) ? member.industry : member.product;
  const shares = memberShares(department, member);
  return [
    ...(what ? [__("For {0}", what)] : []),
    ...department.slots.map(
      (slot) => `${slot.label}: ${sharesText(shares[slot.label] ?? [])}`
    ),
  ];
}

// ---------- who is picked ----------

const picked = ref<string[]>([]);
watch(
  () => current.value?.department,
  () => {
    picked.value = [];
    search.value = "";
  }
);

const isPicked = (user: string) => picked.value.includes(user);
const allPicked = computed(
  () =>
    !!current.value?.members.length &&
    picked.value.length === current.value.members.length
);

function toggle(user: string, on: boolean) {
  picked.value = on
    ? [...new Set([...picked.value, user])]
    : picked.value.filter((u) => u !== user);
}

function pickOnly(user: string) {
  picked.value = [user];
}

function pickAll(on: boolean) {
  picked.value = on ? current.value?.members.map((m) => m.user) ?? [] : [];
}

/** Everyone picked, on the Daily plan tab: the banner's way out of "everyone's plan is 0". */
function planEveryone() {
  pickAll(true);
  tab.value = "plan";
}

const pickedMembers = computed(() =>
  (current.value?.members ?? []).filter((m) => isPicked(m.user))
);
const pickedLabel = computed(() =>
  pickedMembers.value.length === 1
    ? pickedMembers.value[0].full_name
    : __("{0} people", String(pickedMembers.value.length))
);
/** "Owns 554 leads · 100 calls a day", or the names of the people picked. */
const pickedLine = computed(() => {
  const members = pickedMembers.value;
  if (members.length !== 1) return members.map((m) => m.full_name).join(", ");
  const member = members[0];
  const owns = __("Owns {0} leads", member.leads.toLocaleString());
  return planKind(current.value!, member) === "hand"
    ? `${owns} · ${__("no daily plan")}`
    : `${owns} · ${__("{0} calls a day", String(member.total))}`;
});

// ---------- a person's leads, or the waiting ones ----------

const showLeads = ref(false);
const leadsOf = ref<PlanMember | null>(null);
const leadsOnPool = ref(false);
const leadsProduct = ref("");
const leadsDistrict = ref("");
function openLeads(member: PlanMember | null) {
  leadsOf.value = member;
  leadsOnPool.value = false;
  leadsProduct.value = "";
  leadsDistrict.value = "";
  showLeads.value = true;
}

/** The waiting leads of a product (or industry) and district, ready to give to the one person
 * picked. */
function openPool(choice: string, district: string) {
  leadsOf.value =
    pickedMembers.value.length === 1 ? pickedMembers.value[0] : null;
  leadsOnPool.value = true;
  leadsProduct.value = choice;
  leadsDistrict.value = district;
  showLeads.value = true;
}
</script>

<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :icon="LucideTarget"
      :title="__('Assign sales targets')"
      :subtitle="
        __('Pick people, fill in each target for the month, then assign them.')
      "
    >
      <template #right-header>
        <label class="flex items-center gap-3">
          <span class="text-sm text-ink-gray-6">{{ __("Month") }}</span>
          <FormControl
            :model-value="month"
            type="select"
            size="md"
            class="w-44"
            :options="MONTHS"
            @update:model-value="pickMonth"
          />
        </label>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="team.error && !team.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :error="!isRefusal"
          :icon="isRefusal ? LucideLock : LucideCircleAlert"
          :title="
            isRefusal
              ? __('Assigning sales targets isn\'t open to you')
              : __('Couldn\'t load the team')
          "
          :message="
            errorText(team.error, __('Check your connection and try again.'))
          "
        >
          <Button
            v-if="!isRefusal"
            :label="__('Try again')"
            @click="team.reload()"
          />
        </TaskyState>

        <template v-else-if="!team.data">
          <div
            class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
            aria-hidden="true"
          >
            <div
              v-for="n in 4"
              :key="n"
              class="h-[76px] animate-pulse rounded-xl bg-surface-gray-3"
            />
          </div>
          <div
            class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_30rem] xl:grid-cols-[minmax(0,1fr)_38rem] 2xl:grid-cols-[minmax(0,1fr)_44rem]"
            aria-busy="true"
            :aria-label="__('Loading')"
          >
            <div class="h-96 animate-pulse rounded-xl bg-surface-gray-3" />
            <div class="h-96 animate-pulse rounded-xl bg-surface-gray-3" />
          </div>
        </template>

        <TaskyState
          v-else-if="!people.length"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideUsers"
          :title="__('No one to give targets to yet')"
          :message="
            __(
              'Give people the Presales Executive or Sales User role on their user. They show here as soon as they have it.'
            )
          "
        />

        <template v-else>
          <!-- the three steps, and how much of the team has targets -->
          <ol class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <li
              v-for="(step, index) in steps"
              :key="index"
              class="flex min-h-[76px] items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
            >
              <span
                class="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold text-brand-on tabular-nums"
                aria-hidden="true"
                >{{ index + 1 }}</span
              >
              <p class="text-sm text-ink-gray-6">
                <strong class="font-semibold text-ink-gray-9">{{
                  step.lead
                }}</strong>
                {{ step.rest }}
              </p>
            </li>
            <li
              class="flex min-h-[76px] flex-col justify-center gap-2.5 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <span class="text-sm font-semibold text-ink-gray-9">{{
                  __("Team coverage")
                }}</span>
                <span class="text-right text-sm text-ink-gray-6 tabular-nums">
                  {{
                    __(
                      "{0} of {1} have targets",
                      String(withTargets),
                      String(people.length)
                    )
                  }}
                </span>
              </div>
              <div
                class="h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                role="meter"
                :aria-valuenow="withTargets"
                aria-valuemin="0"
                :aria-valuemax="people.length"
                :aria-label="__('People with targets')"
              >
                <div
                  class="h-full rounded-full bg-success transition-[width] motion-reduce:transition-none"
                  :style="{ width: `${(withTargets / people.length) * 100}%` }"
                />
              </div>
            </li>
          </ol>

          <div
            class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_30rem] lg:items-start xl:grid-cols-[minmax(0,1fr)_38rem] 2xl:grid-cols-[minmax(0,1fr)_44rem]"
          >
            <!-- the team: who gets these targets -->
            <section
              class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="peopleHeading"
            >
              <div
                class="flex flex-col gap-3 border-b border-outline-gray-2 p-4 md:px-5"
              >
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="flex items-center gap-2">
                    <h2
                      :id="peopleHeading"
                      class="text-lg font-semibold text-ink-gray-9"
                    >
                      {{ __("People") }}
                    </h2>
                    <TaskyBadge
                      v-if="picked.length"
                      tone="brand"
                      class="tabular-nums"
                      :label="__('{0} selected', String(picked.length))"
                    />
                    <button
                      v-if="picked.length"
                      type="button"
                      class="rounded text-xs font-medium text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                      @click="picked = []"
                    >
                      {{ __("Clear") }}
                    </button>
                  </div>
                  <FormControl
                    v-model="search"
                    type="search"
                    size="md"
                    class="w-full sm:w-72"
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

                <div class="flex flex-wrap items-center justify-between gap-2">
                  <Checkbox
                    :model-value="allShownPicked"
                    :indeterminate="someShownPicked && !allShownPicked"
                    :label="__('Select all shown ({0})', String(shown.length))"
                    :disabled="!shown.length"
                    @update:model-value="pickShown(!!$event)"
                  />
                  <!-- the usual job: everyone still without targets, at once -->
                  <Button
                    v-if="withoutTargets.length && !allWithoutPicked"
                    variant="ghost"
                    :label="
                      __(
                        'Pick the {0} without targets',
                        String(withoutTargets.length)
                      )
                    "
                    @click="pickWithout"
                  >
                    <template #prefix>
                      <LucideListChecks class="size-4" />
                    </template>
                  </Button>
                </div>

                <ViewTabs
                  v-model="roleFilter"
                  class="self-start"
                  :aria-label="__('Role')"
                  :options="roleOptions"
                />
              </div>

              <TaskyState
                v-if="!shown.length"
                class="py-10"
                :icon="LucideSearch"
                :title="
                  search
                    ? __('No one matches “{0}”', search)
                    : __('No one has this role')
                "
                :message="__('Show everyone to see the whole team.')"
              >
                <Button :label="__('Show everyone')" @click="clearFilters" />
              </TaskyState>
              <ul v-else class="divide-y divide-outline-gray-1">
                <li
                  v-for="person in shown"
                  :key="person.user"
                  class="grid min-h-[72px] cursor-pointer grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 transition-colors md:px-5"
                  :class="
                    isPicked(person.user)
                      ? 'bg-brand-soft'
                      : 'hover:bg-surface-gray-1'
                  "
                  @click="pickOnly(person.user)"
                >
                  <!-- the box adds or drops one person; a click on the row picks only them -->
                  <span class="flex" @click.stop>
                    <Checkbox
                      :model-value="isPicked(person.user)"
                      :aria-label="__('Select {0}', person.full_name)"
                      @update:model-value="toggle(person.user, !!$event)"
                    />
                  </span>
                  <span class="flex min-w-0 items-center gap-3">
                    <PersonAvatar :name="person.full_name" size="lg" />
                    <span class="flex min-w-0 flex-col gap-1">
                      <span
                        class="truncate text-sm font-semibold text-ink-gray-9"
                        :title="person.full_name"
                        >{{ person.full_name }}</span
                      >
                      <span class="flex flex-wrap gap-1">
                        <TaskyBadge
                          v-for="role in person.roles"
                          :key="role"
                          :tone="ROLE_TONES[role] ?? 'neutral'"
                          :label="roleLabel(role)"
                        />
                      </span>
                    </span>
                  </span>
                  <span
                    v-if="person.target"
                    class="flex flex-col items-end gap-1 text-right"
                  >
                    <span
                      class="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-0.5 text-xs font-medium text-success tabular-nums"
                    >
                      <LucideCircleCheck class="size-3.5" aria-hidden="true" />
                      {{
                        person.target.criteria.length === 1
                          ? __("1 target")
                          : __(
                              "{0} targets",
                              String(person.target.criteria.length)
                            )
                      }}
                    </span>
                    <!-- how far they are this month, once counted -->
                    <OverallProgress
                      v-if="overallFor(person)?.percent != null"
                      :percent="overallFor(person)!.percent!"
                      :behind="overallFor(person)!.behind"
                    />
                    <span
                      v-else-if="
                        headlineAmount(person.target, team.data.currency)
                      "
                      class="font-mono text-xs text-ink-gray-6 tabular-nums"
                      >{{
                        headlineAmount(person.target, team.data.currency)
                      }}</span
                    >
                  </span>
                  <span
                    v-else
                    class="inline-flex items-center gap-1.5 rounded-full bg-surface-gray-2 px-2.5 py-0.5 text-xs font-medium text-ink-gray-6"
                  >
                    <LucideCircleDashed class="size-3.5" aria-hidden="true" />
                    {{ __("No targets yet") }}
                  </span>
                </li>
              </ul>
              <p
                class="border-t border-outline-gray-2 px-4 py-3.5 text-sm text-ink-gray-6 tabular-nums md:px-5"
              >
                {{
                  __(
                    "{0} of {1} people have targets for {2}.",
                    String(withTargets),
                    String(people.length),
                    monthTitle(month)
                  )
                }}
              </p>
            </section>

            <!-- the targets for the people picked -->
            <section
              class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)]"
              :aria-labelledby="panelHeading"
            >
              <TaskyState
                v-if="!pickedPeople.length"
                class="px-4 py-12"
                :icon="LucideMousePointerClick"
                :title="__('Pick someone to start')"
                :message="
                  __(
                    'Click a person to set their targets for {0}, or tick several to give them all the same.',
                    monthTitle(month)
                  )
                "
              >
                <h2 :id="panelHeading" class="sr-only">
                  {{ __("Targets") }}
                </h2>
              </TaskyState>
              <template v-else>
                <!-- who gets these targets: one face, or the first few overlapping -->
                <div
                  class="mx-4 mt-4 flex min-w-0 items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3"
                >
                  <span class="flex shrink-0 -space-x-2">
                    <PersonAvatar
                      v-for="person in pickedPeople.slice(0, 3)"
                      :key="person.user"
                      :name="person.full_name"
                      size="lg"
                      class="ring-2 ring-surface-gray-1"
                    />
                    <span
                      v-if="pickedPeople.length > 3"
                      class="inline-flex size-[30px] items-center justify-center rounded-full bg-surface-gray-3 text-[11px] font-semibold text-ink-gray-7 ring-2 ring-surface-gray-1 tabular-nums"
                      aria-hidden="true"
                      >+{{ pickedPeople.length - 3 }}</span
                    >
                  </span>
                  <div class="flex min-w-0 flex-1 flex-col">
                    <span
                      class="text-2xs font-semibold uppercase tracking-[0.06em] text-brand-ink"
                      >{{ __("Assigning to") }}</span
                    >
                    <h2
                      :id="panelHeading"
                      class="truncate text-sm font-semibold text-ink-gray-9"
                      :title="pickedLine"
                    >
                      {{
                        pickedPeople.length === 1
                          ? pickedPeople[0].full_name
                          : __("{0} people", String(pickedPeople.length))
                      }}
                    </h2>
                    <p
                      v-if="pickedLine"
                      class="truncate text-xs text-ink-gray-6"
                      :title="pickedLine"
                    >
                      {{ pickedLine }}
                    </p>
                  </div>
                </div>
                <TargetCriteriaForm
                  :key="formKey"
                  :month="month"
                  :currency="team.data.currency"
                  :value-types="team.data.value_types"
                  :start="startCriteria"
                  :people="pickedPeople"
                  :measures="team.data.measures"
                  :saved-for="savedOne"
                  :progress="savedOne ? personProgress.data ?? null : null"
                  @assigned="reloadAll"
                />
              </template>
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
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import ViewTabs from "@/components/ViewTabs.vue";
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Checkbox,
  createResource,
  dayjs,
  FormControl,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideListChecks from "~icons/lucide/list-checks";
import LucideLock from "~icons/lucide/lock";
import LucideMousePointerClick from "~icons/lucide/mouse-pointer-click";
import LucideSearch from "~icons/lucide/search";
import LucideTarget from "~icons/lucide/target";
import LucideUsers from "~icons/lucide/users";
import OverallProgress from "./OverallProgress.vue";
import TargetCriteriaForm from "./TargetCriteriaForm.vue";
import {
  headlineAmount,
  overallOf,
  type Progress,
  type TargetPerson,
  monthOptions,
  monthTitle,
  monthValue,
  type Criterion,
  type TeamTargets,
} from "./salesTargets";

const MONTHS = monthOptions();
const ROLE_LABELS: Record<string, string> = {
  "Presales Executive": __("Presales Executive"),
  "Sales User": __("Sales User"),
};
// each role reads apart at a glance on the list (the owner's design, 2026-11-22)
const ROLE_TONES: Record<string, Tone | "brand"> = {
  "Presales Executive": "info",
  "Sales User": "brand",
};
const roleLabel = (role: string) => ROLE_LABELS[role] ?? role;

const route = useRoute();
const router = useRouter();
const peopleHeading = useId();
const panelHeading = useId();

// the month is in the URL, so a link or a reload opens the same one
const month = computed(() => {
  const asked = String(route.query.month || "");
  return MONTHS.some((m) => m.value === asked) ? asked : monthValue();
});
function pickMonth(value: string) {
  router.replace({ query: { ...route.query, month: value } });
}

const steps = computed(() => [
  { lead: __("Pick people"), rest: __("from your team") },
  {
    lead: __("Fill in targets"),
    rest: __("for {0}", dayjs(month.value).format("MMMM")),
  },
  { lead: __("Assign"), rest: __("— they see it right away") },
]);

const team = createResource<TeamTargets>({
  url: "helpdesk.api.sales_targets.get_team",
  makeParams: () => ({ month: month.value }),
  auto: true,
});
watch(month, () => team.reload());

// how far each person is, counted from their leads: read after the list, so it shows first
const teamProgress = createResource<Record<string, Progress>>({
  url: "helpdesk.api.sales_targets.get_team_progress",
  makeParams: () => ({ month: month.value }),
});
watch(
  () => team.data,
  (data) => {
    if (data?.people.some((p) => p.target)) teamProgress.reload();
  }
);
function overallFor(person: TargetPerson) {
  const progress = teamProgress.data?.[person.user];
  return person.target && progress?.state === "counted"
    ? overallOf(person.target, progress, team.data!.currency)
    : null;
}
function reloadAll() {
  team.reload();
  if (savedOne.value) personProgress.reload();
}

// not a Sales Head: no failure to retry
const isRefusal = computed(
  () => team.error?.exc_type === "SalesTargetsForbiddenError"
);

const people = computed(() => team.data?.people ?? []);
const withTargets = computed(() => people.value.filter((p) => p.target).length);
const withoutTargets = computed(() => people.value.filter((p) => !p.target));

// ---------- which people are shown ----------

const roleFilter = ref("all");
const roleOptions = computed(() =>
  [{ label: __("All"), value: "all" }]
    .concat(
      Object.keys(ROLE_LABELS).map((role) => ({
        label: roleLabel(role),
        value: role,
      }))
    )
    .map((option) => ({
      ...option,
      count:
        option.value === "all"
          ? people.value.length
          : people.value.filter((p) => p.roles.includes(option.value)).length,
    }))
);
const search = ref("");
const shown = computed(() => {
  const text = search.value.trim().toLowerCase();
  return people.value.filter(
    (p) =>
      (roleFilter.value === "all" || p.roles.includes(roleFilter.value)) &&
      (!text ||
        p.full_name.toLowerCase().includes(text) ||
        p.user.toLowerCase().includes(text))
  );
});
function clearFilters() {
  search.value = "";
  roleFilter.value = "all";
}

// ---------- who is picked ----------

const picked = ref<string[]>([]);
const isPicked = (user: string) => picked.value.includes(user);
const allShownPicked = computed(
  () => !!shown.value.length && shown.value.every((p) => isPicked(p.user))
);
const someShownPicked = computed(() =>
  shown.value.some((p) => isPicked(p.user))
);
const allWithoutPicked = computed(
  () =>
    picked.value.length === withoutTargets.value.length &&
    withoutTargets.value.every((p) => isPicked(p.user))
);

function toggle(user: string, on: boolean) {
  picked.value = on
    ? [...new Set([...picked.value, user])]
    : picked.value.filter((u) => u !== user);
}
function pickOnly(user: string) {
  picked.value = [user];
}
/** Everyone shown under the filters, added to or dropped from the pick. */
function pickShown(on: boolean) {
  const users = shown.value.map((p) => p.user);
  picked.value = on
    ? [...new Set([...picked.value, ...users])]
    : picked.value.filter((u) => !users.includes(u));
}
/** The usual job: give everyone still without targets the same ones. */
function pickWithout() {
  picked.value = withoutTargets.value.map((p) => p.user);
}

// someone who lost their role since drops out of the pick; a link from Team targets
// (?employee= or ?pick=without) opens on that person or those people, once
watch(people, (list) => {
  const users = new Set(list.map((p) => p.user));
  picked.value = picked.value.filter((u) => users.has(u));
  const asked = String(route.query.employee || "");
  if (asked && users.has(asked)) picked.value = [asked];
  // Team targets' "Assign to N people": everyone still without targets
  else if (route.query.pick === "without") pickWithout();
  if (route.query.employee || route.query.pick) {
    const { employee: _employee, pick: _pick, ...query } = route.query;
    router.replace({ query });
  }
});

const pickedPeople = computed(() =>
  people.value.filter((p) => isPicked(p.user))
);
const pickedLine = computed(() => {
  const list = pickedPeople.value;
  if (list.length !== 1) return list.map((p) => p.full_name).join(", ");
  // one person: only whether they have targets yet, not who set them
  return list[0].target
    ? ""
    : __("No targets for {0} yet", monthTitle(month.value));
});

/** One person with targets opens on theirs; anyone else on the defaults, to fill in. */
const savedOne = computed(() =>
  pickedPeople.value.length === 1 && pickedPeople.value[0].target
    ? pickedPeople.value[0]
    : null
);
const startCriteria = computed<Criterion[]>(() => {
  if (savedOne.value)
    return savedOne.value.target!.criteria.map((c) => ({ ...c }));
  return (team.data?.defaults ?? []).map((d) => ({ ...d, target: null }));
});
// the one person's progress, shown against each target in the form
const personProgress = createResource<Progress>({
  url: "helpdesk.api.sales_targets.get_progress",
  makeParams: () => ({ month: month.value, employee: savedOne.value?.user }),
});
watch(
  () => savedOne.value && `${month.value}|${savedOne.value.user}`,
  (key) => {
    personProgress.reset();
    if (key) personProgress.reload();
  }
);

// the form starts again only when what it starts from changes: picking one more person
// keeps what the head has typed so far
const formKey = computed(() =>
  savedOne.value
    ? `${month.value}|${savedOne.value.user}|${savedOne.value.target!.modified}`
    : `${month.value}|defaults`
);
</script>

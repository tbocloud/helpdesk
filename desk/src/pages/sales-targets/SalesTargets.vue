<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Assign sales targets')"
      :subtitle="
        __(
          'Pick people, fill in their targets for the month, then assign them.'
        )
      "
    >
      <template #right-header>
        <MonthStepper
          :model-value="month"
          :options="MONTHS"
          @update:model-value="pickMonth"
        />
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

        <div
          v-else-if="!team.data"
          class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_26rem]"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="h-96 animate-pulse rounded-xl bg-surface-gray-3" />
          <div class="h-96 animate-pulse rounded-xl bg-surface-gray-3" />
        </div>

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

        <div
          v-else
          class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_26rem] lg:items-start 2xl:grid-cols-[minmax(0,1fr)_28rem]"
        >
          <!-- the team, and who still needs targets for the month -->
          <section
            class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-labelledby="peopleHeading"
          >
            <div class="flex flex-col gap-3 border-b border-outline-gray-2 p-4">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="flex min-w-0 flex-col gap-0.5">
                  <h2
                    :id="peopleHeading"
                    class="text-base font-semibold text-ink-gray-9"
                  >
                    {{ __("Team") }}
                  </h2>
                  <p class="text-sm text-ink-gray-6 tabular-nums">
                    {{
                      __(
                        "{0} of {1} have targets for {2}",
                        String(withTargets),
                        String(people.length),
                        monthTitle(month)
                      )
                    }}
                  </p>
                </div>
                <Button
                  v-if="withoutTargets.length && !allWithoutPicked"
                  size="md"
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
            </div>

            <!-- filters: search first and widest -->
            <div
              class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-3"
            >
              <FormControl
                v-model="search"
                type="search"
                size="md"
                class="min-w-[12rem] flex-1"
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
              <FormControl
                v-model="roleFilter"
                type="select"
                size="md"
                class="!w-48"
                :aria-label="__('Role')"
                :options="roleOptions"
              />
              <TabButtons
                v-model="statusFilter"
                :aria-label="__('Targets')"
                :options="statusOptions"
              />
            </div>

            <TaskyState
              v-if="!shown.length"
              class="py-10"
              :icon="
                statusFilter === 'without' && !search
                  ? LucideCircleCheck
                  : LucideSearch
              "
              :title="emptyTitle"
              :message="__('Show everyone to see the whole team.')"
            >
              <Button :label="__('Show everyone')" @click="clearFilters" />
            </TaskyState>
            <template v-else>
              <div
                class="grid h-11 grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-3 border-b border-outline-gray-1 bg-surface-gray-1 px-4 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
              >
                <span class="flex">
                  <Checkbox
                    :model-value="allShownPicked"
                    :indeterminate="someShownPicked && !allShownPicked"
                    :aria-label="__('Select everyone shown')"
                    @update:model-value="pickShown(!!$event)"
                  />
                </span>
                <span>{{ __("Person") }}</span>
                <span class="text-right">{{ monthShort }}</span>
              </div>
              <ul class="divide-y divide-outline-gray-1">
                <li
                  v-for="person in shown"
                  :key="person.user"
                  class="grid min-h-[60px] cursor-pointer grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 transition-colors"
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
                    <span class="flex min-w-0 flex-col">
                      <span
                        class="truncate text-[13px] font-semibold text-ink-gray-9"
                        :title="person.full_name"
                        >{{ person.full_name }}</span
                      >
                      <span class="truncate text-xs text-ink-gray-6">{{
                        person.roles.map(roleLabel).join(" · ")
                      }}</span>
                    </span>
                  </span>
                  <span
                    v-if="person.target"
                    class="flex flex-col items-end gap-0.5 text-right"
                  >
                    <span
                      class="flex items-center gap-1.5 text-sm font-medium text-ink-gray-8 tabular-nums"
                    >
                      <LucideCircleCheck
                        class="size-3.5 text-success"
                        aria-hidden="true"
                      />
                      {{
                        person.target.criteria.length === 1
                          ? __("1 target")
                          : __(
                              "{0} targets",
                              String(person.target.criteria.length)
                            )
                      }}
                    </span>
                    <span
                      v-if="headlineAmount(person.target, team.data.currency)"
                      class="font-mono text-xs text-ink-gray-6 tabular-nums"
                      >{{
                        headlineAmount(person.target, team.data.currency)
                      }}</span
                    >
                  </span>
                  <span
                    v-else
                    class="flex items-center gap-1.5 text-sm text-ink-gray-6"
                  >
                    <LucideCircleDashed class="size-3.5" aria-hidden="true" />
                    {{ __("Not set") }}
                  </span>
                </li>
              </ul>
            </template>
            <div
              class="flex flex-wrap items-center justify-between gap-2 border-t border-outline-gray-2 px-4 py-3 text-xs text-ink-gray-6 tabular-nums"
            >
              <span>{{
                __(
                  "Showing {0} of {1}",
                  String(shown.length),
                  String(people.length)
                )
              }}</span>
              <span v-if="picked.length" class="flex items-center gap-2">
                {{ __("{0} picked", String(picked.length)) }}
                <button
                  type="button"
                  class="rounded font-medium text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  @click="picked = []"
                >
                  {{ __("Clear") }}
                </button>
              </span>
            </div>
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
              <div
                class="flex min-w-0 items-center gap-3 border-b border-outline-gray-2 p-4"
              >
                <!-- who gets these targets: one face, or the first few overlapping -->
                <span class="flex shrink-0 -space-x-2">
                  <PersonAvatar
                    v-for="person in pickedPeople.slice(0, 3)"
                    :key="person.user"
                    :name="person.full_name"
                    size="lg"
                    class="ring-2 ring-surface-base"
                  />
                  <span
                    v-if="pickedPeople.length > 3"
                    class="inline-flex size-[30px] items-center justify-center rounded-full bg-surface-gray-3 text-[11px] font-semibold text-ink-gray-7 ring-2 ring-surface-base tabular-nums"
                    aria-hidden="true"
                    >+{{ pickedPeople.length - 3 }}</span
                  >
                </span>
                <div class="flex min-w-0 flex-1 flex-col">
                  <span class="text-xs text-ink-gray-6">{{
                    __("Assigning to")
                  }}</span>
                  <h2
                    :id="panelHeading"
                    class="truncate text-base font-semibold text-ink-gray-9"
                    :title="pickedLine"
                  >
                    {{
                      pickedPeople.length === 1
                        ? pickedPeople[0].full_name
                        : __("{0} people", String(pickedPeople.length))
                    }}
                  </h2>
                  <p
                    class="truncate text-xs text-ink-gray-6"
                    :title="pickedLine"
                  >
                    {{ pickedLine }}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  :aria-label="__('Clear the pick')"
                  @click="picked = []"
                >
                  <template #icon>
                    <LucideX class="size-4 text-ink-gray-6" />
                  </template>
                </Button>
              </div>
              <TargetCriteriaForm
                :key="formKey"
                :month="month"
                :currency="team.data.currency"
                :value-types="team.data.value_types"
                :start="startCriteria"
                :people="pickedPeople"
                @assigned="team.reload()"
              />
            </template>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Checkbox,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
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
import LucideUsers from "~icons/lucide/users";
import LucideX from "~icons/lucide/x";
import MonthStepper from "./MonthStepper.vue";
import TargetCriteriaForm from "./TargetCriteriaForm.vue";
import {
  headlineAmount,
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
/** "Nov 2026", the column heading over each person's targets */
const monthShort = computed(() => dayjs(month.value).format("MMM YYYY"));

const team = createResource<TeamTargets>({
  url: "helpdesk.api.sales_targets.get_team",
  makeParams: () => ({ month: month.value }),
  auto: true,
});
watch(month, () => team.reload());

// not a Sales Head: no failure to retry
const isRefusal = computed(
  () => team.error?.exc_type === "SalesTargetsForbiddenError"
);

const people = computed(() => team.data?.people ?? []);
const withTargets = computed(() => people.value.filter((p) => p.target).length);
const withoutTargets = computed(() => people.value.filter((p) => !p.target));

// ---------- which people are shown ----------

const roleFilter = ref("all");
const roleOptions = computed(() => [
  { label: __("All roles"), value: "all" },
  ...Object.keys(ROLE_LABELS).map((role) => ({
    label: `${roleLabel(role)} (${
      people.value.filter((p) => p.roles.includes(role)).length
    })`,
    value: role,
  })),
]);
const statusFilter = ref<"all" | "without" | "with">("all");
const statusOptions = computed(() => [
  { label: __("All"), value: "all" },
  {
    label: __("Not set ({0})", String(withoutTargets.value.length)),
    value: "without",
  },
  { label: __("Set ({0})", String(withTargets.value)), value: "with" },
]);
const search = ref("");
const shown = computed(() => {
  const text = search.value.trim().toLowerCase();
  return people.value.filter(
    (p) =>
      (roleFilter.value === "all" || p.roles.includes(roleFilter.value)) &&
      (statusFilter.value === "all" ||
        (statusFilter.value === "with") === !!p.target) &&
      (!text ||
        p.full_name.toLowerCase().includes(text) ||
        p.user.toLowerCase().includes(text))
  );
});
function clearFilters() {
  search.value = "";
  roleFilter.value = "all";
  statusFilter.value = "all";
}

// filtered to "Not set" with none left is good news, not a dead end
const emptyTitle = computed(() =>
  search.value
    ? __("No one matches “{0}”", search.value)
    : statusFilter.value === "without"
    ? __("Everyone shown has targets for {0}", monthTitle(month.value))
    : __("No one matches these filters")
);

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

// someone who lost their role since drops out of the pick
watch(people, (list) => {
  const users = new Set(list.map((p) => p.user));
  picked.value = picked.value.filter((u) => users.has(u));
});

const pickedPeople = computed(() =>
  people.value.filter((p) => isPicked(p.user))
);
const pickedLine = computed(() => {
  const list = pickedPeople.value;
  if (list.length !== 1) return list.map((p) => p.full_name).join(", ");
  const person = list[0];
  if (!person.target)
    return __("No targets for {0} yet", monthTitle(month.value));
  return __(
    "Set by {0}",
    person.target.assigned_by_name || person.target.assigned_by
  );
});

/** One person with targets opens on theirs; anyone else on the five defaults, to fill in. */
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
// the form starts again only when what it starts from changes: picking one more person
// keeps what the head has typed so far
const formKey = computed(() =>
  savedOne.value
    ? `${month.value}|${savedOne.value.user}|${savedOne.value.target!.modified}`
    : `${month.value}|defaults`
);
</script>

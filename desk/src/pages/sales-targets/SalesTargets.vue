<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Assign Sales targets')"
      :subtitle="
        __('Pick people, fill in each target for the month, then assign them.')
      "
    >
      <template #right-header>
        <FormControl
          :model-value="month"
          type="select"
          size="md"
          class="w-44"
          :aria-label="__('Month')"
          :options="MONTHS"
          @update:model-value="pickMonth(String($event))"
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
              ? __('Assign Sales targets isn\'t available to you')
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
          class="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_24rem]"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="h-96 animate-pulse rounded-xl bg-surface-gray-3" />
          <div class="h-96 animate-pulse rounded-xl bg-surface-gray-3" />
        </div>

        <TaskyState
          v-else-if="!team.data.people.length"
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
          class="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_24rem] lg:items-start 2xl:grid-cols-[minmax(0,1fr)_26rem]"
        >
          <!-- the people, and whether they have targets for the month -->
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
                class="ml-auto w-full sm:w-56"
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
            <div
              class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2.5"
            >
              <Checkbox
                :model-value="allShownPicked"
                :indeterminate="someShownPicked && !allShownPicked"
                :disabled="!shown.length"
                :label="__('Select all ({0})', String(shown.length))"
                @update:model-value="pickShown(!!$event)"
              />
              <TabButtons
                :model-value="roleFilter"
                :aria-label="__('Show')"
                :options="roleOptions"
                @update:model-value="roleFilter = $event"
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
              :message="
                search
                  ? __('Check the spelling, or clear the search.')
                  : __('Pick another role above.')
              "
            >
              <Button
                v-if="search"
                :label="__('Clear search')"
                @click="search = ''"
              />
            </TaskyState>
            <ul v-else class="divide-y divide-outline-gray-1">
              <li
                v-for="person in shown"
                :key="person.user"
                class="grid cursor-pointer grid-cols-[1.5rem_minmax(0,1fr)] items-center gap-x-3 gap-y-1 px-4 py-3 hover:bg-surface-gray-1 sm:grid-cols-[1.5rem_minmax(0,1fr)_auto]"
                :class="
                  isPicked(person.user) && 'bg-brand-soft hover:bg-brand-soft'
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
                <span class="flex min-w-0 items-center gap-2.5">
                  <PersonAvatar :name="person.full_name" size="md" />
                  <span class="flex min-w-0 flex-col">
                    <span
                      class="truncate text-[13px] font-semibold text-ink-gray-9"
                      >{{ person.full_name }}</span
                    >
                    <span class="truncate text-xs text-ink-gray-6">{{
                      person.roles.map(roleLabel).join(" · ")
                    }}</span>
                  </span>
                </span>
                <span
                  class="col-start-2 inline-flex items-center gap-1.5 justify-self-start whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium sm:col-start-3 sm:justify-self-end"
                  :class="
                    person.target
                      ? 'bg-success-soft text-success'
                      : 'bg-surface-gray-2 text-ink-gray-7'
                  "
                >
                  <component
                    :is="person.target ? LucideCircleCheck : LucideCircleDashed"
                    class="size-3.5"
                    aria-hidden="true"
                  />
                  {{
                    person.target
                      ? __(
                          "{0} targets set",
                          String(person.target.criteria.length)
                        )
                      : __("No targets yet")
                  }}
                </span>
              </li>
            </ul>
            <p
              class="border-t border-outline-gray-2 px-4 py-3.5 text-xs text-ink-gray-6 tabular-nums"
            >
              {{
                __(
                  "{0} of {1} people have targets for {2}.",
                  String(withTargets),
                  String(team.data.people.length),
                  monthTitle(month)
                )
              }}
            </p>
          </section>

          <!-- the targets for the people picked -->
          <section
            class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto"
            :aria-labelledby="panelHeading"
          >
            <TaskyState
              v-if="!pickedPeople.length"
              class="px-4 py-12"
              :icon="LucideMousePointerClick"
              :title="__('Pick someone to start')"
              :message="
                __(
                  'Pick one or more people, or Select all. Then fill in their targets for {0}.',
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
                class="flex min-w-0 items-center gap-3 border-b border-outline-gray-2 px-4 py-4"
              >
                <PersonAvatar
                  v-if="pickedPeople.length === 1"
                  :name="pickedPeople[0].full_name"
                  size="lg"
                />
                <span
                  v-else
                  class="grid size-9 shrink-0 place-items-center rounded-full bg-surface-gray-3 text-sm font-semibold text-ink-gray-8 tabular-nums"
                  aria-hidden="true"
                  >{{ pickedPeople.length }}</span
                >
                <div class="min-w-0">
                  <h2
                    :id="panelHeading"
                    class="truncate text-base font-semibold text-ink-gray-9"
                  >
                    {{
                      pickedPeople.length === 1
                        ? pickedPeople[0].full_name
                        : __("{0} people", String(pickedPeople.length))
                    }}
                  </h2>
                  <p
                    class="truncate text-sm text-ink-gray-6"
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
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideLock from "~icons/lucide/lock";
import LucideMousePointerClick from "~icons/lucide/mouse-pointer-click";
import LucideSearch from "~icons/lucide/search";
import LucideUsers from "~icons/lucide/users";
import TargetCriteriaForm from "./TargetCriteriaForm.vue";
import {
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

// ---------- which people are shown ----------

const roleFilter = ref("all");
const roleOptions = computed(() => [
  { label: __("All ({0})", String(people.value.length)), value: "all" },
  ...Object.keys(ROLE_LABELS).map((role) => ({
    label: `${roleLabel(role)} (${
      people.value.filter((p) => p.roles.includes(role)).length
    })`,
    value: role,
  })),
]);
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

// ---------- who is picked ----------

const picked = ref<string[]>([]);
const isPicked = (user: string) => picked.value.includes(user);
const allShownPicked = computed(
  () => !!shown.value.length && shown.value.every((p) => isPicked(p.user))
);
const someShownPicked = computed(() =>
  shown.value.some((p) => isPicked(p.user))
);

function toggle(user: string, on: boolean) {
  picked.value = on
    ? [...new Set([...picked.value, user])]
    : picked.value.filter((u) => u !== user);
}
function pickOnly(user: string) {
  picked.value = [user];
}
/** Select all: everyone shown under the role and search, added to or dropped from the pick. */
function pickShown(on: boolean) {
  const users = shown.value.map((p) => p.user);
  picked.value = on
    ? [...new Set([...picked.value, ...users])]
    : picked.value.filter((u) => !users.includes(u));
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
    "Assigned by {0}",
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

<template>
  <!-- new leads taken today and yesterday, and each salesperson's share against the daily target -->
  <section
    :class="
      peopleOnly
        ? 'flex flex-col'
        : 'grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3'
    "
    :aria-labelledby="headingId"
  >
    <h2 :id="headingId" class="sr-only">{{ __("New leads taken") }}</h2>
    <StatTile
      v-for="(day, index) in peopleOnly ? [] : days"
      :key="day.key"
      :label="index === 0 ? __('New leads today') : __('New leads yesterday')"
      :value="day.total"
      :icon="index === 0 ? LucidePlus : LucideCalendar"
      :icon-tone="index === 0 ? 'info' : 'success'"
      :sub="daySub(day)"
      :to="link(day.key)"
    />

    <!-- who took them: one bar per salesperson, for the day picked -->
    <div
      v-if="shown"
      class="flex min-w-0 flex-col gap-3.5 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
      :class="!peopleOnly && 'sm:col-span-2 xl:col-span-1'"
    >
      <div class="flex items-center justify-between gap-2">
        <span class="text-[13px] font-medium text-ink-gray-6">{{
          __("New leads by person")
        }}</span>
        <TabButtons
          v-if="days.length > 1"
          v-model="dayKey"
          :aria-label="__('Day')"
          :options="[
            { label: __('Today'), value: 'today' },
            { label: __('Yesterday'), value: 'yesterday' },
          ]"
        />
      </div>
      <!-- in a side column the day's total heads the card, as the stat tiles aren't there -->
      <p
        v-if="peopleOnly"
        class="flex items-baseline gap-2 text-[12px] text-ink-gray-6"
      >
        <strong class="text-[22px] font-bold tabular-nums text-ink-gray-9">{{
          shown.total
        }}</strong>
        {{ __("new leads · {0}", dayjs(shown.date).format("D MMM")) }}
      </p>
      <ul
        v-if="shown.people.length"
        role="list"
        class="flex flex-col gap-2.5"
        :aria-label="__('By salesperson, {0}', shown.label)"
      >
        <li v-for="person in shown.people" :key="person.user">
          <router-link
            :to="link(shown.key, person.user)"
            class="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          >
            <PersonAvatar :name="person.name" />
            <span
              class="w-24 truncate text-[12px] font-medium text-ink-gray-9"
              >{{ person.name }}</span
            >
            <span
              class="h-2 flex-1 overflow-hidden rounded-full bg-surface-gray-3"
              aria-hidden="true"
            >
              <span
                class="block h-full rounded-full"
                :class="person.met ? 'bg-success' : 'bg-brand'"
                :style="{ width: `${(person.count / shown.max) * 100}%` }"
              />
            </span>
            <span
              class="min-w-4 text-right text-[12px] font-bold tabular-nums text-ink-gray-9"
            >
              {{ person.count
              }}<template v-if="target"
                ><span class="font-medium text-ink-gray-6">
                  / {{ target }}</span
                ></template
              >
            </span>
            <LucideCircleCheck
              v-if="person.met"
              class="size-3.5 shrink-0 text-success"
              :aria-label="__('target met')"
            />
          </router-link>
        </li>
      </ul>
      <template v-else>
        <p class="text-p-sm text-ink-gray-6">
          {{
            shown.key === "today"
              ? __("No new leads yet today")
              : __("No new leads yesterday")
          }}
        </p>
        <p v-if="pickHint" class="text-p-sm text-ink-gray-6">
          {{
            __(
              "Pick your salespeople in Settings → Agents → Department wall → Sales team"
            )
          }}
        </p>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import StatTile from "@/components/StatTile.vue";
import { __ } from "@/translation";
import { dayjs, TabButtons } from "frappe-ui";
import { computed, ref, useId } from "vue";
import type { RouteLocationRaw } from "vue-router";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucidePlus from "~icons/lucide/plus";
import { useAuthStore } from "@/stores/auth";
import type { LeadIntake } from "./leads";

const props = defineProps<{
  intake: LeadIntake;
  /** only the by-person card, for a side column */
  peopleOnly?: boolean;
}>();

const headingId = useId();
const target = computed(() => props.intake.target || 0);
const authStore = useAuthStore();
// no one is picked as a salesperson yet: only a manager can fix that
const pickHint = computed(
  () => !!props.intake.team_empty && authStore.isManager
);

// the ERP site answers newest first: today, then yesterday
const days = computed(() => {
  const people = props.intake.people ?? [];
  return (props.intake.days ?? []).slice(0, 2).map((day, index) => {
    const counts = new Map(
      day.by_owner
        .filter((row) => row.user)
        .map((row) => [row.user as string, row])
    );
    // the sales team (the hub drops the rest), plus anyone else who took a lead that day
    const users = new Map(people.map((p) => [p.user, p.full_name]));
    counts.forEach((row, user) => {
      if (!users.has(user)) users.set(user, row.full_name || user);
    });
    return {
      key: index === 0 ? "today" : "yesterday",
      label: index === 0 ? __("Today") : __("Yesterday"),
      date: day.date,
      total: day.total,
      people: [...users.entries()]
        .map(([user, name]) => {
          const count = counts.get(user)?.count ?? 0;
          return {
            user,
            name: name || user,
            count,
            met: target.value > 0 && count >= target.value,
          };
        })
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)),
    };
  });
});

// the by-person card opens on yesterday until someone has taken a lead today
const dayKey = ref<"today" | "yesterday">(
  (props.intake.days?.[0]?.total ?? 0) > 0 ? "today" : "yesterday"
);
const shown = computed(() => {
  const day = days.value.find((d) => d.key === dayKey.value) ?? days.value[0];
  if (!day) return null;
  return {
    ...day,
    max: Math.max(1, target.value, ...day.people.map((p) => p.count)),
  };
});

/** "Fri, 14 Nov · all to Fidha V P": the day, and who took them. */
function daySub(day: (typeof days.value)[number]) {
  const date = dayjs(day.date).format("ddd, D MMM");
  const took = day.people.filter((p) => p.count);
  if (!day.total) return __("{0} · none taken yet", date);
  if (took.length === 1) return __("{0} · all to {1}", date, took[0].name);
  return __("{0} · {1} people", date, String(took.length));
}

/** The list of the leads behind a count: taken that day, by that person. */
function link(period: string, owner?: string): RouteLocationRaw {
  return {
    name: "Leads",
    query: { view: "all", metric: "intake", period, owner },
  };
}
</script>

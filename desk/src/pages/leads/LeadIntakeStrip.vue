<template>
  <!-- new leads taken today and yesterday, each salesperson against the daily target -->
  <section
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="headingId"
  >
    <h2 :id="headingId" class="sr-only">{{ __("New leads taken") }}</h2>
    <div
      class="grid divide-y divide-outline-gray-1 md:grid-cols-2 md:divide-x md:divide-y-0"
    >
      <div
        v-for="day in days"
        :key="day.key"
        class="flex min-w-0 flex-col gap-2 px-4 py-3"
      >
        <div class="flex flex-wrap items-baseline justify-between gap-x-3">
          <router-link
            :to="link(day.key)"
            class="inline-flex min-h-[36px] items-baseline gap-2 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            <span class="text-sm-medium text-ink-gray-8">{{ day.label }}</span>
            <span
              class="font-mono text-xl font-semibold tabular-nums text-ink-gray-9 underline-offset-2 hover:underline"
              >{{ day.total }}</span
            >
            <span class="text-sm text-ink-gray-6">{{
              day.total === 1 ? __("new lead") : __("new leads")
            }}</span>
          </router-link>
          <span
            class="font-mono text-xs tabular-nums text-ink-gray-5"
            :title="day.date"
            >{{ dayjs(day.date).format("D MMM") }}</span
          >
        </div>
        <ul
          v-if="day.people.length"
          role="list"
          class="flex flex-wrap gap-1.5"
          :aria-label="__('By salesperson, {0}', day.label)"
        >
          <li v-for="person in day.people" :key="person.user">
            <router-link
              :to="link(day.key, person.user)"
              class="inline-flex min-h-[36px] max-w-full items-center gap-1.5 rounded-md border border-outline-gray-2 px-2 text-xs transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              <LucideCircleCheck
                v-if="person.met"
                class="size-3.5 shrink-0 text-success"
                aria-hidden="true"
              />
              <span class="max-w-[9rem] truncate text-ink-gray-8">{{
                person.name
              }}</span>
              <span
                class="font-mono tabular-nums"
                :class="person.met ? 'text-success' : 'text-ink-gray-9'"
              >
                {{ person.count
                }}<template v-if="target"> / {{ target }}</template>
              </span>
              <span v-if="person.met" class="sr-only">{{
                __("target met")
              }}</span>
            </router-link>
          </li>
        </ul>
        <p v-else class="text-p-xs text-ink-gray-6">
          {{ __("No salespeople in your view yet.") }}
        </p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { computed, useId } from "vue";
import type { RouteLocationRaw } from "vue-router";
import LucideCircleCheck from "~icons/lucide/circle-check";
import type { LeadIntake } from "./leads";

const props = defineProps<{ intake: LeadIntake }>();

const headingId = useId();
const target = computed(() => props.intake.target || 0);

// the ERP site answers newest first: today, then yesterday
const days = computed(() => {
  const people = props.intake.people ?? [];
  return (props.intake.days ?? []).slice(0, 2).map((day, index) => {
    const counts = new Map(
      day.by_owner
        .filter((row) => row.user)
        .map((row) => [row.user as string, row])
    );
    // the scope's salespeople, plus anyone else who took a lead that day
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

/** The list of the leads behind a count: taken that day, by that person. */
function link(period: string, owner?: string): RouteLocationRaw {
  return {
    name: "Leads",
    query: { view: "all", metric: "intake", period, owner },
  };
}
</script>

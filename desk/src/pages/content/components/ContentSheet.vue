<template>
  <div
    class="overflow-x-auto rounded-lg border border-outline-gray-2 bg-surface-base"
  >
    <table class="w-full min-w-[900px] text-left text-sm">
      <thead class="bg-surface-gray-1 text-xs text-ink-gray-5">
        <tr>
          <th scope="col" class="px-3 py-2 font-medium">{{ __("Date") }}</th>
          <th scope="col" class="px-3 py-2 font-medium">
            {{ __("Copy") }}
          </th>
          <th v-if="!filtersCustomer" scope="col" class="px-3 py-2 font-medium">
            {{ __("Customer") }}
          </th>
          <th scope="col" class="px-3 py-2 font-medium">
            {{ __("Platform") }}
          </th>
          <th scope="col" class="px-3 py-2 font-medium">{{ __("Type") }}</th>
          <th scope="col" class="px-3 py-2 font-medium">{{ __("Status") }}</th>
          <th
            v-for="role in TEAM_ROLES"
            :key="role.field"
            scope="col"
            class="px-3 py-2 font-medium"
          >
            {{ __(role.label) }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!rows.length">
          <td
            :colspan="filtersCustomer ? 8 : 9"
            class="px-3 py-10 text-center text-p-sm text-ink-gray-5"
          >
            {{
              loading
                ? __("Loading…")
                : {
                    day: __("Nothing planned for this day."),
                    week: __("Nothing planned for this week."),
                    month: __("Nothing planned for this month yet."),
                  }[period || "month"]
            }}
          </td>
        </tr>
        <tr
          v-for="post in rows"
          :key="post.name"
          class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1 focus-within:bg-surface-gray-1"
          @click="emit('open', post.name)"
        >
          <td
            class="whitespace-nowrap px-3 py-2 font-mono text-xs tabular-nums text-ink-gray-7"
          >
            {{ dayjs(post.publish_on).format("ddd DD MMM, h:mm A") }}
          </td>
          <td class="max-w-[18rem] px-3 py-2">
            <button
              type="button"
              class="block max-w-full truncate text-left text-ink-gray-9 hover:underline"
              :title="post.title"
              @click.stop="emit('open', post.name)"
            >
              {{ post.title }}
            </button>
            <SpecialDayBadge
              v-if="post.special_day"
              :name="post.special_day"
              class="mt-0.5"
            />
          </td>
          <td
            v-if="!filtersCustomer"
            class="max-w-[12rem] truncate px-3 py-2 text-ink-gray-7"
          >
            {{ post.customer }}
          </td>
          <td class="px-3 py-2 text-ink-gray-7">
            {{ platformsOf(post).join(", ") }}
          </td>
          <td class="px-3 py-2 text-ink-gray-7">{{ post.format }}</td>
          <td class="px-3 py-2"><StatusPill :post="post" /></td>
          <td
            v-for="role in TEAM_ROLES"
            :key="role.field"
            class="max-w-[12rem] px-3 py-2 text-xs text-ink-gray-7"
            :title="namesOf(post, role.field).join(', ')"
          >
            <span
              v-if="!namesOf(post, role.field).length"
              class="text-ink-gray-4"
              >—</span
            >
            <span
              v-for="name in namesOf(post, role.field)"
              :key="name"
              class="block truncate"
              >{{ name }}</span
            >
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { createResource, dayjs } from "frappe-ui";
import { computed, watch } from "vue";
import {
  type ContentPost,
  platformsOf,
  type RolePerson,
  TEAM_ROLES,
  type TeamRole,
} from "../constants";
import SpecialDayBadge from "./SpecialDayBadge.vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps<{
  posts: ContentPost[];
  loading?: boolean;
  filtersCustomer?: string;
  period?: "day" | "week" | "month";
}>();

// the list carries each role's main person; this adds everyone else on it
const team = createResource({
  url: "helpdesk.api.content_board.get_team_task_status",
  makeParams: () => ({ posts: props.posts.map((p) => p.name) }),
});
watch(
  () => props.posts,
  () => props.posts.length && team.reload(),
  { immediate: true }
);

function namesOf(post: ContentPost, role: TeamRole): string[] {
  const people: RolePerson[] | undefined = team.data?.[post.name]?.[role];
  if (people) return people.map((p) => p.full_name);
  return post[role] ? [post[role]!] : [];
}
const emit = defineEmits<{ (e: "open", name: string): void }>();

const rows = computed(() =>
  props.posts
    .filter((p) => p.publish_on)
    .sort((a, b) => (a.publish_on! < b.publish_on! ? -1 : 1))
);
</script>

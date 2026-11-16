<template>
  <div
    class="overflow-x-auto rounded-xl border border-outline-gray-2 bg-surface-base"
  >
    <table class="w-full min-w-[900px] text-left text-[13px]">
      <thead>
        <tr
          class="h-11 border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
        >
          <th scope="col" class="pl-4 pr-3 md:pl-4">{{ __("Date") }}</th>
          <th scope="col" class="px-3">
            {{ __("Copy") }}
          </th>
          <th v-if="!filtersCustomer" scope="col" class="px-3">
            {{ __("Customer") }}
          </th>
          <th scope="col" class="px-3">
            {{ __("Platform") }}
          </th>
          <th scope="col" class="px-3">{{ __("Type") }}</th>
          <th scope="col" class="px-3">{{ __("Status") }}</th>
          <th
            v-for="role in TEAM_ROLES"
            :key="role.field"
            scope="col"
            class="px-3 last:pr-4 md:last:pr-5"
          >
            {{ __(role.label) }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!rows.length">
          <td
            :colspan="filtersCustomer ? 8 : 9"
            class="px-4 py-14 text-center text-p-sm text-ink-gray-6"
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
          :id="post.name === startRow ? 'sheet-from-today' : undefined"
          :key="post.name"
          class="scroll-mt-2 cursor-pointer border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1 focus-within:bg-surface-gray-1"
          @click="emit('open', post.name)"
        >
          <td
            class="whitespace-nowrap py-3 pl-4 pr-3 font-mono text-xs tabular-nums text-ink-gray-7 md:pl-4"
          >
            {{ dayjs(post.publish_on).format("ddd DD MMM, h:mm A") }}
          </td>
          <td class="max-w-[18rem] px-3 py-3">
            <button
              type="button"
              class="block max-w-full truncate text-left text-ink-gray-9 hover:underline"
              :title="copyOf(post)"
              @click.stop="emit('open', post.name)"
            >
              {{ copyOf(post) }}
            </button>
            <SpecialDayBadge
              v-if="post.special_day"
              :name="post.special_day"
              class="mt-0.5"
            />
          </td>
          <td
            v-if="!filtersCustomer"
            class="max-w-[12rem] truncate px-3 py-3 text-ink-gray-7"
          >
            {{ post.customer }}
          </td>
          <td class="px-3 py-3 text-ink-gray-7">
            {{ platformsOf(post).join(", ") }}
          </td>
          <td class="px-3 py-3 text-ink-gray-7">{{ post.format }}</td>
          <td class="px-3 py-3">
            <div class="flex flex-wrap items-center gap-1">
              <StatusPill :post="post" /><ClientApprovalChip
                :status="post.status"
              />
            </div>
          </td>
          <td
            v-for="role in TEAM_ROLES"
            :key="role.field"
            class="max-w-[12rem] px-3 py-3 text-xs text-ink-gray-7 last:pr-4 md:last:pr-5"
            :title="namesOf(post, role.field).join(', ')"
          >
            <span
              v-if="!namesOf(post, role.field).length"
              class="text-ink-gray-5"
              >—</span
            >
            <span
              v-for="name in namesOf(post, role.field)"
              :key="name"
              class="flex min-w-0 items-center gap-1.5 py-0.5"
            >
              <PersonAvatar :name="name" size="xs" />
              <span class="truncate">{{ name }}</span>
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import { __ } from "@/translation";
import { createResource, dayjs } from "frappe-ui";
import { computed, nextTick, watch } from "vue";
import {
  type ContentPost,
  platformsOf,
  type RolePerson,
  TEAM_ROLES,
  type TeamRole,
  copyOf,
} from "../constants";
import { firstFromToday, revealIfLow } from "../dayFocus";
import SpecialDayBadge from "./SpecialDayBadge.vue";
import ClientApprovalChip from "./ClientApprovalChip.vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps<{
  posts: ContentPost[];
  loading?: boolean;
  filtersCustomer?: string;
  period?: "day" | "week" | "month";
  /** The period on screen, so the sheet opens on today once per period. */
  month?: string;
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

// like the board, open on the first post from today on instead of the 1st of the month
const today = dayjs().format("YYYY-MM-DD");
const dayOf = (post: ContentPost) =>
  dayjs(post.publish_on).format("YYYY-MM-DD");
const startRow = computed(() => {
  const start = firstFromToday(rows.value.map(dayOf), today);
  return start ? rows.value.find((p) => dayOf(p) === start)?.name : undefined;
});
let openedOn: string | undefined;
watch(
  () => [props.month, props.loading, startRow.value] as const,
  async ([month, loading, row]) => {
    if (loading || !row || openedOn === month) return;
    openedOn = month;
    await nextTick();
    revealIfLow(document.getElementById("sheet-from-today"));
  },
  { immediate: true }
);
</script>

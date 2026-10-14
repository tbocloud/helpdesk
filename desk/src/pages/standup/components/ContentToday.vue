<template>
  <SectionCard
    :title="__('Content today')"
    :icon="LucideNewspaper"
    :icon-class="flagged ? 'text-danger' : undefined"
    :count="posts.length"
    :description="
      __('Posts going live today, and missed ones from the past week, first.')
    "
    to="/content"
    :link-label="__('Open content calendar')"
  >
    <ul v-if="posts.length" role="list">
      <li
        v-for="post in posts"
        :key="post.post"
        class="flex min-w-0 items-start gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
      >
        <span
          class="w-12 shrink-0 pt-0.5 font-mono text-sm tabular-nums text-ink-gray-7"
        >
          {{ dayjs(post.go_live).format("HH:mm") }}
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <RouterLink
              :to="post.route"
              class="min-w-0 text-base text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              {{ post.title }}
            </RouterLink>
            <TaskyBadge
              :tone="STATE_TONES[post.state]"
              :icon="STATE_ICONS[post.state]"
              :label="stateLabel(post)"
            />
          </div>
          <p
            class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-p-sm text-ink-gray-6"
          >
            <span v-if="post.client || post.channels.length">{{
              [post.client, post.channels.join(", ")]
                .filter(Boolean)
                .join(" · ")
            }}</span>
            <span v-if="post.state === 'missed'" class="text-danger">
              {{
                __(
                  "Was due {0}",
                  dayjs(post.go_live).format("ddd D MMM, HH:mm")
                )
              }}
            </span>
            <span
              v-if="post.people.length"
              class="inline-flex items-center gap-1"
            >
              <LucideUsers class="size-3.5" aria-hidden="true" />
              {{ post.people.map((p) => p.full_name).join(", ") }}
            </span>
          </p>
        </div>
      </li>
    </ul>
    <p
      v-else
      class="flex items-center gap-1.5 px-4 py-3 text-p-sm text-ink-gray-6"
    >
      <LucideCalendarCheck
        class="size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      {{ __("Nothing goes live today and nothing was missed this week.") }}
    </p>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { computed, type Component } from "vue";
import { RouterLink } from "vue-router";
import LucideCalendarCheck from "~icons/lucide/calendar-check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideNewspaper from "~icons/lucide/newspaper";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUsers from "~icons/lucide/users";
import type { ContentState, ContentTodayPost } from "../standupMeta";

const props = defineProps<{
  /** missed and not-approved posts first, as the server sorts them */
  posts: ContentTodayPost[];
}>();

const flagged = computed(() =>
  props.posts.some((p) => p.state === "missed" || p.state === "at_risk")
);

const STATE_TONES: Record<ContentState, Tone> = {
  missed: "danger",
  at_risk: "warning",
  published: "success",
  ready: "neutral",
};

const STATE_ICONS: Record<ContentState, Component | undefined> = {
  missed: LucideCircleAlert,
  at_risk: LucideTriangleAlert,
  published: LucideCircleCheck,
  ready: undefined,
};

function stateLabel(post: ContentTodayPost) {
  if (post.state === "missed") return __("Missed");
  if (post.state === "at_risk") return __("Not approved · {0}", __(post.stage));
  return __(post.stage);
}
</script>

<template>
  <!-- the same columns as WorkItemRow with assignees, so a lane's rows line up;
       the title's button covers the row (::after) and opens the post in place -->
  <div
    class="relative grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-4 py-3 text-left transition-colors hover:bg-surface-gray-1 focus-within:bg-surface-gray-1 md:grid-cols-[1fr_9rem_8rem_15rem]"
  >
    <div class="flex min-w-0 items-start gap-3">
      <LucideCalendarDays
        class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
        aria-hidden="true"
      />
      <div class="min-w-0">
        <div
          class="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 md:flex-nowrap"
        >
          <span class="sr-only">{{ __("Content post") }}</span>
          <button
            type="button"
            class="max-w-full truncate text-left text-base text-ink-gray-9 after:absolute after:inset-0 after:rounded after:content-[''] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-highlight"
            @click="emit('open')"
          >
            {{ copyOf(post) }}
          </button>
          <TaskyBadge
            v-if="post.at_risk"
            tone="warning"
            :icon="LucideTriangleAlert"
            :label="__('Not approved yet')"
            :title="__('Goes live within 2 days and isn\'t approved yet.')"
          />
        </div>
        <div
          class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-sm text-ink-gray-5"
        >
          <span v-if="post.customer" class="truncate">{{ post.customer }}</span>
          <span v-if="post.customer" aria-hidden="true">·</span>
          <span class="inline-flex items-center gap-1">
            <template v-for="channel in post.platforms" :key="channel">
              <ChannelIcon :channel="channel" class="size-3.5" />
              <span class="sr-only">{{ channel }}</span>
            </template>
          </span>
          <template v-if="post.format">
            <span aria-hidden="true">·</span>
            <span>{{ __(post.format) }}</span>
          </template>
          <span class="md:hidden" aria-hidden="true">·</span>
          <span class="truncate md:hidden">{{ pendingLabel }}</span>
          <span class="md:hidden" aria-hidden="true">·</span>
          <StatusPill :post="pillPost" class="md:hidden" />
        </div>
      </div>
    </div>

    <div class="hidden min-w-0 items-center gap-2 md:flex">
      <div v-if="people.length" class="flex shrink-0 -space-x-1.5">
        <Avatar
          v-for="person in people.slice(0, 3)"
          :key="person.user"
          shape="circle"
          size="sm"
          class="ring-2 ring-[var(--surface-base)]"
          :image="userStore.getUser(person.user)?.user_image"
          :label="person.full_name"
          aria-hidden="true"
        />
      </div>
      <span class="min-w-0" :title="pendingLabel">
        <span class="block truncate text-sm text-ink-gray-7">
          {{ pendingWho }}
        </span>
        <span
          v-if="pendingParts"
          class="block truncate text-xs text-ink-gray-5"
        >
          {{ pendingParts }}
        </span>
      </span>
    </div>

    <div class="hidden min-w-0 md:block">
      <StatusPill :post="pillPost" />
    </div>

    <div
      class="flex items-center justify-end gap-1 whitespace-nowrap text-sm tabular-nums"
      :class="post.is_missed ? 'font-medium text-danger' : 'text-ink-gray-5'"
      :title="liveTitle"
    >
      <LucideAlarmClock
        v-if="post.is_missed"
        class="size-3.5 shrink-0"
        aria-hidden="true"
      />
      {{ liveLabel }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { copyOf } from "@/pages/content/constants";
import TaskyBadge from "@/components/TaskyBadge.vue";
import ChannelIcon from "@/pages/content/components/ChannelIcon.vue";
import StatusPill from "@/pages/content/components/StatusPill.vue";
import type { ContentPost } from "@/pages/content/constants";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { Avatar, dayjs } from "frappe-ui";
import { computed } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { InProgressPost } from "../inProgressMeta";

const props = defineProps<{ post: InProgressPost }>();
const emit = defineEmits<{ open: [] }>();

const userStore = useUserStore();

// StatusPill reads the stage and whether it's missed from these fields alone
const pillPost = computed(
  () =>
    ({
      name: props.post.name,
      title: props.post.title,
      status: props.post.status,
      customer: props.post.customer ?? "",
      channel: props.post.platforms[0] ?? "",
      publish_on: props.post.publish_on ?? undefined,
    } as ContentPost)
);

const people = computed(() =>
  props.post.pending.flatMap((part) => part.people)
);

/** "Writer: Riya Thomas", "Client approval", or who still needs to be found. */
const pendingLabel = computed(() => {
  if (props.post.waiting_on) return props.post.waiting_on;
  if (!props.post.pending.length) return __("No one on it yet");
  return props.post.pending
    .map((part) => {
      const [first, ...rest] = part.people;
      const name = rest.length
        ? `${first.full_name} +${rest.length}`
        : first.full_name;
      return `${part.label}: ${name}`;
    })
    .join(", ");
});

// the desktop column: who on the first line, which part under it
const pendingWho = computed(() => {
  if (props.post.waiting_on) return props.post.waiting_on;
  const [first, ...rest] = people.value;
  if (!first) return __("No one on it yet");
  return rest.length ? `${first.full_name} +${rest.length}` : first.full_name;
});

const pendingParts = computed(() =>
  props.post.waiting_on
    ? ""
    : props.post.pending.map((part) => part.label).join(", ")
);

const liveLabel = computed(() => {
  if (!props.post.publish_on) return __("No date");
  const at = dayjs(props.post.publish_on);
  if (props.post.is_missed) return __("Missed · {0}", at.format("D MMM"));
  const days = at.startOf("day").diff(dayjs().startOf("day"), "day");
  if (days === 0) return __("Live today {0}", at.format("h:mm A"));
  if (days === 1) return __("Live tomorrow {0}", at.format("h:mm A"));
  return __("Live {0}", at.format("ddd D MMM"));
});

const liveTitle = computed(() =>
  props.post.publish_on
    ? __(
        "Goes live {0}",
        dayjs(props.post.publish_on).format("D MMM YYYY, h:mm A")
      )
    : undefined
);
</script>

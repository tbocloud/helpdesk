<template>
  <section class="flex flex-col gap-4" :aria-label="__('Publish to Meta')">
    <div
      v-if="state.loading && !data"
      class="h-24 animate-pulse rounded-lg bg-surface-gray-1"
      aria-busy="true"
    />
    <p
      v-else-if="state.error && !data"
      role="alert"
      class="flex flex-wrap items-center gap-2 text-p-sm text-danger"
    >
      <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
      {{ errorText(state.error, __("Couldn't load the Meta details.")) }}
      <Button
        type="button"
        variant="ghost"
        :label="__('Try again')"
        @click="state.reload()"
      />
    </p>

    <template v-else-if="data">
      <!-- connection -->
      <div
        class="flex flex-wrap items-center gap-2 rounded-lg border border-outline-gray-2 px-3 py-2"
      >
        <TaskyBadge
          v-if="data.connection?.status === 'Connected'"
          tone="success"
          :icon="LucideCircleCheck"
          :label="__('Connected')"
        />
        <TaskyBadge
          v-else
          :tone="data.connection ? 'danger' : 'neutral'"
          :icon="data.connection ? LucideCircleAlert : LucideUnlink"
          :label="data.connection ? __('Needs attention') : __('Not connected')"
        />
        <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">
          <template v-if="data.connection?.page_name">
            {{ data.connection.page_name }}
            <template v-if="data.connection.instagram_username">
              · @{{ data.connection.instagram_username }}
            </template>
          </template>
        </span>
        <router-link
          v-if="data.project && !data.connection?.page_name"
          :to="{ name: 'TaskyMeta', params: { projectId: data.project } }"
          class="rounded text-sm font-medium text-brand-ink underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        >
          {{ __("Connect Meta on the project") }}
        </router-link>
      </div>

      <p
        v-if="!data.can_publish"
        class="flex items-start gap-2 text-p-sm text-ink-gray-7"
        role="note"
      >
        <LucideLock class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{
          __(
            "Only the project's managers and the Digital Marketing Head can publish to Meta."
          )
        }}
      </p>
      <p
        v-else-if="data.blocked_reason"
        class="flex items-start gap-2 text-p-sm text-ink-gray-7"
        role="note"
      >
        <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ data.blocked_reason }}
      </p>

      <!-- per-target results -->
      <ul v-if="data.publishes.length" class="flex flex-col gap-2" role="list">
        <li
          v-for="row in data.publishes"
          :key="row.target"
          class="flex flex-col gap-1 rounded-lg border border-outline-gray-2 px-3 py-2"
        >
          <div class="flex flex-wrap items-center gap-2">
            <ChannelIcon :channel="row.target" class="size-4 shrink-0" />
            <span class="text-sm-medium text-ink-gray-9">{{
              __(row.target)
            }}</span>
            <TaskyBadge
              :tone="ROW_STATUS[row.status].tone"
              :icon="ROW_STATUS[row.status].icon"
              :label="__(ROW_STATUS[row.status].label)"
            />
            <span
              v-if="row.status === 'Queued' && row.publish_at"
              class="text-p-sm tabular-nums text-ink-gray-6"
            >
              {{ dayjs(row.publish_at).format("ddd D MMM, h:mm A") }}
            </span>
            <a
              v-if="row.permalink"
              :href="row.permalink"
              target="_blank"
              rel="noopener"
              class="ms-auto inline-flex items-center gap-1 rounded text-sm text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >
              <LucideExternalLink class="size-3.5" aria-hidden="true" />
              {{ __("View post") }}
            </a>
          </div>
          <p v-if="row.error" role="alert" class="text-p-sm text-danger">
            {{ row.error }}
            <template v-if="row.status === 'Queued'">
              {{ __("Trying again soon.") }}
            </template>
          </p>
        </li>
      </ul>

      <!-- what will be posted, and where -->
      <template v-if="data.can_publish && !data.blocked_reason">
        <fieldset class="flex flex-col gap-2">
          <legend class="mb-1 text-xs text-ink-gray-5">
            {{ __("Post to") }}
          </legend>
          <label
            v-for="t in data.targets"
            :key="t.name"
            class="flex min-h-11 items-center gap-2 text-base text-ink-gray-8"
            :class="!t.available && 'opacity-60'"
          >
            <input
              v-model="targets"
              type="checkbox"
              :value="t.name"
              :disabled="!t.available"
              class="size-4 accent-brand"
            />
            <ChannelIcon :channel="t.name" class="size-4" />
            {{ __(t.name) }}
            <span v-if="!t.available" class="text-p-sm text-ink-gray-6">
              {{ __("(no Instagram account linked to the Page)") }}
            </span>
          </label>
        </fieldset>

        <div class="flex flex-col gap-1 text-p-sm text-ink-gray-7">
          <p v-if="data.media_problem" role="alert" class="text-danger">
            {{ data.media_problem }}
          </p>
          <p v-else>
            <span class="font-medium text-ink-gray-8">{{ __("Format:") }}</span>
            {{ kindLabel }}
            <template v-if="data.media.length">
              · {{ data.media.map((m) => m.name).join(", ") }}
            </template>
          </p>
          <p v-if="data.caption" class="line-clamp-3 whitespace-pre-line">
            <span class="font-medium text-ink-gray-8">{{
              __("Caption:")
            }}</span>
            {{ data.caption }}
          </p>
          <p v-else class="text-ink-gray-5">
            {{ __("No caption yet: add Sub copy to the post.") }}
          </p>
        </div>

        <label
          v-if="data.media.length === 1"
          class="flex min-h-11 items-center gap-2 text-base text-ink-gray-8"
        >
          <input v-model="story" type="checkbox" class="size-4 accent-brand" />
          {{ __("Post as an Instagram Story (no caption, Instagram only)") }}
        </label>

        <TabButtons
          v-model="mode"
          :aria-label="__('When to publish')"
          :options="[
            { label: __('Publish now'), value: 'now' },
            { label: __('Schedule'), value: 'later' },
          ]"
        />
        <div
          v-if="mode === 'later'"
          class="grid grid-cols-1 gap-3 sm:grid-cols-2"
        >
          <FormControl v-model="date" type="date" :label="__('Date')" />
          <FormControl
            v-model="time"
            type="time"
            format="h:mm A"
            :interval="5"
            :label="__('Time')"
          />
        </div>

        <ErrorMessage :message="error" />
        <div class="flex flex-wrap justify-end gap-2">
          <Button
            v-if="queued"
            type="button"
            :label="__('Cancel scheduled posts')"
            :loading="busy === 'cancel'"
            @click="unschedule"
          />
          <Button
            type="button"
            variant="solid"
            :label="mode === 'now' ? __('Publish now') : __('Schedule')"
            :loading="busy === 'publish'"
            :disabled="!targets.length || !!data.media_problem"
            @click="publish"
          >
            <template #prefix>
              <component
                :is="mode === 'now' ? LucideSend : LucideCalendarClock"
                class="size-4"
                aria-hidden="true"
              />
            </template>
          </Button>
        </div>
      </template>
    </template>
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  dayjs,
  ErrorMessage,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, onBeforeUnmount, ref, watch, type Component } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideInfo from "~icons/lucide/info";
import LucideLoader from "~icons/lucide/loader";
import LucideLock from "~icons/lucide/lock";
import LucideSend from "~icons/lucide/send";
import LucideUnlink from "~icons/lucide/unlink";
import type { ContentPost } from "../constants";
import ChannelIcon from "./ChannelIcon.vue";

interface PublishRow {
  target: string;
  status: "Queued" | "Publishing" | "Published" | "Failed";
  publish_at?: string | null;
  permalink?: string | null;
  error?: string | null;
}
interface PublishState {
  project?: string | null;
  can_publish: boolean;
  blocked_reason?: string | null;
  connection: {
    status: string;
    page_name?: string | null;
    instagram_username?: string | null;
  } | null;
  targets: { name: string; available: boolean }[];
  default_targets: string[];
  kind?: string | null;
  media_problem?: string | null;
  media: { name: string; kind: string }[];
  caption: string;
  default_publish_at?: string | null;
  publishes: PublishRow[];
}

const props = defineProps<{ post: ContentPost | null; open: boolean }>();
const emit = defineEmits<{ (e: "changed"): void }>();

const ROW_STATUS: Record<
  PublishRow["status"],
  { label: string; tone: Tone; icon: Component }
> = {
  Queued: { label: "Queued", tone: "info", icon: LucideClock },
  Publishing: { label: "Publishing", tone: "info", icon: LucideLoader },
  Published: { label: "Published", tone: "success", icon: LucideCircleCheck },
  Failed: { label: "Failed", tone: "danger", icon: LucideCircleAlert },
};
const KIND_LABELS: Record<string, string> = {
  Text: __("Text post (Facebook)"),
  Image: __("Single image"),
  Carousel: __("Carousel"),
  Video: __("Video / Reel"),
};

const targets = ref<string[]>([]);
const story = ref(false);
const mode = ref<"now" | "later">("now");
const date = ref("");
const time = ref("10:00");
const error = ref("");
const busy = ref<"publish" | "cancel" | null>(null);

const state = createResource({
  url: "helpdesk.api.meta.get_publish_state",
  makeParams: () => ({ post: props.post?.name }),
  onSuccess: keepPolling,
});
const data = computed(() => state.data as PublishState | undefined);
const queued = computed(() =>
  data.value?.publishes.some((r) => r.status === "Queued")
);
const kindLabel = computed(() =>
  story.value
    ? __("Instagram Story")
    : KIND_LABELS[data.value?.kind ?? ""] ?? ""
);

// the rows change by themselves (the worker, the scheduler), so look again while one is open
let timer: ReturnType<typeof setTimeout> | undefined;
function keepPolling(next: PublishState) {
  clearTimeout(timer);
  if (
    props.open &&
    next.publishes.some(
      (r) => r.status === "Publishing" || r.status === "Queued"
    )
  )
    timer = setTimeout(() => state.reload(), 5000);
}
onBeforeUnmount(() => clearTimeout(timer));

watch(
  () => [props.open, props.post?.name],
  ([isOpen]) => {
    clearTimeout(timer);
    if (!isOpen || !props.post) return;
    error.value = "";
    story.value = false;
    mode.value = "now";
    state.reload().then((next: PublishState | undefined) => {
      if (!next) return;
      targets.value = next.default_targets.filter((t) =>
        next.targets.some((x) => x.name === t && x.available)
      );
      const planned = dayjs(next.default_publish_at || undefined);
      date.value = planned.format("YYYY-MM-DD");
      time.value = planned.format("HH:mm");
    });
  },
  { immediate: true }
);

async function publish() {
  error.value = "";
  busy.value = "publish";
  try {
    await call("helpdesk.api.meta.publish", {
      post: props.post!.name,
      targets: targets.value,
      story: story.value,
      publish_at:
        mode.value === "later" ? `${date.value} ${time.value}:00` : undefined,
    });
    toast.success(
      mode.value === "now"
        ? __("Publishing now. This page updates when it's live.")
        : __("Scheduled. The hub posts it at that time.")
    );
    await state.reload();
    emit("changed");
  } catch (e) {
    error.value = errorText(e, __("Couldn't publish. Try again."));
  } finally {
    busy.value = null;
  }
}

async function unschedule() {
  error.value = "";
  busy.value = "cancel";
  try {
    await call("helpdesk.api.meta.unschedule", { post: props.post!.name });
    await state.reload();
    emit("changed");
  } catch (e) {
    error.value = errorText(e, __("Couldn't cancel. Try again."));
  } finally {
    busy.value = null;
  }
}
</script>

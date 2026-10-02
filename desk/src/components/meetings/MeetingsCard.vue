<template>
  <section
    v-if="visible"
    :class="flush ? '' : 'px-5 py-4'"
    :aria-labelledby="headingId"
  >
    <div class="mb-2.5 flex items-center justify-between gap-2">
      <h2
        :id="headingId"
        class="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5"
      >
        <LucideVideo class="size-3.5" aria-hidden="true" />
        {{ __("Meetings") }}
      </h2>
      <Button
        v-if="data?.enabled"
        size="sm"
        variant="ghost"
        :label="__('Schedule')"
        :icon-left="LucidePlus"
        @click="showSchedule = true"
      />
    </div>

    <p
      v-if="!data?.upcoming.length && !data?.earlier.length"
      class="text-p-xs text-ink-gray-5"
    >
      {{ __("No meetings yet. Schedule a Teams call with the customer.") }}
    </p>

    <ul v-if="data?.upcoming.length" role="list" class="flex flex-col gap-2">
      <li
        v-for="m in data.upcoming"
        :key="m.name"
        class="rounded-md border border-outline-gray-2 p-2.5"
      >
        <p class="font-mono text-xs tabular-nums text-ink-gray-6">
          {{ when(m) }}
        </p>
        <p class="mt-0.5 text-sm text-ink-gray-8">{{ m.subject }}</p>
        <p class="mt-0.5 text-xs text-ink-gray-5">
          {{ replies(m) }}
        </p>
        <div class="mt-2 flex flex-wrap gap-2">
          <Button
            v-if="m.join_url"
            size="sm"
            :variant="startsSoon(m) ? 'solid' : 'subtle'"
            :label="__('Join')"
            :icon-left="LucideVideo"
            :link="m.join_url"
          />
          <Button
            v-if="m.can_cancel"
            size="sm"
            variant="ghost"
            :label="__('Cancel meeting')"
            @click="cancelling = m"
          />
        </div>
      </li>
    </ul>

    <details v-if="data?.earlier.length" class="mt-2 text-xs">
      <summary
        class="cursor-pointer rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
      >
        {{ __("Earlier ({0})", String(data.earlier.length)) }}
      </summary>
      <ul role="list" class="mt-1.5 flex flex-col gap-1">
        <li v-for="m in data.earlier" :key="m.name" class="text-ink-gray-6">
          <span class="font-mono tabular-nums">{{ when(m) }}</span>
          · {{ m.subject }}
          <span v-if="m.status === 'Cancelled'" class="text-ink-gray-5">
            ({{ __("cancelled") }})
          </span>
        </li>
      </ul>
    </details>

    <ScheduleMeetingDialog
      v-if="showSchedule"
      v-model:open="showSchedule"
      :reference-doctype="referenceDoctype"
      :reference-name="referenceName"
      @scheduled="onChanged"
    />

    <Dialog
      :open="!!cancelling"
      :title="__('Cancel meeting?')"
      size="md"
      @update:open="(isOpen: boolean) => !isOpen && (cancelling = null)"
    >
      <div class="flex flex-col gap-3">
        <p class="text-p-sm text-ink-gray-7">
          {{
            __(
              "Outlook tells everyone invited that {0} is cancelled.",
              cancelling?.subject || ""
            )
          }}
        </p>
        <Textarea
          v-model="cancelReason"
          :label="__('Message to attendees (optional)')"
          :rows="2"
        />
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Keep it')" @click="cancelling = null" />
          <Button
            variant="solid"
            theme="red"
            :label="__('Cancel meeting')"
            :loading="cancel.loading"
            @click="confirmCancel"
          />
        </div>
      </template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  Textarea,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, inject, ref, useId, watch } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideVideo from "~icons/lucide/video";
import { meetingsChanged } from "./meetingsBus";
import ScheduleMeetingDialog from "./ScheduleMeetingDialog.vue";

interface MeetingRow {
  name: string;
  subject: string;
  starts_on: string;
  ends_on: string;
  status: "Scheduled" | "Cancelled";
  join_url: string | null;
  attendee_count: number;
  accepted: number;
  declined: number;
  can_cancel: boolean;
}

interface MeetingsData {
  enabled: boolean;
  upcoming: MeetingRow[];
  earlier: MeetingRow[];
}

const props = defineProps<{
  referenceDoctype: "HD Ticket" | "Task";
  referenceName: string;
  // no padding of its own, for use inside a padded dialog
  flush?: boolean;
}>();

const SOON_MINUTES = 15;
const refreshTicket = inject<() => void>("refreshTicket", () => {});
const headingId = `meetings-${useId()}`;
const showSchedule = ref(false);
const cancelling = ref<MeetingRow | null>(null);
const cancelReason = ref("");

const meetings = createResource({
  url: "helpdesk.api.meetings.get_meetings",
  makeParams: () => ({
    reference_doctype: props.referenceDoctype,
    reference_name: props.referenceName,
  }),
  auto: true,
});
watch(
  () => [props.referenceDoctype, props.referenceName],
  () => meetings.reload()
);
watch(meetingsChanged, () => meetings.reload());

const data = computed<MeetingsData | null>(() => meetings.data ?? null);
// hidden until Teams meetings are set up, unless meetings already exist
const visible = computed(
  () =>
    !!data.value &&
    (data.value.enabled ||
      data.value.upcoming.length > 0 ||
      data.value.earlier.length > 0)
);

function when(m: MeetingRow) {
  const start = dayjs(m.starts_on);
  const day = start.isSame(dayjs(), "day")
    ? __("Today")
    : start.isSame(dayjs().add(1, "day"), "day")
    ? __("Tomorrow")
    : start.format("ddd D MMM");
  return `${day}, ${start.format("HH:mm")}–${dayjs(m.ends_on).format("HH:mm")}`;
}

// replies come from Outlook every 15 minutes
function replies(m: MeetingRow) {
  const parts = [__("{0} invited", String(m.attendee_count))];
  if (m.accepted) parts.push(__("{0} accepted", String(m.accepted)));
  if (m.declined) parts.push(__("{0} declined", String(m.declined)));
  return parts.join(" · ");
}

function startsSoon(m: MeetingRow) {
  return dayjs(m.starts_on).diff(dayjs(), "minute") <= SOON_MINUTES;
}

function onChanged() {
  meetings.reload();
  // the internal note about the meeting shows in the activity
  refreshTicket();
}

const cancel = createResource({
  url: "helpdesk.api.meetings.cancel_meeting",
  onSuccess() {
    toast.success(__("Meeting cancelled. Attendees have been told."));
    cancelling.value = null;
    cancelReason.value = "";
    onChanged();
  },
  onError(err: any) {
    toast.error(err?.messages?.[0] || __("Couldn't cancel the meeting."));
  },
});

function confirmCancel() {
  if (!cancelling.value) return;
  cancel.submit({
    meeting: cancelling.value.name,
    reason: cancelReason.value.trim(),
  });
}
</script>

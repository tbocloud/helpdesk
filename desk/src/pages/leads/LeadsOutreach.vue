<template>
  <div class="flex flex-col gap-4">
    <TaskyState
      v-if="outbox.error && !shown"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the outbox')"
      :message="
        errorText(outbox.error, __('Check your connection and try again.'))
      "
    >
      <Button :label="__('Try again')" @click="reload" />
    </TaskyState>

    <div
      v-else-if="!shown"
      class="flex flex-col gap-3"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="h-12 animate-pulse rounded-xl bg-surface-gray-2" />
      <div class="h-56 animate-pulse rounded-xl bg-surface-gray-2" />
    </div>

    <TaskyState
      v-else-if="!shown.available"
      :icon="LucideCloudOff"
      :title="__('Outreach isn\'t available yet')"
      :message="__('The ERP site needs the latest TBO Smart.')"
    />

    <TaskyState
      v-else-if="!shown.enabled"
      :icon="LucideMailX"
      :title="__('Outreach is switched off')"
      :message="
        __(
          'An admin can switch it on in TBO Smart Settings on the ERP site, under Outreach.'
        )
      "
    />

    <template v-else>
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div class="overflow-x-auto">
          <TabButtons
            :model-value="status"
            size="md"
            :aria-label="__('Which messages')"
            :options="statusTabs"
            @update:model-value="pick($event as OutreachStatus)"
          />
        </div>
        <p
          v-if="shown.cap"
          class="ml-auto flex flex-col items-end text-p-sm text-ink-gray-7 sm:flex-row sm:items-center sm:gap-3"
        >
          <span>
            {{ __("Emails today") }}
            <span class="font-mono tabular-nums text-ink-gray-9"
              >{{ shown.cap.used }} / {{ shown.cap.limit }}</span
            >
            ·
            <span class="font-mono tabular-nums text-ink-gray-9">{{
              shown.cap.left
            }}</span>
            {{ __("left") }}
          </span>
          <span
            v-if="shown.window && !shown.window.open"
            class="text-ink-gray-6"
          >
            {{
              __(
                "Outside sending hours ({0} to {1}): approved emails go out from {2}.",
                shown.window.start,
                shown.window.end,
                dayjs(shown.window.next).format("ddd D MMM, h:mm a")
              )
            }}
          </span>
        </p>
      </div>

      <p
        v-if="shown.drafting"
        role="status"
        class="flex items-center gap-2 rounded-lg border border-outline-gray-2 bg-surface-base px-3 py-2 text-p-sm text-ink-gray-8"
      >
        <LucideLoader
          class="size-4 animate-spin text-ink-gray-6"
          aria-hidden="true"
        />
        {{
          __(
            "Drafting {0} of {1}. Drafts appear here as they are written.",
            String(shown.drafting.done + shown.drafting.failed),
            String(shown.drafting.total)
          )
        }}
      </p>

      <p
        v-if="!shown.email_ready && hasEmail"
        role="alert"
        class="flex items-start gap-2 rounded-lg border border-outline-gray-2 bg-warning-soft px-3 py-2 text-p-sm text-ink-gray-9"
      >
        <LucideTriangleAlert
          class="mt-0.5 size-4 shrink-0 text-warning"
          aria-hidden="true"
        />
        {{
          __(
            "Set up an outgoing email account first. Until then emails can't be approved; ask an admin to add one on the ERP site (Email Account, default outgoing)."
          )
        }}
      </p>

      <p
        v-if="outbox.error"
        role="alert"
        class="flex flex-wrap items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-base px-3 py-2 text-p-sm text-ink-gray-8"
      >
        <LucideCircleAlert
          class="size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        {{ errorText(outbox.error, __("Couldn't update the outbox.")) }}
        <Button class="ml-auto" :label="__('Try again')" @click="reload" />
      </p>

      <div
        v-if="rows.length && canSelect"
        class="flex flex-wrap items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-base px-4 py-2"
      >
        <Checkbox
          :model-value="allPicked"
          :label="__('Select all')"
          @update:model-value="toggleAll"
        />
        <span class="text-p-sm text-ink-gray-6" aria-live="polite">{{
          picked.size ? __("{0} selected", String(picked.size)) : ""
        }}</span>
        <div class="ml-auto flex gap-2">
          <Button
            v-if="status === 'Draft'"
            variant="solid"
            :label="__('Approve selected')"
            :disabled="!picked.size"
            :loading="approve.loading"
            @click="approveMany"
          />
          <Button
            :label="__('Cancel selected')"
            :disabled="!picked.size"
            :loading="cancel.loading"
            @click="cancelMany([...picked])"
          />
        </div>
      </div>

      <TaskyState
        v-if="!rows.length"
        :icon="LucideInbox"
        :title="empty.title"
        :message="empty.message"
      >
        <Button
          v-if="status === 'Draft' && options?.can_find_prospects"
          :label="__('Find prospects')"
          :route="{ name: 'FindProspects' }"
        />
      </TaskyState>

      <ul
        v-else
        class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
        role="list"
        :aria-label="__('Messages')"
        :aria-busy="outbox.loading"
      >
        <OutreachRow
          v-for="message in rows"
          :key="message.name"
          :message="message"
          :selected="picked.has(message.name)"
          :selectable="canSelect"
          :show-owner="showOwner"
          :opt-out="shown.opt_out"
          :busy="acting.has(message.name)"
          @toggle="toggleRow(message.name)"
          @save="(edits) => save(message, edits)"
          @approve="(edits) => approveOne(message, edits)"
          @regenerate="regenerate(message)"
          @cancel="cancelMany([message.name])"
          @mark-sent="markSent(message)"
        />
      </ul>
    </template>
  </div>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useIntervalFn } from "@vueuse/core";
import {
  Button,
  call,
  Checkbox,
  createResource,
  dayjs,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCloudOff from "~icons/lucide/cloud-off";
import LucideInbox from "~icons/lucide/inbox";
import LucideLoader from "~icons/lucide/loader";
import LucideMailX from "~icons/lucide/mail-x";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { LeadOptions } from "./leads";
import OutreachRow from "./OutreachRow.vue";
import {
  OUTREACH_STATUSES,
  STATUS_LOOK,
  useOutreachAction,
  type Outbox,
  type OutreachMessage,
  type OutreachResult,
  type OutreachStatus,
} from "./outreach";

defineProps<{ options?: LeadOptions }>();

const API = "helpdesk.api.outreach";
const DRAFTING_POLL_MS = 3000;

const status = ref<OutreachStatus>("Draft");
const picked = reactive(new Set<string>());
const acting = reactive(new Set<string>());

const outbox = createResource({
  url: `${API}.get_outbox`,
  makeParams: () => ({ status: status.value }),
  auto: true,
});
const shown = computed(() => outbox.data as Outbox | null);
const rows = computed(() => shown.value?.rows ?? []);
const hasEmail = computed(() => rows.value.some((m) => m.channel === "Email"));
// a head or manager also sees other people's messages: say whose
const showOwner = computed(() =>
  rows.value.some((m) => m.owner !== rows.value[0]?.owner)
);
const canSelect = computed(
  () => status.value !== "Sent" && status.value !== "Cancelled"
);
const allPicked = computed(
  () => rows.value.length > 0 && rows.value.every((m) => picked.has(m.name))
);

const statusTabs = computed(() =>
  OUTREACH_STATUSES.map((value) => ({
    value,
    label: `${STATUS_LOOK[value].label} ${shown.value?.counts?.[value] ?? 0}`,
  }))
);

const EMPTY: Record<OutreachStatus, { title: string; message: string }> = {
  Draft: {
    title: __("No drafts to review"),
    message: __(
      "Draft first messages from a prospect run, then read, edit and approve them here. Nothing is sent until you approve."
    ),
  },
  Approved: {
    title: __("Nothing approved is waiting"),
    message: __(
      "Emails you approve go out at once during sending hours; WhatsApp messages wait here until you send them and mark them sent."
    ),
  },
  Sent: {
    title: __("Nothing sent yet"),
    message: __("Messages that went out appear here."),
  },
  Failed: {
    title: __("Nothing failed"),
    message: __("An email that couldn't be sent shows its error here."),
  },
  Cancelled: {
    title: __("Nothing cancelled"),
    message: __("Cancelled messages are kept here."),
  },
};
const empty = computed(() => EMPTY[status.value]);

function reload() {
  outbox.reload();
}
defineExpose({ reload });

function pick(next: OutreachStatus) {
  status.value = next;
  picked.clear();
  outbox.reload();
}

// drafts appear while the AI writes them
const { pause, resume } = useIntervalFn(reload, DRAFTING_POLL_MS, {
  immediate: false,
});
watch(
  () => !!shown.value?.drafting,
  (busy) => (busy ? resume() : pause()),
  { immediate: true }
);

function toggleRow(name: string) {
  if (!picked.delete(name)) picked.add(name);
}
function toggleAll() {
  if (allPicked.value) picked.clear();
  else rows.value.forEach((m) => picked.add(m.name));
}

// ---- what became of each message, in words ----

function report(results: OutreachResult[]) {
  const count = (state: OutreachStatus) =>
    results.filter((r) => r.status === state).length;
  const parts = [
    count("Sent") && __("{0} sent", String(count("Sent"))),
    count("Approved") && __("{0} approved", String(count("Approved"))),
    count("Cancelled") && __("{0} cancelled", String(count("Cancelled"))),
  ].filter(Boolean);
  // an approved message may carry a note (waiting for the window); anything else with words is a problem
  const problems = results.filter((r) => r.message && r.status !== "Approved");
  if (parts.length) toast.success(parts.join(", "));
  if (problems.length) toast.error(problems[0].message);
  const notes = results.filter((r) => r.status === "Approved" && r.message);
  if (notes.length && !problems.length) toast.info(notes[0].message);
  picked.clear();
  outbox.reload();
}

const approve = useOutreachAction(`${API}.approve_outreach`, report);
const cancel = useOutreachAction(`${API}.cancel_outreach`, report);

async function guarded(names: string[], work: () => Promise<void>) {
  names.forEach((n) => acting.add(n));
  try {
    await work();
  } catch (e) {
    toast.error(errorText(e, __("That didn't work. Try again.")));
  } finally {
    names.forEach((n) => acting.delete(n));
  }
}

async function saveEdits(
  message: OutreachMessage,
  edits: { subject: string; body: string }
) {
  await call(`${API}.update_outreach`, {
    name: message.name,
    subject: edits.subject || null,
    body: edits.body,
  });
}

function save(
  message: OutreachMessage,
  edits: { subject: string; body: string }
) {
  return guarded([message.name], async () => {
    await saveEdits(message, edits);
    toast.success(__("Saved"));
    outbox.reload();
  });
}

function approveOne(
  message: OutreachMessage,
  edits: { subject: string; body: string }
) {
  return guarded([message.name], async () => {
    await saveEdits(message, edits);
    report(await call(`${API}.approve_outreach`, { names: [message.name] }));
  });
}

function approveMany() {
  approve.submit({ names: [...picked] });
}

function cancelMany(names: string[]) {
  cancel.submit({ names });
}

function regenerate(message: OutreachMessage) {
  return guarded([message.name], async () => {
    await call(`${API}.regenerate_outreach`, { name: message.name });
    toast.success(__("Written again"));
    outbox.reload();
  });
}

function markSent(message: OutreachMessage) {
  return guarded([message.name], async () => {
    report(await call(`${API}.mark_outreach_sent`, { names: [message.name] }));
  });
}
</script>

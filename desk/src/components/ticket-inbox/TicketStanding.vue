<template>
  <!-- where the ticket stands (Phase 16), always on top of its conversation: whose move it is in
       words with the SLA, and Copilot's line with the buttons for the step it is at -->
  <section
    class="shrink-0 border-b border-outline-gray-1 px-4 py-2.5 sm:px-5"
    :class="copilot.needsYou.value ? 'bg-warning-soft' : 'bg-surface-base'"
    :aria-label="__('Where this ticket stands')"
  >
    <div class="flex flex-wrap items-start gap-x-4 gap-y-2">
      <!-- the words keep at least 16rem; with less room the buttons go under them -->
      <div class="min-w-0 flex-1 basis-64 space-y-1">
        <p
          class="flex items-start gap-2 text-base font-medium"
          :class="move.tone === 'late' ? 'text-danger' : 'text-ink-gray-9'"
        >
          <component
            :is="move.icon"
            class="mt-0.5 size-4 shrink-0"
            :class="move.iconClass"
            aria-hidden="true"
          />
          <span class="min-w-0">
            {{ move.text }}
            <Tooltip v-if="due && showDue" :text="due.hint">
              <TaskyBadge
                :tone="due.tone"
                :icon="due.icon"
                class="ms-1.5 align-middle"
              >
                {{ due.label }}
                <span class="sr-only">, {{ due.hint }}</span>
              </TaskyBadge>
            </Tooltip>
          </span>
        </p>
        <p
          v-if="copilot.now.value"
          class="flex items-start gap-2 text-base text-ink-gray-8"
        >
          <component
            :is="copilotIcon.icon"
            class="mt-0.5 size-4 shrink-0"
            :class="copilotIcon.class"
            aria-hidden="true"
          />
          <span class="line-clamp-2 min-w-0" :title="copilot.now.value.line">
            <span
              v-if="copilot.needsYou.value"
              class="me-1.5 rounded-full bg-surface-base px-2 py-0.5 text-xs font-semibold text-warning"
              >{{ __("Needs you") }}</span
            >
            <span
              v-else-if="
                copilot.now.value.state &&
                copilot.now.value.state !== copilot.now.value.line
              "
              class="me-1 text-ink-gray-5"
              >{{ __("Copilot") }} · {{ copilot.now.value.state }} ·</span
            >
            {{ copilot.now.value.line }}
          </span>
        </p>
        <p
          v-else-if="copilot.thread.loading"
          class="h-5 w-2/3 animate-pulse rounded bg-surface-gray-2"
          aria-hidden="true"
        />
      </div>
      <div class="flex flex-wrap items-center gap-1.5">
        <Button
          v-for="(a, i) in copilot.now.value?.actions || []"
          :key="i"
          size="sm"
          :variant="a.style === 'positive' ? 'solid' : 'subtle'"
          :theme="a.style === 'destructive' ? 'red' : 'gray'"
          :loading="copilot.busy.value"
          @click="act(a)"
        >
          {{ a.label }}
        </Button>
        <Button
          v-if="customerWaits && !copilot.needsYou.value"
          size="sm"
          :variant="copilot.now.value?.actions?.length ? 'subtle' : 'solid'"
          :label="__('Reply to {0}', contactFirst)"
          @click="startWriting('reply')"
        >
          <template #prefix>
            <LucideReply class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Dropdown v-if="menu.length" :options="menu" placement="right">
          <Button variant="ghost" size="sm" :label="__('More Copilot actions')">
            <template #icon>
              <LucideEllipsis class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
      </div>
    </div>

    <Dialog
      v-model="asking.open"
      :options="{ title: asking.action?.label || '', size: 'sm' }"
    >
      <template #body-content>
        <FormControl
          v-model="asking.value"
          type="textarea"
          :label="asking.label"
          :placeholder="asking.placeholder"
        />
      </template>
      <template #actions>
        <Button
          variant="solid"
          class="w-full"
          :loading="copilot.busy.value"
          :disabled="!asking.value.trim()"
          @click="submitAsked"
        >
          {{ asking.action?.label }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import type { CopilotAction } from "@/components/copilot/CopilotCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { SlaTimeLeftSymbol } from "@/composables/useSlaTimeLeft";
import { dueBadge } from "@/pages/ticket/ticketMeta";
import { startWriting } from "@/pages/ticket/modalStates";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { __ } from "@/translation";
import { ActivitiesSymbol, TicketSymbol } from "@/types";
import {
  Button,
  Dialog,
  dayjsLocal,
  Dropdown,
  FormControl,
  Tooltip,
} from "frappe-ui";
import { computed, inject, reactive, type Component } from "vue";
import LucideBot from "~icons/lucide/bot";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideMessageSquare from "~icons/lucide/message-square";
import LucideReply from "~icons/lucide/reply";
import LucideShieldAlert from "~icons/lucide/shield-alert";
import LucideSparkles from "~icons/lucide/sparkles";
import { firstName } from "./inbox";
import { COPILOT_WORKING, useCopilotThread } from "./useCopilotThread";

const ticket = inject(TicketSymbol)!;
const activities = inject(ActivitiesSymbol)!;
const sla = inject(SlaTimeLeftSymbol, null);
const { getStatus } = useTicketStatusStore();

const doc = computed(() => ticket.value.doc);
// the ticket page re-mounts this per ticket (TicketAgent keys it), so one thread is enough
const copilot = useCopilotThread(String(doc.value.name));
const contactFirst = computed(() =>
  firstName(doc.value.contact || doc.value.raised_by)
);

const category = computed(
  () => getStatus(doc.value.status)?.category ?? doc.value.status_category
);

const due = computed(() =>
  dueBadge(
    doc.value,
    category.value === "Paused",
    (clock) => sla?.workingLeft(String(doc.value.name), clock),
    sla?.now.value ?? dayjsLocal()
  )
);

// the newest email says who wrote last: the customer (they wait for us) or the team
const customerWaits = computed(() => {
  if (category.value !== "Open") return false;
  const emails = activities.value?.data?.communications ?? [];
  const last = emails[emails.length - 1];
  return !last || last.sent_or_received === "Received";
});

// a Rating field holds 0–1; five stars
const stars = computed(() => {
  const r = Number(doc.value.feedback_rating) || 0;
  return Math.round(r <= 1 ? r * 5 : r);
});

type Move = {
  text: string;
  tone: "you" | "late" | "them" | "done";
  icon: Component;
  iconClass: string;
};

const move = computed<Move>(() => {
  const who = contactFirst.value;
  const status = doc.value.status;
  if (category.value === "Resolved") {
    const text =
      status === "Closed"
        ? __("Closed.")
        : doc.value.feedback_rating
        ? __("Resolved. {0} rated it {1}/5.", who, String(stars.value))
        : __("Resolved. Waiting for {0} to confirm it's fixed.", who);
    return {
      text,
      tone: "done",
      icon: LucideCircleCheck,
      iconClass: "text-success",
    };
  }
  if (category.value === "Paused") {
    const text =
      status === "Replied"
        ? __("Waiting for {0} to answer. The SLA clock is paused.", who)
        : status === "Waiting on Task"
        ? __("Waiting on a task. The SLA clock is paused.")
        : __("{0}. The SLA clock is paused.", __(status));
    return {
      text,
      tone: "them",
      icon: LucideHourglass,
      iconClass: "text-warning",
    };
  }
  if (customerWaits.value) {
    const late = due.value?.tone === "danger";
    return {
      text: late
        ? __("{0} is waiting for a reply, and it's overdue.", who)
        : __("{0} is waiting for a reply.", who),
      tone: late ? "late" : "you",
      icon: late ? LucideCircleAlert : LucideMessageSquare,
      iconClass: late ? "text-danger" : "text-info",
    };
  }
  return {
    text: __("{0} has our last reply. The ticket is still open.", who),
    tone: "you",
    icon: LucideMessageSquare,
    iconClass: "text-ink-gray-5",
  };
});

// the SLA beside whose move it is, while its clock runs (paused and done say it in words)
const showDue = computed(() => category.value === "Open");

const copilotIcon = computed(() => {
  const state = copilot.now.value?.state || "";
  if (copilot.needsYou.value)
    return { icon: LucideShieldAlert, class: "text-warning" };
  if (!state) return { icon: LucideBot, class: "text-ink-gray-5" };
  if (COPILOT_WORKING.has(state))
    return {
      icon: LucideLoaderCircle,
      class: "text-ink-gray-6 motion-safe:animate-spin",
    };
  return { icon: LucideSparkles, class: "text-ink-gray-6" };
});

// an action that needs a few words first (a reason, the right root cause) asks for them
const NEEDS: Record<string, { label: string; placeholder?: string }> = {
  reason: { label: __("Why?") },
  root_cause: {
    label: __("The right root cause"),
    placeholder: "bug, wrong_setting, customer_mistake, question, …",
  },
};
const asking = reactive({
  open: false,
  action: null as CopilotAction | null,
  value: "",
  label: "",
  placeholder: "",
});

function act(a: CopilotAction) {
  const needs = a.data?.needs as string | undefined;
  if (!needs) return copilot.press(a, {});
  asking.action = a;
  asking.value = "";
  asking.label = NEEDS[needs]?.label || needs;
  asking.placeholder =
    needs === "root_cause"
      ? (copilot.now.value?.categories || []).join(", ") ||
        NEEDS.root_cause.placeholder ||
        ""
      : "";
  asking.open = true;
}

async function submitAsked() {
  const a = asking.action;
  if (!a) return;
  await copilot.press(a, { [a.data.needs as string]: asking.value });
  asking.open = false;
}

const menu = computed(() => [
  ...(copilot.now.value?.more || []).map((a) => ({
    label: a.label,
    onClick: () => act(a),
  })),
  ...(copilot.now.value?.links || []).map(([label, url]) => ({
    label,
    onClick: () => window.open(url, "_blank", "noopener"),
  })),
]);
</script>

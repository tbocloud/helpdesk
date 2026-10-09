<template>
  <header class="flex flex-col gap-4 px-4 pt-5 md:px-10 md:pt-6">
    <div class="flex min-w-0 flex-col gap-2">
      <h1 class="text-xl font-semibold text-ink-gray-9 break-words">
        {{ ticket.data.subject }}
      </h1>
      <p
        class="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-gray-6"
      >
        <TaskyBadge v-bind="status" />
        <span class="font-mono tabular-nums text-ink-gray-5">
          #{{ ticket.data.name }}
        </span>
        <span aria-hidden="true">·</span>
        <Tooltip :text="dateFormat(ticket.data.creation, dateTooltipFormat)">
          <span>{{ __("Opened {0}", [timeAgo(ticket.data.creation)]) }}</span>
        </Tooltip>
      </p>
    </div>

    <!-- what happens next: one sentence, and the one thing the customer can do -->
    <section
      class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4 sm:flex-row sm:items-start"
      :aria-labelledby="headingId"
    >
      <component
        :is="next.icon"
        class="size-5 shrink-0"
        :class="INK[next.tone]"
        aria-hidden="true"
      />
      <div class="flex min-w-0 flex-1 flex-col gap-1">
        <h2 :id="headingId" class="text-base-medium text-ink-gray-9">
          {{ next.title }}
        </h2>
        <p class="text-p-sm text-ink-gray-6">{{ next.message }}</p>
      </div>
      <Button
        v-if="isClosed"
        :label="__('New ticket')"
        class="shrink-0 self-start"
        @click="$router.push({ name: 'TicketNew' })"
      />
      <Button
        v-else-if="stage === 'awaiting'"
        :label="__('Reply')"
        class="shrink-0 self-start"
        @click="emit('reply')"
      >
        <template #prefix>
          <LucideReply class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </section>
  </header>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { INK, type Tone } from "@/components/tone";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat, timeAgo } from "@/utils";
import { Button, dayjsLocal, Tooltip } from "frappe-ui";
import { computed, inject, useId, type Component } from "vue";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideLock from "~icons/lucide/lock";
import LucideMessageSquareReply from "~icons/lucide/message-square-reply";
import LucideReply from "~icons/lucide/reply";
import { useCustomerStatus } from "./customerStatus";
import { deadlineLabel } from "./ticketMeta";
import { ITicket } from "./symbols";

const props = defineProps<{ isClosed: boolean }>();
const emit = defineEmits<{ reply: [] }>();

const ticket = inject(ITicket);
const customerStatus = useCustomerStatus();
const headingId = `ticket-next-${useId()}`;

const status = computed(() => customerStatus.badge(ticket.data.status));
const stage = computed(() => customerStatus.stage(ticket.data.status));

function at(date: string) {
  return dayjsLocal(date).format("ddd D MMM, h:mm A");
}

const next = computed<{
  title: string;
  message: string;
  tone: Tone;
  icon: Component;
}>(() => {
  const t = ticket.data;
  if (props.isClosed) {
    return {
      title: __("This ticket is closed"),
      message: __(
        "Closed tickets can't take new replies. If you still need help, raise a new ticket."
      ),
      tone: "neutral",
      icon: LucideLock,
    };
  }
  if (stage.value === "resolved") {
    return {
      title: __("We've marked this resolved"),
      message: __(
        "If something still isn't right, reply below and we'll pick it up again."
      ),
      tone: "success",
      icon: LucideCircleCheck,
    };
  }
  if (stage.value === "awaiting") {
    return {
      title: __("We're waiting for your reply"),
      message: __(
        "We've answered and need a little more from you before we can carry on."
      ),
      tone: "warning",
      icon: LucideMessageSquareReply,
    };
  }
  if (stage.value === "paused") {
    return {
      title: __("On hold for now"),
      message: __(
        "We're waiting on related work before the next step. We'll update you here."
      ),
      tone: "neutral",
      icon: LucideHourglass,
    };
  }
  // open: say when the reply or fix is due, but never that a deadline was missed
  const ahead = (deadline?: string) =>
    !!deadline && dayjsLocal().isBefore(dayjsLocal(deadline));
  if (!t.first_responded_on && ahead(t.response_by)) {
    // the time, not "within 3h": the deadline counts working hours only
    return {
      title: __("We'll reply by {0}", [deadlineLabel(t.response_by)]),
      message: __(
        "Our team has your ticket. You'll get the reply by email and here."
      ),
      tone: "info",
      icon: LucideClock,
    };
  }
  if (!t.first_responded_on) {
    return {
      title: __("Our team has your ticket"),
      message: __(
        "We'll reply as soon as we can. You'll get it by email and here."
      ),
      tone: "info",
      icon: LucideClock,
    };
  }
  if (ahead(t.resolution_by)) {
    return {
      title: __("We're working on it"),
      message: __(
        "We aim to resolve this by {0}. We'll keep you posted here.",
        [at(t.resolution_by)]
      ),
      tone: "info",
      icon: LucideClock,
    };
  }
  return {
    title: __("We're working on it"),
    message: __("We'll keep you posted here."),
    tone: "info",
    icon: LucideClock,
  };
});
</script>

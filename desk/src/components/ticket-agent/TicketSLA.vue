<template>
  <!-- Teleport to App Header -->
  <teleport to="#app-header">
    <div class="mx-4 pb-3.5 md:mx-5">
      <h1
        class="mt-1 cursor-text truncate text-[22px] font-semibold leading-[30px] tracking-[-0.01em] text-ink-gray-9"
        :title="__('Click to rename')"
        @click="emit('edit-subject')"
      >
        {{ ticket.doc.subject }}
      </h1>
      <div class="mt-2.5 flex flex-wrap items-center gap-2">
        <span class="inline-flex items-center gap-1.5 text-xs text-ink-gray-5">
          <GlobeIcon
            v-if="ticket.doc.via_customer_portal"
            class="size-4"
            aria-hidden="true"
          />
          <EmailIcon v-else class="size-4" aria-hidden="true" />
          {{
            ticket.doc.via_customer_portal ? __("via Portal") : __("via Email")
          }}
        </span>
        <span class="mx-1 h-4 w-px bg-surface-gray-4" aria-hidden="true" />

        <span
          class="inline-flex h-[22px] items-center gap-1.5 rounded-md px-2 text-xs font-medium"
          :class="statusTone"
        >
          <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
          {{ ticket.doc.status }}
        </span>

        <span
          v-if="ticket.doc.priority"
          class="inline-flex h-[22px] items-center gap-1.5 rounded-md bg-surface-gray-2 px-2 text-xs font-medium text-ink-gray-6"
        >
          <span
            class="size-2 rounded-sm"
            :class="priorityTone"
            aria-hidden="true"
          />
          {{ __("{0} priority", ticket.doc.priority) }}
        </span>

        <Tooltip
          v-for="sla in slaChips"
          :key="sla.key"
          :text="sla.date ? dateFormat(sla.date, dateTooltipFormat) : sla.state"
          :hover-delay="0.3"
          placement="top"
        >
          <span
            class="inline-flex h-[26px] items-center gap-2 rounded-md pl-2 pr-2.5 text-xs font-medium"
            :class="sla.chip"
          >
            <component
              :is="sla.icon"
              class="size-4"
              :class="sla.accent"
              aria-hidden="true"
            />
            <span class="text-ink-gray-5">{{ sla.label }}</span>
            <span
              v-if="sla.value"
              class="font-mono tabular-nums"
              :class="sla.accent || 'text-ink-gray-9'"
            >
              <span class="sr-only">{{ sla.state }}</span
              >{{ sla.value }}
            </span>
            <span v-else :class="sla.accent || 'text-ink-gray-9'">{{
              sla.state
            }}</span>
          </span>
        </Tooltip>

        <button
          type="button"
          class="font-mono text-xs text-ink-gray-5 hover:text-ink-gray-8"
          :title="__('Copy ticket ID')"
          @click="
            copyToClipboard(
              ticket.doc.name,
              `Ticket #${ticket.doc.name} copied to clipboard`
            )
          "
        >
          #{{ ticket.doc.name }}
        </button>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { useShortcut } from "@/composables/shortcuts";
import { TicketSymbol } from "@/types";
import {
  copyToClipboard,
  dateFormat,
  dateTooltipFormat,
  formatTime,
} from "@/utils";
import { EmailIcon, GlobeIcon } from "@/components/icons";
import { __ } from "@/translation";
import { dayjs, Tooltip } from "frappe-ui";
import { computed, inject } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucidePause from "~icons/lucide/pause";

const emit = defineEmits<{ (e: "edit-subject"): void }>();

const ticket = inject(TicketSymbol)!;

const statusTone = computed(
  () =>
    ({
      Open: "bg-info-soft text-info",
      Paused: "bg-warning-soft text-warning",
      Resolved: "bg-success-soft text-success",
    }[ticket.value.doc.status_category as string] ??
    "bg-surface-gray-2 text-ink-gray-6")
);

const priorityTone = computed(
  () =>
    ({ Urgent: "bg-danger", High: "bg-danger", Medium: "bg-warning" }[
      ticket.value.doc.priority as string
    ] ?? "bg-surface-gray-5")
);

// SLA labels read "Due in 8h 34m"; show the state in words and the duration in mono
const SLA_TONES: Record<string, { chip: string; accent: string; icon: any }> = {
  orange: {
    chip: "bg-surface-gray-2",
    accent: "text-success",
    icon: LucideClock,
  },
  purple: { chip: "bg-surface-gray-2", accent: "", icon: LucideClock },
  green: {
    chip: "bg-surface-gray-2",
    accent: "text-success",
    icon: LucideCircleCheck,
  },
  blue: { chip: "bg-warning-soft", accent: "text-warning", icon: LucidePause },
  red: {
    chip: "bg-danger-soft",
    accent: "text-danger",
    icon: LucideAlarmClock,
  },
  gray: { chip: "bg-surface-gray-2", accent: "", icon: LucideClock },
};

function slaChip(
  key: string,
  label: string,
  sla: { label: string; color: string; date?: string }
) {
  const match = sla.label.match(/^(.*?)\s*(\d.*)$/);
  return {
    key,
    label,
    state: match ? match[1] : sla.label,
    value: match ? match[2] : "",
    date: sla.date,
    ...(SLA_TONES[sla.color] ?? SLA_TONES.gray),
  };
}

const slaChips = computed(() =>
  [
    ticket.value.doc.response_by &&
      slaChip("response", __("First response"), firstResponse.value),
    ticket.value.doc.resolution_by &&
      slaChip("resolution", __("Resolution"), resolutionBy.value),
  ].filter(Boolean)
);

const timeFormat = {
  day: true,
  hour: true,
  minute: true,
};

// Cases:
// - if not first responded and response by is in future -> show due in
// - if first responded before response by -> show fulfilled in
// - if not first responded and response by is in past -> show overdue by
// - if first responded after response by -> show failed by
const firstResponse = computed(() => {
  if (ticket.value?.get?.loading) return { label: "", color: "gray" };
  if (
    !ticket.value.doc.first_responded_on &&
    dayjs().isBefore(dayjs(ticket.value.doc.response_by))
  ) {
    let responseBy = formatTimeShort(ticket.value.doc.response_by as string);
    return {
      label: `Due in ${responseBy}`,
      color: "orange",
    };
  } else if (
    dayjs(ticket.value.doc.first_responded_on).isBefore(
      dayjs(ticket.value.doc.response_by)
    )
  ) {
    let responseTime = ticket.value?.doc?.first_response_time;
    let format =
      responseTime <= 60
        ? {
            ...timeFormat,
            second: true,
          }
        : timeFormat;
    let fulfilled =
      responseTime != null
        ? formatTime(responseTime, format)
        : formatTimeShort(
            ticket.value.doc.first_responded_on as string,
            ticket.value.doc.creation
          );
    return {
      label: `Fulfilled in ${fulfilled}`,
      color: "green",
    };
  } else {
    if (!ticket.value.doc.first_responded_on) {
      let responseBy = formatTimeShort(
        String(new Date()),
        ticket.value.doc.response_by as string
      );
      return {
        label: `Overdue by ${responseBy}`,
        color: "red",
        date: ticket.value.doc.response_by,
      };
    }

    let failed = ticket.value?.doc?.first_response_failed_by
      ? formatTime(ticket.value.doc.first_response_failed_by, timeFormat)
      : formatTimeShort(
          ticket.value.doc.first_responded_on,
          ticket.value.doc.response_by
        );
    return {
      label: `Failed by ${failed}`,
      color: "red",
    };
  }
});

const resolutionBy = computed(() => {
  if (ticket.value?.get?.loading) return { label: "", color: "gray" };

  if (
    ticket.value.doc?.status_category === "Paused" &&
    ticket.value.doc?.on_hold_since &&
    dayjs(ticket.value.doc?.resolution_by).isAfter(
      dayjs(ticket.value.doc?.on_hold_since)
    )
  ) {
    return {
      label: `On Hold`,
      color: "blue",
    };
  } else if (
    !ticket.value.doc?.resolution_date &&
    dayjs().isAfter(dayjs(ticket.value.doc?.resolution_by))
  ) {
    let overdue = formatTimeShort(
      String(new Date()),
      ticket.value.doc?.resolution_by as string
    );

    return {
      label: `Overdue by ${overdue}`,
      color: "red",
      date: ticket.value.doc?.resolution_by,
    };
  } else if (
    !ticket.value.doc?.resolution_date &&
    dayjs().isBefore(dayjs(ticket.value.doc?.resolution_by))
  ) {
    let resolutionBy = formatTimeShort(
      ticket.value.doc?.resolution_by as string
    );
    return {
      label: `Due in ${resolutionBy}`,
      color: "purple",
    };
  } else if (
    dayjs(ticket.value.doc?.resolution_date).isBefore(
      dayjs(ticket.value.doc?.resolution_by)
    )
  ) {
    let resolutionTime = ticket.value?.doc?.resolution_time;
    let format =
      resolutionTime <= 60
        ? {
            ...timeFormat,
            second: true,
          }
        : timeFormat;
    let fulfilled =
      resolutionTime != null
        ? formatTime(resolutionTime, format)
        : formatTimeShort(
            ticket.value.doc?.resolution_date as string,
            ticket.value.doc?.creation
          );
    return {
      label: `Fulfilled in ${fulfilled}`,
      color: "green",
    };
  } else {
    let failed = ticket.value.doc?.resolution_failed_by
      ? formatTime(ticket.value.doc?.resolution_failed_by, timeFormat)
      : formatTimeShort(
          ticket.value.doc?.resolution_by,
          ticket.value.doc?.resolution_date
        );
    return {
      label: `Failed by ${failed}`,
      color: "red",
    };
  }
});

function formatTimeShort(date: string, end?: string): string {
  if (!end) {
    end = dayjs().toString();
  }
  let _date = dayjs(date);
  let duration = dayjs.duration(_date.diff(dayjs(end)));

  let years = duration.years();
  let months = duration.months();
  let days = duration.days();
  let hours = duration.hours();
  let minutes = duration.minutes();

  if (years > 0) {
    return `${years}y ${months}mo`;
  } else if (months > 0) {
    return `${months}mo ${days}d`;
  } else if (days > 0) {
    return `${days}d ${hours}h`;
  } else if (hours > 0) {
    return `${hours}h ${minutes}m`;
  } else {
    return `${minutes}m`;
  }
}

useShortcut({ meta: true, shift: true, key: "." }, () => {
  copyToClipboard(window.location.href, `Ticket URL copied to clipboard`);
});

useShortcut({ meta: true, key: "." }, () => {
  copyToClipboard(
    ticket.value.doc.name,
    `Ticket #${ticket.value.doc.name} copied to clipboard`
  );
});
</script>

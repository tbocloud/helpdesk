<template>
  <PanelSection v-if="rows.length" :title="__('SLA')" :icon="LucideTimer">
    <dl class="flex flex-col gap-2.5">
      <div v-if="doc.sla" class="flex items-baseline justify-between gap-3">
        <dt class="text-xs font-medium text-ink-gray-6">{{ __("Policy") }}</dt>
        <dd class="min-w-0 truncate text-sm text-ink-gray-8" :title="doc.sla">
          {{ doc.sla }}
        </dd>
      </div>
      <div
        v-for="row in rows"
        :key="row.key"
        class="flex items-start justify-between gap-3"
      >
        <dt class="pt-0.5 text-xs font-medium text-ink-gray-6">
          {{ row.label }}
        </dt>
        <dd class="flex min-w-0 flex-col items-end gap-1 text-end">
          <TaskyBadge v-if="row.badge" v-bind="row.badge" />
          <span class="font-mono text-xs tabular-nums text-ink-gray-6">
            {{ row.detail }}
          </span>
        </dd>
      </div>
      <div v-if="pausedSince" class="flex items-baseline justify-between gap-3">
        <dt class="text-xs font-medium text-ink-gray-6">
          {{ __("Paused since") }}
        </dt>
        <dd class="font-mono text-xs tabular-nums text-ink-gray-8">
          {{ pausedSince }}
        </dd>
      </div>
    </dl>
  </PanelSection>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import {
  resolutionSla,
  responseSla,
  slaBadge,
} from "@/pages/ticket/ticketMeta";
import { __ } from "@/translation";
import { TicketSymbol } from "@/types";
import { dateFormat, dateTooltipFormat } from "@/utils";
import { computed, inject } from "vue";
import LucideTimer from "~icons/lucide/timer";
import PanelSection from "./PanelSection.vue";

// the header shows the countdowns; this says when exactly, and against which policy
const ticket = inject(TicketSymbol)!;
const doc = computed(() => ticket.value.doc ?? {});

const at = (date: string) => dateFormat(date, dateTooltipFormat);

const rows = computed(() => {
  const d = doc.value;
  const paused = d.status_category === "Paused";
  const result = [];
  if (d.response_by) {
    result.push({
      key: "response",
      label: __("First response"),
      badge: slaBadge(responseSla(d, d.response_by), d.response_by),
      detail: d.first_responded_on
        ? __("Responded {0}", at(d.first_responded_on))
        : __("Due {0}", at(d.response_by)),
    });
  }
  if (d.resolution_by) {
    result.push({
      key: "resolution",
      label: __("Resolution"),
      badge: slaBadge(
        resolutionSla(d, d.resolution_by, paused),
        d.resolution_by
      ),
      detail: d.resolution_date
        ? __("Resolved {0}", at(d.resolution_date))
        : __("Due {0}", at(d.resolution_by)),
    });
  }
  return result;
});

const pausedSince = computed(() =>
  doc.value.status_category === "Paused" && doc.value.on_hold_since
    ? at(doc.value.on_hold_since)
    : ""
);
</script>

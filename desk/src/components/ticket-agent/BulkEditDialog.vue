<template>
  <!-- the tickets list's selection bar (Phase 15): assign, set the status or the priority of the
       selected tickets in one go; each ticket is changed as the agent, so its own checks apply -->
  <Dialog
    v-model="open"
    :options="{ title: TITLES[mode], size: 'sm' }"
    @after-leave="reset"
  >
    <template #body-content>
      <p class="mb-3 text-p-sm text-ink-gray-6">
        {{
          tickets.length === 1
            ? __("For ticket #{0}.", [tickets[0]])
            : __("For {0} selected tickets.", [tickets.length])
        }}
      </p>
      <FormControl
        v-model="value"
        type="select"
        :label="LABELS[mode]"
        :options="choices"
      />
      <p v-if="mode === 'assign'" class="mt-2 text-p-xs text-ink-gray-5">
        {{
          __(
            "People on leave all day today are not offered. Each ticket keeps anyone already on it."
          )
        }}
      </p>
      <p v-if="failures.length" class="mt-3 text-p-sm text-danger" role="alert">
        {{
          __(
            "Not changed: {0}. {1}",
            failures.map((f) => "#" + f.ticket).join(", "),
            failures[0].reason
          )
        }}
      </p>
    </template>
    <template #actions>
      <Button
        variant="solid"
        class="w-full"
        :label="__('Apply')"
        :loading="busy"
        :disabled="!value"
        @click="apply"
      />
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { useOnLeave } from "@/composables/onLeave";
import { useAgentStore } from "@/stores/agent";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createListResource,
  Dialog,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref } from "vue";

export type BulkMode = "assign" | "status" | "priority";

const props = defineProps<{ mode: BulkMode; tickets: string[] }>();
const emit = defineEmits<{ done: [] }>();
const open = defineModel<boolean>({ default: false });

const TITLES: Record<BulkMode, string> = {
  assign: __("Assign"),
  status: __("Set status"),
  priority: __("Set priority"),
};
const LABELS: Record<BulkMode, string> = {
  assign: __("Assign to"),
  status: __("Status"),
  priority: __("Priority"),
};

const agentStore = useAgentStore();
if (!agentStore.agents.data && !agentStore.agents.loading)
  agentStore.agents.fetch();
const statusStore = useTicketStatusStore();
const { awayAllDay, leaveLabel } = useOnLeave();
const priorities = createListResource({
  doctype: "HD Ticket Priority",
  fields: ["name"],
  orderBy: "integer_value desc",
  pageLength: 50,
  auto: true,
});

const choices = computed(() => {
  const blank = { label: "", value: "" };
  if (props.mode === "assign")
    return [
      blank,
      ...(agentStore.agents.data ?? []).map((a: any) => ({
        label: leaveLabel(a.name)
          ? `${a.agent_name} · ${leaveLabel(a.name)}`
          : a.agent_name,
        value: a.name,
        disabled: awayAllDay(a.name),
      })),
    ];
  if (props.mode === "status")
    return [
      blank,
      ...(statusStore.statuses.data ?? [])
        .filter((s: any) => s.enabled)
        .map((s: any) => ({ label: s.label_agent, value: s.label_agent })),
    ];
  return [
    blank,
    ...(priorities.data ?? []).map((p: any) => ({
      label: __(p.name),
      value: p.name,
    })),
  ];
});

const value = ref("");
const busy = ref(false);
const failures = ref<{ ticket: string; reason: string }[]>([]);

function reset() {
  value.value = "";
  failures.value = [];
}

function change(ticket: string) {
  if (props.mode === "assign")
    return call("frappe.desk.form.assign_to.add", {
      doctype: "HD Ticket",
      name: ticket,
      assign_to: [value.value],
    });
  return call("frappe.client.set_value", {
    doctype: "HD Ticket",
    name: ticket,
    fieldname: props.mode,
    value: value.value,
  });
}

async function apply() {
  busy.value = true;
  failures.value = [];
  for (const ticket of props.tickets) {
    try {
      await change(ticket);
    } catch (e) {
      failures.value.push({ ticket, reason: errorText(e, __("Try again.")) });
    }
  }
  busy.value = false;
  const changed = props.tickets.length - failures.value.length;
  if (changed)
    toast.success(
      changed === 1
        ? __("1 ticket changed")
        : __("{0} tickets changed", [changed])
    );
  emit("done");
  if (!failures.value.length) open.value = false;
}
</script>

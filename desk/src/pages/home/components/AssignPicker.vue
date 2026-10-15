<template>
  <!-- "Assign" next to "Take it": hand an unassigned ticket to someone else;
       the stand-up's "Assign help" uses it with its own label -->
  <Combobox
    v-model:open="open"
    :model-value="null"
    :options="options"
    :loading="people.loading && !people.data"
    :placeholder="__('Search agents')"
    :empty-text="__('No active agent matches')"
    align="end"
    @update:model-value="pick"
  >
    <template #trigger>
      <!-- frappe-ui's Button swaps aria-label for `label`: the name is sr-only text -->
      <Button size="sm" :class="{ '!h-11': touch }" :loading="loading">
        <template #prefix>
          <LucideUsers class="size-4" aria-hidden="true" />
        </template>
        <!-- phones keep Home's row on one line: the icon alone -->
        <span :class="{ 'max-sm:hidden': !label }" aria-hidden="true">{{
          label || __("Assign")
        }}</span>
        <span class="sr-only">{{
          label
            ? __("{0}: {1}", label, title)
            : __("Assign to someone else: {0}", title)
        }}</span>
      </Button>
    </template>
    <template v-if="people.error" #footer>
      <p
        class="flex items-center gap-2 border-t border-outline-gray-1 px-3 py-2 text-p-sm text-ink-gray-7"
        role="alert"
      >
        {{ __("Couldn't load the agents.") }}
        <Button variant="ghost" :label="__('Retry')" @click="people.fetch()" />
      </p>
    </template>
  </Combobox>
</template>

<script setup lang="ts">
import {
  useAssignablePeople,
  type AssignablePerson,
} from "@/composables/assignablePeople";
import { useOnLeave } from "@/composables/onLeave";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, Combobox, createResource } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideUsers from "~icons/lucide/users";

const props = defineProps<{
  /** the ticket's subject, for the button's accessible name */
  title: string;
  /** the button's text instead of "Assign" */
  label?: string;
  customer?: string | null;
  loading?: boolean;
  /** a 44px button, where it is the row's main action on a phone */
  touch?: boolean;
}>();
const emit = defineEmits<{ pick: [user: string, name: string] }>();

const open = ref(false);
const authStore = useAuthStore();
// active agents with enabled accounts: who can be given a ticket
const { people, nameOf } = useAssignablePeople();
const { leaveLabel } = useOnLeave();

// the customer's ticket owner and backup (docs/ticket-owners.md), asked for on first open
const owners = createResource({
  url: "frappe.client.get_value",
  // without them the picker still lists every agent
  onError() {},
});
watch(open, (isOpen) => {
  if (!isOpen || !props.customer || owners.data || owners.loading) return;
  owners.submit({
    doctype: "HD Customer",
    filters: props.customer,
    fieldname: ["ticket_owner", "backup_ticket_owner"],
  });
});

function option(person: AssignablePerson, role = "") {
  return {
    label: person.full_name || person.name,
    value: person.name,
    description:
      [role, leaveLabel(person.name)].filter(Boolean).join(" · ") || undefined,
  };
}

const options = computed(() => {
  // "Take it" is the way to assign yourself
  const all = ((people.data ?? []) as AssignablePerson[]).filter(
    (p) => p.name !== authStore.userId
  );
  const find = (user?: string | null) => all.find((p) => p.name === user);
  const owner = find(owners.data?.ticket_owner);
  const backup = find(owners.data?.backup_ticket_owner);
  const suggested = [
    owner && option(owner, __("Ticket owner")),
    backup && option(backup, __("Backup")),
  ].filter(Boolean) as ReturnType<typeof option>[];
  const rest = all
    .filter((p) => p !== owner && p !== backup)
    .map((p) => option(p));
  return [
    ...(suggested.length
      ? [{ group: __("Suggested"), options: suggested }]
      : []),
    { group: __("Agents"), hideLabel: !suggested.length, options: rest },
  ];
});

function pick(user: string | null) {
  if (user) emit("pick", user, nameOf(user));
}
</script>

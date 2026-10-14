<template>
  <!-- one customer's ticket owner (its page) or several at once (the Customers list) -->
  <Dialog v-model:open="open" :title="title" size="md">
    <template #default>
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "New tickets from the customer are assigned to the owner. The backup takes them while the owner is on leave or inactive. Anyone can still reassign a ticket."
            )
          }}
        </p>
        <Combobox
          v-model="owner"
          :label="__('Ticket owner')"
          :options="ownerOptions"
          :loading="people.loading"
          :placeholder="__('Pick an agent')"
          :empty-text="__('No active agent matches')"
        />
        <Combobox
          v-model="backup"
          :label="__('Backup')"
          :options="backupOptions"
          :loading="people.loading"
          :disabled="!hasOwner"
          :placeholder="__('Pick an agent')"
          :empty-text="__('No active agent matches')"
        />
        <p
          v-if="people.error"
          class="flex items-center gap-2 text-p-sm text-ink-gray-7"
          role="alert"
        >
          {{ __("Couldn't load the agents.") }}
          <Button
            variant="ghost"
            :label="__('Retry')"
            @click="people.fetch()"
          />
        </p>
        <p v-if="error" class="text-p-sm text-danger" role="alert">
          {{ error }}
        </p>
        <!-- Enter submits the form -->
        <button type="submit" class="hidden" tabindex="-1" />
      </form>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="open = false" />
        <Button
          variant="solid"
          :label="saveLabel"
          :loading="save.loading"
          :disabled="!canSave"
          @click="submit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import {
  useAssignablePeople,
  type AssignablePerson,
} from "@/composables/assignablePeople";
import { useOnLeave } from "@/composables/onLeave";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Combobox, createResource, Dialog, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";

// Combobox values can't be empty: these stand for "no owner" and "keep as it is"
const NONE = "__none__";
const KEEP = "__keep__";

const props = defineProps<{
  /** the customers to set; more than one makes it the bulk dialog */
  customers: string[];
  owner?: string | null;
  backup?: string | null;
}>();

const emit = defineEmits<{ saved: [] }>();
const open = defineModel<boolean>({ default: false });

const owner = ref("");
const backup = ref("");
const error = ref("");

const bulk = computed(() => props.customers.length > 1);
const { leaveLabel } = useOnLeave();
// active agents with enabled accounts: the people the server accepts as owners
const { people } = useAssignablePeople();

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    error.value = "";
    owner.value = props.owner || (bulk.value ? "" : NONE);
    backup.value = bulk.value ? KEEP : props.backup || NONE;
  },
  { immediate: true }
);

const hasOwner = computed(() => !!owner.value && owner.value !== NONE);

// a backup can't be the owner: picking that owner drops the backup
watch(owner, (value) => {
  if (!hasOwner.value) backup.value = bulk.value ? KEEP : NONE;
  else if (backup.value === value) backup.value = bulk.value ? KEEP : NONE;
});

function personOptions(skip: string) {
  return ((people.data ?? []) as AssignablePerson[])
    .filter((p) => p.name !== skip)
    .map((p) => ({
      label: p.full_name || p.name,
      value: p.name,
      description: leaveLabel(p.name) || p.name,
    }));
}

const ownerOptions = computed(() => [
  ...(bulk.value ? [] : [{ label: __("No owner"), value: NONE }]),
  ...personOptions(""),
]);

const backupOptions = computed(() => [
  ...(bulk.value
    ? [{ label: __("Keep each customer's backup"), value: KEEP }]
    : []),
  { label: __("No backup"), value: NONE },
  ...personOptions(owner.value),
]);

const title = computed(() =>
  bulk.value
    ? __(
        "Set the ticket owner of {0} customers",
        String(props.customers.length)
      )
    : __("Ticket owner")
);

const saveLabel = computed(() =>
  bulk.value
    ? __("Set owner for {0} customers", String(props.customers.length))
    : __("Save ticket owner")
);

const canSave = computed(() =>
  bulk.value
    ? hasOwner.value
    : (owner.value === NONE ? "" : owner.value) !== (props.owner || "") ||
      (backup.value === NONE ? "" : backup.value) !== (props.backup || "")
);

const save = createResource({
  url: "helpdesk.api.ticket_owner.set_ticket_owner",
});

async function submit() {
  if (!canSave.value || save.loading) return;
  error.value = "";
  try {
    await save.submit({
      customers: props.customers,
      ticket_owner: hasOwner.value ? owner.value : "",
      // left out, the server keeps each customer's backup
      ...(backup.value === KEEP
        ? {}
        : { backup_ticket_owner: backup.value === NONE ? "" : backup.value }),
    });
    toast.success(
      bulk.value
        ? __(
            "Ticket owner set for {0} customers",
            String(props.customers.length)
          )
        : __("Ticket owner saved")
    );
    emit("saved");
    open.value = false;
  } catch (err) {
    error.value = errorText(
      err,
      __("The ticket owner wasn't saved. Try again.")
    );
  }
}
</script>

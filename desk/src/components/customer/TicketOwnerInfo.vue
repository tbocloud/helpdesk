<template>
  <!-- the customer page header's ticket owner: who gets new tickets, and who covers -->
  <span class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
    <span class="flex min-w-0 flex-wrap items-center gap-x-1.5">
      <LucideUserCheck
        class="size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      <template v-if="owner">
        <span class="shrink-0 text-ink-gray-5">{{ __("Ticket owner") }}</span>
        <span class="truncate text-ink-gray-8">{{ nameOf(owner) }}</span>
        <span v-if="away(owner)" class="text-ink-gray-5">
          ({{ away(owner) }})
        </span>
      </template>
      <span v-else class="text-ink-gray-5">{{ __("No ticket owner") }}</span>
    </span>
    <span
      v-if="owner && backup"
      class="flex min-w-0 flex-wrap items-center gap-x-1.5"
    >
      <span class="shrink-0 text-ink-gray-5">{{ __("Backup") }}</span>
      <span class="truncate text-ink-gray-8">{{ nameOf(backup) }}</span>
      <span v-if="away(backup)" class="text-ink-gray-5">
        ({{ away(backup) }})
      </span>
    </span>
    <Button
      v-if="editable"
      variant="ghost"
      size="sm"
      :label="owner ? __('Change') : __('Set owner')"
      :aria-label="owner ? __('Change ticket owner') : __('Set ticket owner')"
      @click="emit('edit')"
    />
  </span>
</template>

<script setup lang="ts">
import { useAssignablePeople } from "@/composables/assignablePeople";
import { useOnLeave } from "@/composables/onLeave";
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import LucideUserCheck from "~icons/lucide/user-check";

defineProps<{
  owner?: string | null;
  backup?: string | null;
  /** managers, Project Managers and department heads (the server checks too) */
  editable?: boolean;
}>();

const emit = defineEmits<{ edit: [] }>();

const { nameOf, isInactive } = useAssignablePeople();
const { leaveLabel } = useOnLeave();

/** Why someone can't take new tickets today, or "". */
function away(user: string) {
  return isInactive(user) ? __("inactive") : leaveLabel(user);
}
</script>

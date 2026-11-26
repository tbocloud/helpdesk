<template>
  <!-- adds an agent to the sales team, or changes the team roles of someone on it -->
  <Dialog
    :open="open"
    :title="member ? __('Roles of {0}', member.full_name) : __('Add to team')"
    size="md"
    @update:open="(value: boolean) => !value && emit('close')"
  >
    <form :id="formId" class="flex flex-col gap-4" @submit.prevent="save">
      <Combobox
        v-if="!member"
        v-model="person"
        :options="personOptions"
        :label="__('Person')"
        :placeholder="__('Pick an agent')"
      />
      <fieldset class="flex flex-col gap-3">
        <legend class="mb-2 text-sm text-ink-gray-6">
          {{ __("Sales roles") }}
        </legend>
        <div
          v-for="role in roles"
          :key="role"
          class="rounded-lg border border-outline-gray-2 p-3"
        >
          <Checkbox
            :label="__(role)"
            :description="ROLE_HINTS[role]"
            :model-value="picked.includes(role)"
            @update:model-value="toggle(role, !!$event)"
          />
        </div>
      </fieldset>
      <ErrorMessage :message="saving.error ? errorText(saving.error) : ''" />
    </form>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="emit('close')" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="member ? __('Save roles') : __('Add to team')"
          :loading="saving.loading"
          :disabled="!ready || saving.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Checkbox,
  Combobox,
  createResource,
  Dialog,
  ErrorMessage,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { ROLE_HINTS, type TeamCandidate, type TeamMember } from "./salesTeam";

const props = defineProps<{
  open: boolean;
  /** who to change; none adds someone from `candidates` */
  member: TeamMember | null;
  roles: string[];
  candidates: TeamCandidate[];
}>();
const emit = defineEmits<{ close: []; saved: [] }>();

const formId = `member-roles-${useId()}`;
const person = ref("");
const picked = ref<string[]>([]);

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    person.value = "";
    picked.value = [...(props.member?.roles ?? [])];
    saving.reset();
  }
);

const personOptions = computed(() =>
  props.candidates.map((c) => ({ label: c.full_name, value: c.user }))
);
// removing every role is Remove from team, which asks first; here at least one stays
const ready = computed(
  () => picked.value.length > 0 && (!!props.member || !!person.value)
);

function toggle(role: string, on: boolean) {
  picked.value = on
    ? [...picked.value, role]
    : picked.value.filter((r) => r !== role);
}

const saving = createResource({
  url: "helpdesk.api.sales_team.set_member_roles",
  onSuccess() {
    toast.success(
      props.member ? __("Roles saved") : __("Added to the sales team")
    );
    emit("saved");
  },
});

function save() {
  if (!ready.value) return;
  saving.submit({
    user: props.member?.user ?? person.value,
    roles: picked.value,
  });
}
</script>

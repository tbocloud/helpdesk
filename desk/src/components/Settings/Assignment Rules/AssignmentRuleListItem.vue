<template>
  <SettingsListItem
    :title="data.name"
    :subtitle="data.description || undefined"
    :muted="Boolean(data.disabled)"
    @open="assignmentRulesActiveScreen = { screen: 'view', data: data }"
  >
    <template #meta>
      <label class="flex shrink-0 items-center gap-1 text-sm text-ink-gray-6">
        <span class="hidden sm:inline">{{ __("Priority") }}</span>
        <select
          v-model="data.priority"
          class="h-7 rounded border-0 bg-transparent py-0 pe-6 ps-2 text-base text-ink-gray-8 hover:bg-surface-gray-3"
          :aria-label="__('Priority of {0}', data.name)"
          @change="onPriorityChange"
        >
          <option
            v-for="option in priorityOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
      </label>
    </template>
    <template #actions>
      <Switch
        size="sm"
        :label="__('Enabled')"
        :model-value="!data.disabled"
        @update:model-value="onToggle"
      />
      <Dropdown placement="right" :options="dropdownOptions">
        <Button
          variant="ghost"
          :label="__('More actions for {0}', data.name)"
          @click="isConfirmingDelete = false"
        >
          <template #icon>
            <LucideEllipsis class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </Dropdown>
    </template>
  </SettingsListItem>
  <DuplicateDialog
    v-model:open="duplicateDialog.show"
    v-model:name="duplicateDialog.newName"
    :title="__('Duplicate assignment rule')"
    :label="__('Name of the copy')"
    @duplicate="duplicate()"
  />
</template>

<script setup lang="ts">
import { assignmentRulesActiveScreen } from "@/stores/assignmentRules";
import { __ } from "@/translation";
import { AssignmentRuleListResourceSymbol } from "@/types";
import { AssignmentRule } from "@/types/doctypes";
import { ConfirmDelete } from "@/utils";
import { Button, createResource, Dropdown, Switch, toast } from "frappe-ui";
import LucideEllipsis from "~icons/lucide/ellipsis";
import DuplicateDialog from "../DuplicateDialog.vue";
import SettingsListItem from "../SettingsListItem.vue";
import { inject, ref } from "vue";

const assignmentRulesListData = inject(AssignmentRuleListResourceSymbol);

const props = defineProps({
  data: {
    type: Object,
    required: true,
  },
});

const priorityOptions = [
  { label: __("Low"), value: "0" },
  { label: __("Low-Medium"), value: "1" },
  { label: __("Medium"), value: "2" },
  { label: __("Medium-High"), value: "3" },
  { label: __("High"), value: "4" },
];

const duplicateDialog = ref({
  show: false,
  newName: "",
  name: "",
});

const isConfirmingDelete = ref(false);

const deleteAssignmentRule = () => {
  createResource({
    url: "frappe.client.delete",
    params: {
      doctype: "Assignment Rule",
      name: props.data.name,
    },
    onSuccess: () => {
      assignmentRulesListData?.reload();
      isConfirmingDelete.value = false;
      toast.success(__("Assignment rule deleted successfully."));
    },
    auto: true,
  });
};

const dropdownOptions = [
  {
    label: __("Duplicate"),
    onClick: () => {
      duplicateDialog.value = {
        show: true,
        newName: props.data.name + " (Copy)",
        name: props.data.name,
      };
    },
    icon: "lucide-copy",
  },
  ...ConfirmDelete({
    onConfirmDelete: () => deleteAssignmentRule(),
    isConfirmingDelete,
  }),
];

const duplicate = () => {
  createResource({
    url: "frappe.client.get",
    params: {
      doctype: "Assignment Rule",
      name: duplicateDialog.value.name,
    },
    onSuccess: (data: AssignmentRule) => {
      createResource({
        url: "frappe.client.insert",
        params: {
          doc: {
            ...data,
            name: duplicateDialog.value.newName,
          },
        },
        auto: true,
        onSuccess(newAssignmentRuleData: AssignmentRule) {
          assignmentRulesListData?.reload();
          toast.success(__("Assignment rule duplicated successfully."));
          duplicateDialog.value = {
            show: false,
            newName: "",
            name: "",
          };
          setTimeout(() => {
            assignmentRulesActiveScreen.value = {
              screen: "view",
              data: newAssignmentRuleData,
            };
          }, 250);
        },
      });
    },
    auto: true,
  });
};

const onPriorityChange = () => {
  setAssignmentRuleValue("priority", props.data.priority);
};

const onToggle = (enabled: boolean) => {
  if (!props.data.users_exists && props.data.disabled) {
    toast.error(__("Cannot enable rule without adding users in it"));
    return;
  }
  // Optimistically flip so the switch reflects the new state immediately;
  // revert if the backend update fails.
  const previous = props.data.disabled;
  props.data.disabled = enabled ? 0 : 1;
  setAssignmentRuleValue("disabled", props.data.disabled, "status", () => {
    props.data.disabled = previous;
  });
};

const setAssignmentRuleValue = (
  key: string,
  value: any,
  fieldName?: string,
  onError?: () => void
) => {
  createResource({
    url: "frappe.client.set_value",
    params: {
      doctype: "Assignment Rule",
      name: props.data.name,
      fieldname: key,
      value: value,
    },
    onSuccess: () => {
      toast.success(
        __("Assignment rule {0} updated successfully.", fieldName || key)
      );
    },
    onError: () => {
      onError?.();
      toast.error(
        __("Failed to update assignment rule {0}.", fieldName || key)
      );
    },
    auto: true,
  });
};
</script>

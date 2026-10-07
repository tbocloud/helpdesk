<template>
  <SettingsListItem
    :title="data.name"
    :subtitle="data.description || undefined"
    :muted="!data.enabled"
    @open="slaActiveScreen = { screen: 'view', data: data, fetchData: true }"
  >
    <template v-if="data.default_sla" #badges>
      <TaskyBadge :label="__('Default')" />
    </template>
    <template #actions>
      <Switch
        size="sm"
        :label="__('Enabled')"
        :model-value="Boolean(data.enabled)"
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
    :title="__('Duplicate SLA policy')"
    :label="__('Name of the copy')"
    @duplicate="duplicate()"
  />
</template>

<script setup lang="ts">
import { Switch, Button, createResource, toast, Dropdown } from "frappe-ui";
import LucideEllipsis from "~icons/lucide/ellipsis";
import TaskyBadge from "@/components/TaskyBadge.vue";
import DuplicateDialog from "../DuplicateDialog.vue";
import SettingsListItem from "../SettingsListItem.vue";
import { ref, inject } from "vue";
import { slaActiveScreen } from "@/stores/sla";
import { ConfirmDelete } from "@/utils";
import { __ } from "@/translation";
import { SlaPolicyListResourceSymbol } from "@/types";
import { HDServiceLevelAgreement } from "@/types/doctypes";

const slaPolicyList = inject(SlaPolicyListResourceSymbol);

const duplicateDialog = ref({
  show: false,
  newName: "",
  name: "",
});

const props = defineProps({
  data: {
    type: Object,
    required: true,
  },
});

const isConfirmingDelete = ref(false);

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
    onConfirmDelete: () => deleteSla(),
    isConfirmingDelete,
  }),
];

const duplicate = () => {
  createResource({
    url: "frappe.client.get",
    params: {
      doctype: "HD Service Level Agreement",
      name: duplicateDialog.value.name,
    },
    onSuccess: (data: HDServiceLevelAgreement) => {
      createResource({
        url: "frappe.client.insert",
        params: {
          doc: {
            ...data,
            default_sla: false,
            service_level: duplicateDialog.value.newName,
            name: duplicateDialog.value.newName,
          },
        },
        auto: true,
        onSuccess(newSlaPolicyData: HDServiceLevelAgreement) {
          slaPolicyList?.reload();
          toast.success(__("SLA policy duplicated successfully."));
          duplicateDialog.value = {
            show: false,
            newName: "",
            name: "",
          };
          setTimeout(() => {
            slaActiveScreen.value = {
              screen: "view",
              data: newSlaPolicyData,
              fetchData: true,
            };
          }, 250);
        },
      });
    },
    auto: true,
  });
};

const deleteSla = () => {
  if (!isConfirmingDelete.value) {
    isConfirmingDelete.value = true;
    return;
  }

  slaPolicyList?.delete.submit(props.data.name, {
    onSuccess: () => {
      toast.success(__("SLA policy deleted successfully."));
    },
  });
};

const onToggle = () => {
  if (props.data.default_sla) {
    toast.error(__("SLA set as default cannot be disabled."));
    return;
  }
  slaPolicyList?.setValue.submit(
    {
      name: props.data.name,
      enabled: !props.data.enabled,
    },
    {
      onSuccess: () => {
        toast.success(__("SLA policy status updated successfully."));
      },
    }
  );
};
</script>

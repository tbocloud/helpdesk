<template>
  <SettingsListItem
    :title="data.name"
    :subtitle="data.description || undefined"
    @open="holidayListActiveScreen = { screen: 'view', data: data }"
  >
    <template #actions>
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
    :title="__('Duplicate holiday schedule')"
    :label="__('Name of the copy')"
    :maxlength="100"
    @duplicate="duplicate()"
  />
</template>

<script setup lang="ts">
import { Button, createResource, Dropdown, toast } from "frappe-ui";
import LucideEllipsis from "~icons/lucide/ellipsis";
import DuplicateDialog from "../DuplicateDialog.vue";
import SettingsListItem from "../SettingsListItem.vue";
import { inject, ref } from "vue";
import { holidayListActiveScreen } from "@/stores/holidayList";
import { ConfirmDelete } from "@/utils";
import { __ } from "@/translation";
import { HolidayListResourceSymbol } from "@/types";
import { HDServiceHolidayList } from "@/types/doctypes";

const props = defineProps({
  data: {
    type: Object,
    required: true,
  },
});

const holidayList = inject(HolidayListResourceSymbol);

const duplicateDialog = ref({
  show: false,
  newName: "",
  name: "",
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
    onConfirmDelete: () => deleteHolidayList(),
    isConfirmingDelete,
  }),
];

const duplicate = () => {
  createResource({
    url: "frappe.client.get",
    params: {
      doctype: "HD Service Holiday List",
      name: duplicateDialog.value.name,
    },
    onSuccess: (data: HDServiceHolidayList) => {
      createResource({
        url: "frappe.client.insert",
        params: {
          doc: {
            ...data,
            holiday_list_name: duplicateDialog.value.newName,
            name: duplicateDialog.value.newName,
          },
        },
        auto: true,
        onSuccess(newHolidayListData: HDServiceHolidayList) {
          holidayList?.reload();
          toast.success(__("Holiday list duplicated successfully."));
          duplicateDialog.value = {
            show: false,
            newName: "",
            name: "",
          };
          setTimeout(() => {
            holidayListActiveScreen.value = {
              screen: "view",
              data: newHolidayListData,
            };
          }, 250);
        },
      });
    },
    auto: true,
  });
};

const deleteHolidayList = () => {
  if (!isConfirmingDelete.value) {
    isConfirmingDelete.value = true;
    return;
  }

  holidayList?.delete.submit(props.data.name, {
    onSuccess: () => {
      toast.success(__("Holiday list deleted successfully."));
    },
  });
};
</script>

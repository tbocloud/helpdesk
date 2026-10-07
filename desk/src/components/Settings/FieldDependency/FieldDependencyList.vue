<template>
  <SettingsLayoutBase :title="__('Field Dependencies')">
    <template #description>
      <p class="max-w-prose text-p-sm text-ink-gray-6">
        {{
          __(
            "Narrow one ticket field's options by what was picked in another, e.g. sub-categories by category."
          )
        }}
        <a
          href="https://docs.frappe.io/helpdesk/field-dependency"
          target="_blank"
          rel="noopener noreferrer"
          class="underline"
          >{{ __("How field dependencies work") }}</a
        >
      </p>
    </template>
    <template #header-actions>
      <Button
        variant="solid"
        :label="__('New field dependency')"
        @click="$emit('update:step', 'fd')"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template #content>
      <SettingsList
        :items="fieldDependenciesList.data"
        :label="__('Field dependencies')"
        :loading="fieldDependenciesList.list.loading"
        :error="fieldDependenciesList.list.error"
        :empty-icon="FieldDependencyIcon"
        :empty-title="__('No field dependencies yet')"
        :empty-message="
          __('Add one to show only the options that fit an earlier choice.')
        "
        @retry="fieldDependenciesList.reload()"
      >
        <template #default="{ item: row }">
          <SettingsListItem
            :title="getFieldDependencyLabel(row.name)"
            :muted="!row.enabled"
            @open="$emit('update:step', 'fd', row.name)"
          >
            <template #meta>
              <span
                class="hidden w-40 shrink-0 items-center gap-1.5 text-sm text-ink-gray-7 md:flex"
              >
                <Avatar size="sm" :image="row.owner" :label="row.owner" />
                <span class="truncate" :title="row.owner">{{ row.owner }}</span>
              </span>
            </template>
            <template #actions>
              <Switch
                size="sm"
                :label="__('Enabled')"
                :model-value="Boolean(row.enabled)"
                @update:model-value="(e) => handleSwitchToggle(row, e)"
              />
              <Dropdown placement="right" :options="getOptions(row.name)">
                <Button
                  variant="ghost"
                  :label="
                    __(
                      'More actions for {0}',
                      getFieldDependencyLabel(row.name)
                    )
                  "
                  @click="isConfirmingDelete = false"
                >
                  <template #icon>
                    <LucideEllipsis class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </Dropdown>
            </template>
          </SettingsListItem>
        </template>
      </SettingsList>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { Avatar, Button, Dropdown, Switch, toast } from "frappe-ui";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucidePlus from "~icons/lucide/plus";
import { getFieldDependencyLabel, ConfirmDelete } from "@/utils";
import { onMounted, ref } from "vue";
import { fieldDependenciesList } from "./fieldDependency";
import FieldDependencyIcon from "@/components/icons/FieldDependencyIcon.vue";
import { __ } from "@/translation";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";

onMounted(() => {
  fieldDependenciesList.reload();
});

const isConfirmingDelete = ref(false);

function getOptions(rowName: string) {
  return ConfirmDelete({
    isConfirmingDelete,
    onConfirmDelete: () => {
      fieldDependenciesList.delete.submit(rowName, {
        onSuccess: () => {
          toast.success(__("Field dependency deleted successfully."));
          fieldDependenciesList.reload();
        },
      });
    },
  });
}

function handleSwitchToggle(row: any, value: boolean) {
  // Optimistically reflect the new state so the controlled Switch stays in
  // sync; without this the bound value never changes and toggling keeps
  // re-sending the same value (the disable never takes effect).
  row.enabled = value;
  fieldDependenciesList.setValue.submit(
    {
      name: row.name,
      enabled: value,
    },
    {
      onSuccess: () => {
        toast.success(__("Field dependency updated successfully."));
      },
      onError: () => {
        row.enabled = !value;
        toast.error(__("Failed to update field dependency."));
      },
    }
  );
}
</script>

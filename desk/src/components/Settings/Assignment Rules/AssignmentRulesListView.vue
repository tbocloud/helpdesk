<template>
  <SettingsList
    :items="assignmentRulesList"
    :label="__('Assignment rules')"
    :loading="assignmentRulesListData.loading"
    :error="assignmentRulesListData.error"
    :filtered="Boolean(assignmentRuleSearchQuery)"
    :empty-icon="Settings"
    :empty-title="__('No assignment rules yet')"
    :empty-message="
      __('Add a rule to hand new tickets to agents automatically.')
    "
    @retry="assignmentRulesListData.reload()"
    @clear-filters="assignmentRuleSearchQuery = ''"
  >
    <template #default="{ item }">
      <AssignmentRuleListItem :data="item" />
    </template>
  </SettingsList>
</template>

<script setup lang="ts">
import { inject, Ref, ref, watch } from "vue";
import AssignmentRuleListItem from "./AssignmentRuleListItem.vue";
import Settings from "~icons/lucide/settings-2";
import SettingsList from "../SettingsList.vue";
import { AssignmentRuleListResourceSymbol } from "@/types";

const assignmentRulesListData = inject(AssignmentRuleListResourceSymbol);

const assignmentRulesList = ref(assignmentRulesListData.data || []);

const assignmentRuleSearchQuery = inject<Ref>("assignmentRuleSearchQuery");

watch(
  () => [assignmentRuleSearchQuery.value, assignmentRulesListData.data],
  ([query, data]) => {
    if (!query) {
      assignmentRulesList.value = data || [];
      return;
    }
    assignmentRulesList.value =
      data?.filter((item) => {
        return (
          item.name.toLowerCase().includes(query.toLowerCase()) ||
          (item.description || "").toLowerCase().includes(query.toLowerCase())
        );
      }) || [];
  }
);
</script>

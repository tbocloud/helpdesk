<template>
  <SettingsLayoutBase
    :title="__('Assignment Rules')"
    :description="
      __(
        'Assignment Rules automatically route tickets to the right team members based on predefined conditions.'
      )
    "
  >
    <template #header-actions>
      <Button
        variant="solid"
        :label="__('New assignment rule')"
        @click="goToNew()"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template
      v-if="
        assignmentRulesListData.data?.length > 9 ||
        assignmentRuleSearchQuery.length
      "
      #header-bottom
    >
      <SettingsSearch
        v-model="assignmentRuleSearchQuery"
        :placeholder="__('Search assignment rules')"
      />
    </template>
    <template #content>
      <AssignmentRulesListView />
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { Button, createResource } from "frappe-ui";
import { inject, provide, Ref } from "vue";
import {
  assignmentRulesActiveScreen,
  resetAssignmentRuleData,
} from "@/stores/assignmentRules";
import AssignmentRulesListView from "./AssignmentRulesListView.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import LucidePlus from "~icons/lucide/plus";
import SettingsSearch from "../SettingsSearch.vue";
import { AssignmentRuleListResourceSymbol } from "@/types";

const assignmentRulesListData = createResource({
  url: "helpdesk.api.assignment_rule.get_assignment_rules_list",
  cache: ["assignmentRules", "get_assignment_rules_list"],
  auto: true,
});
const assignmentRuleSearchQuery = inject<Ref>("assignmentRuleSearchQuery");

provide(AssignmentRuleListResourceSymbol, assignmentRulesListData);

const goToNew = () => {
  resetAssignmentRuleData();
  assignmentRulesActiveScreen.value = {
    screen: "view",
    data: null,
  };
};
</script>

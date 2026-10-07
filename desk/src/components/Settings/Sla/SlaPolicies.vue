<template>
  <SettingsLayoutBase :title="__('SLA Policies')">
    <template #description>
      <p class="max-w-prose text-p-sm text-ink-gray-6">
        {{
          __(
            "How fast tickets must get a first response and a resolution, by priority and working hours."
          )
        }}
        <a
          href="https://docs.frappe.io/helpdesk/service-level-agreement"
          target="_blank"
          rel="noopener noreferrer"
          class="underline"
          >{{ __("How SLAs work") }}</a
        >
      </p>
    </template>
    <template #header-actions>
      <Button variant="solid" :label="__('New SLA policy')" @click="goToNew()">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template
      v-if="slaPolicyList.data?.length > 9 || slaSearchQuery.length"
      #header-bottom
    >
      <SettingsSearch
        v-model="slaSearchQuery"
        :placeholder="__('Search SLA policies')"
      />
    </template>
    <template #content>
      <SlaPolicyList />
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { resetSlaData, slaActiveScreen } from "@/stores/sla";
import { Button } from "frappe-ui";
import LucidePlus from "~icons/lucide/plus";
import SettingsSearch from "../SettingsSearch.vue";
import SlaPolicyList from "./SlaPolicyList.vue";
import { inject, Ref, watch } from "vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { SlaPolicyListResourceSymbol } from "@/types";

const slaPolicyList = inject(SlaPolicyListResourceSymbol);
const slaSearchQuery = inject<Ref>("slaSearchQuery");

const goToNew = () => {
  resetSlaData();
  slaActiveScreen.value = {
    screen: "view",
    data: null,
    fetchData: true,
  };
};

watch(slaSearchQuery, (newValue) => {
  slaPolicyList.filters = {
    name: ["like", `%${newValue}%`],
  };
  if (!newValue) {
    slaPolicyList.start = 0;
    slaPolicyList.pageLength = 10;
  }
  slaPolicyList.reload();
});
</script>

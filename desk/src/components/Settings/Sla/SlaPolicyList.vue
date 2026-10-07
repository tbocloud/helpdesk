<template>
  <SettingsList
    :items="slaPolicyList.data"
    :label="__('SLA policies')"
    :loading="slaPolicyList.list.loading"
    :error="slaPolicyList.list.error"
    :filtered="Boolean(slaSearchQuery)"
    :empty-icon="ShieldCheck"
    :empty-title="__('No SLA policies yet')"
    :empty-message="
      __(
        'Add a policy to set response and resolution targets for your tickets.'
      )
    "
    @retry="slaPolicyList.reload()"
    @clear-filters="slaSearchQuery = ''"
  >
    <template #default="{ item }">
      <SlaPolicyListItem :data="item" />
    </template>
  </SettingsList>
</template>

<script setup lang="ts">
import { SlaPolicyListResourceSymbol } from "@/types";
import { inject, Ref } from "vue";
import ShieldCheck from "~icons/lucide/shield-check";
import SettingsList from "../SettingsList.vue";
import SlaPolicyListItem from "./SlaPolicyListItem.vue";

const slaPolicyList = inject(SlaPolicyListResourceSymbol);
const slaSearchQuery = inject<Ref<string>>("slaSearchQuery");
</script>

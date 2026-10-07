<template>
  <SettingsList
    :items="holidayList.data"
    :label="__('Holiday schedules')"
    :loading="holidayList.list.loading"
    :error="holidayList.list.error"
    :filtered="Boolean(holidaySearchRef)"
    :empty-icon="Briefcase"
    :empty-title="__('No holiday schedules yet')"
    :empty-message="
      __(
        'Add your working hours and holidays so SLA timers pause outside them.'
      )
    "
    @retry="holidayList.reload()"
    @clear-filters="holidaySearchRef = ''"
  >
    <template #default="{ item }">
      <HolidayListItem :data="item" />
    </template>
  </SettingsList>
</template>

<script setup lang="ts">
import { HolidayListResourceSymbol } from "@/types";
import { inject, Ref } from "vue";
import Briefcase from "~icons/lucide/briefcase";
import SettingsList from "../SettingsList.vue";
import HolidayListItem from "./HolidayListItem.vue";

const holidayList = inject(HolidayListResourceSymbol);
const holidaySearchRef = inject<Ref<string>>("holidaySearchRef");
</script>

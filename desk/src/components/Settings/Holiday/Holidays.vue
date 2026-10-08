<template>
  <SettingsLayoutBase
    :title="__('Business Holidays')"
    :description="
      __(
        'Working days, hours and holidays. SLA timers only run inside these hours.'
      )
    "
  >
    <template #header-actions>
      <Button
        variant="solid"
        :label="__('New holiday schedule')"
        @click="goToNew()"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template
      v-if="holidayList.data?.length > 9 || holidaySearchRef.length"
      #header-bottom
    >
      <SettingsSearch
        v-model="holidaySearchRef"
        :placeholder="__('Search holiday schedules')"
      />
    </template>
    <template #content>
      <HolidayList />
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import {
  holidayListActiveScreen,
  resetHolidayData,
} from "@/stores/holidayList";
import { Button } from "frappe-ui";
import LucidePlus from "~icons/lucide/plus";
import SettingsSearch from "../SettingsSearch.vue";
import HolidayList from "./HolidayList.vue";
import { inject, Ref, watch } from "vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { HolidayListResourceSymbol } from "@/types";

const holidayList = inject(HolidayListResourceSymbol);
const holidaySearchRef = inject<Ref<string>>("holidaySearchRef");

const goToNew = () => {
  resetHolidayData();
  holidayListActiveScreen.value = {
    screen: "view",
    data: null,
  };
};

watch(holidaySearchRef, (newValue) => {
  holidayList.filters = {
    name: ["like", `%${newValue}%`],
  };
  if (!newValue) {
    holidayList.start = 0;
    holidayList.pageLength = 10;
  }
  holidayList.reload();
});
</script>

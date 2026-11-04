<template>
  <!-- stays out until the ERP site's TBO Smart has the Lead Bank -->
  <SettingsSection
    v-if="settings.data || error"
    :title="__('Referral (Lead Bank)')"
    :description="
      __(
        'Staff who add a lead in the Lead Bank earn a percentage of the money collected when it becomes a client and pays, by the country they added it in, up to a cap per lead. Salespeople who own the lead earn no referral on it. Leads of a country with no department wait in a list for managers to place.'
      )
    "
  >
    <div
      v-if="error"
      role="alert"
      class="flex flex-wrap items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
    >
      <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
      <span class="min-w-0 flex-1">{{ error }}</span>
      <Button :label="__('Try again')" @click="settings.reload()" />
    </div>
    <form v-else class="flex flex-col gap-4" novalidate @submit.prevent="save">
      <div
        v-for="row in form.regions"
        :key="row.region"
        class="grid grid-cols-1 items-end gap-3 sm:grid-cols-[6rem_8rem_minmax(0,1fr)]"
      >
        <span class="text-base-medium text-ink-gray-9">{{
          REGION_LABEL[row.region]
        }}</span>
        <FormControl
          v-model="row.rate"
          type="number"
          min="0"
          max="100"
          step="0.5"
          :label="__('Referral %')"
        />
        <FormControl
          v-model="row.department"
          type="select"
          :label="__('Department')"
          :options="departmentOptions(row)"
        />
      </div>
      <FormControl
        v-model="form.cap"
        class="sm:max-w-xs"
        type="number"
        min="0"
        :label="__('Cap per lead ({0}, 0 for none)', currency)"
      />
      <p class="text-p-xs text-ink-gray-6">
        {{
          __(
            "The cap is in {0}, whatever the country, because payments are counted in it. India's blank department means the one called TBO.",
            currency
          )
        }}
      </p>
      <p
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ errorMessage }}
      </p>
      <div>
        <Button
          variant="solid"
          type="submit"
          :label="__('Save')"
          :loading="saving"
        />
      </div>
    </form>
  </SettingsSection>
</template>

<script setup lang="ts">
import {
  REGION_LABEL,
  type ReferralSettings,
  type ReferralSettingsRegion,
} from "@/pages/lead-bank/leadBank";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, createResource, FormControl, toast } from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import SettingsSection from "../SettingsSection.vue";

interface RegionForm {
  region: ReferralSettingsRegion["region"];
  rate: number | string;
  department: string;
}

const settings = createResource<ReferralSettings>({
  url: "helpdesk.api.lead_bank.get_referral_settings",
  auto: true,
});
const currency = computed(() => settings.data?.currency || "INR");
const error = computed(() =>
  settings.error
    ? errorText(
        settings.error,
        __("Couldn't load the referral settings. Check your connection.")
      )
    : ""
);

const form = reactive<{ regions: RegionForm[]; cap: number | string }>({
  regions: [],
  cap: 0,
});
const errorMessage = ref("");
const saving = ref(false);

watch(
  () => settings.data,
  (data) => {
    if (!data) return;
    form.regions = data.regions.map((r) => ({
      region: r.region,
      rate: r.rate,
      department: r.department ?? "",
    }));
    form.cap = data.cap;
  },
  { immediate: true }
);

function departmentOptions(row: RegionForm) {
  const names = settings.data?.departments ?? [];
  return [
    { label: __("None (use the default)"), value: "" },
    ...names.map((name) => ({ label: name, value: name })),
    // a department since removed still shows what is set
    ...(row.department && !names.includes(row.department)
      ? [{ label: row.department, value: row.department }]
      : []),
  ];
}

function save() {
  if (saving.value) return;
  errorMessage.value = "";
  saving.value = true;
  call("helpdesk.api.lead_bank.save_referral_settings", {
    values: {
      regions: form.regions.map((r) => ({
        region: r.region,
        rate: Number(r.rate) || 0,
        department: r.department,
      })),
      cap: Number(form.cap) || 0,
    },
  })
    .then(() => {
      toast.success(__("Referral settings saved"));
      settings.reload();
    })
    // the ERP site's own reason, e.g. a rate above 100
    .catch((e: unknown) => {
      errorMessage.value = errorText(
        e,
        __("Couldn't save. Check your connection and try again.")
      );
    })
    .finally(() => (saving.value = false));
}
</script>

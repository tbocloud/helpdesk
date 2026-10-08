<template>
  <SettingsLayoutBase
    :title="__('Telephony')"
    :description="
      __(
        'Calls from helpdesk: your default provider, and each provider\'s setup.'
      )
    "
    :dirty="isDirty.twilio || isDirty.exotel || isDirty.telephonyAgent"
    :saving="
      twilio.save.loading || exotel.save.loading || telephonyAgent.save.loading
    "
    @save="save"
  >
    <template #content>
      <div class="flex flex-col gap-6">
        <SettingRow
          v-slot="{ id, labelledby }"
          :label="__('Default medium')"
          :description="__('Default calling medium for logged in user')"
        >
          <SelectDropdown
            :id="id"
            :labelledby="labelledby"
            :options="telephonyProviders"
            :modelValue="telephonyAgent.doc?.default_medium"
            @update:modelValue="telephonyAgent.doc.default_medium = $event"
            :defaultValue="telephonyAgent.originalDoc?.default_medium"
            placement="bottom-start"
          />
        </SettingRow>
        <SettingsList
          :items="providers"
          :label="__('Telephony providers')"
          :empty-icon="LucidePhone"
          :empty-title="__('No telephony providers')"
        >
          <template #default="{ item }">
            <SettingsListItem
              :title="item.label"
              :subtitle="item.description"
              @open="emit('updateStep', item.step)"
            />
          </template>
        </SettingsList>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { createDocumentResource, toast, createResource } from "frappe-ui";
import SelectDropdown from "@/components/SelectDropdown.vue";
import { ref, watch } from "vue";
import LucidePhone from "~icons/lucide/phone";
import { isDocDirty, validateExotel, validateTwilio } from "./utils";
import { useAuthStore } from "@/stores/auth";
import { useTelephonyStore } from "@/stores/telephony";
import { disableSettingModalOutsideClick } from "../settingsModal";
import { __ } from "@/translation";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import SettingRow from "../SettingRow.vue";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";

const auth = useAuthStore();
const telephonyStore = useTelephonyStore();
const isDirty = ref({
  twilio: false,
  exotel: false,
  telephonyAgent: false,
});
const emit = defineEmits(["updateStep"]);

const twilioErrors = ref({
  accountSid: "",
  authToken: "",
  number: "",
  default_medium: "",
});

const exotelErrors = ref({
  accountSid: "",
  webhookVerifyToken: "",
  subdomain: "",
  apiKey: "",
  apiToken: "",
  number: "",
  mobileNo: "",
  default_medium: "",
});

const twilio = createDocumentResource({
  doctype: "TP Twilio Settings",
  name: "TP Twilio Settings",
  cache: ["tp_twilio_settings"],
  fields: ["*"],
  auto: true,
});

const exotel = createDocumentResource({
  doctype: "TP Exotel Settings",
  name: "TP Exotel Settings",
  cache: ["tp_exotel_settings"],
  fields: ["*"],
  auto: true,
});

const telephonyAgent = createDocumentResource({
  doctype: "TP Telephony Agent",
  name: auth.user,
  cache: ["tp_telephony_agent"],
  fields: ["*"],
  auto: false,
  onError(er) {
    toast.error(er?.messages?.[0] || __("Failed to load telephony agent"));
  },
});

const telephonyProviders = [
  { label: "Twilio", value: "Twilio" },
  { label: "Exotel", value: "Exotel" },
];

const providers = [
  {
    name: "twilio",
    label: __("Twilio"),
    description: __(
      "Configure your Twilio telephony integration settings here"
    ),
    step: "twilio-settings",
  },
  {
    name: "exotel",
    label: __("Exotel"),
    description: __(
      "Configure your Exotel telephony integration settings here"
    ),
    step: "exotel-settings",
  },
];

async function save() {
  validateTwilio(twilio.doc, telephonyAgent.doc, twilioErrors);
  validateExotel(exotel.doc, telephonyAgent.doc, exotelErrors);
  if (Object.values(twilioErrors.value).some((v) => v)) {
    toast.error(__("Please configure your Twilio settings correctly"));
    return;
  }
  if (Object.values(exotelErrors.value).some((v) => v)) {
    toast.error(__("Please configure your Exotel settings correctly"));
    return;
  }

  const promises = [];

  // Temporary fix, as createDocumentResource's dirty state has bug
  if (isDirty.value.twilio) {
    promises.push(
      twilio.save.submit().catch((er) => {
        const error = __(`Twilio error: {0}`, er?.messages?.[0]);
        toast.error(error || __("Failed to save Twilio settings"));
      })
    );
  }
  if (isDirty.value.exotel) {
    promises.push(
      exotel.save.submit().catch((er) => {
        const error = __(`Exotel error: {0}`, er?.messages?.[0]);
        toast.error(error || __("Failed to save Exotel settings"));
      })
    );
  }
  if (isDirty.value.telephonyAgent) {
    if (telephonyAgent.doc.twilio_number) {
      telephonyAgent.doc.twilio = true;
    } else {
      telephonyAgent.doc.twilio = false;
    }

    if (telephonyAgent.doc.exotel_number) {
      telephonyAgent.doc.exotel = true;
    } else {
      telephonyAgent.doc.exotel = false;
    }
    promises.push(telephonyAgent.save.submit());
  }

  const results = await Promise.all(promises);

  if (!results.some((result) => result == undefined)) {
    toast.success(__("Telephony settings updated successfully."));
  }

  // Reload twilio to prevent "doc has been modified" error, as an application is created and doc is updated on save
  await twilio.reload();
  telephonyStore.fetchCallIntegrationStatus();
}

createResource({
  url: "telephony.api.create_telephony_agent",
  auto: true,
  onSuccess() {
    telephonyAgent.get.submit();
  },
});

watch(
  () => telephonyAgent.doc,
  (newVal) => {
    isDirty.value.telephonyAgent = isDocDirty(
      newVal,
      telephonyAgent.originalDoc
    );
    if (isDirty.value.telephonyAgent) {
      disableSettingModalOutsideClick.value = true;
    } else {
      disableSettingModalOutsideClick.value = false;
    }
  },
  { deep: true }
);

watch(
  () => twilio.doc,
  (newVal) => {
    isDirty.value.twilio = isDocDirty(newVal, twilio.originalDoc);
    if (isDirty.value.twilio) {
      disableSettingModalOutsideClick.value = true;
    } else {
      disableSettingModalOutsideClick.value = false;
    }
  },
  { deep: true }
);

watch(
  () => exotel.doc,
  (newVal) => {
    isDirty.value.exotel = isDocDirty(newVal, exotel.originalDoc);
    if (isDirty.value.exotel) {
      disableSettingModalOutsideClick.value = true;
    } else {
      disableSettingModalOutsideClick.value = false;
    }
  },
  { deep: true }
);
</script>

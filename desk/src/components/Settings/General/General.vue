<template>
  <SettingsLayoutBase
    :title="__('General')"
    :description="
      __('Branding, ticket rules and sign-up for everyone on this helpdesk.')
    "
    :dirty="isDirty"
    :saving="
      saveSettingsResource.loading || saveWebsiteSettingsResource.loading
    "
    :loading="settingsDataResource.loading && !settingsDataResource.data"
    :error="settingsDataResource.error"
    @retry="settingsDataResource.reload()"
    @save="saveSettings"
  >
    <template #content>
      <div>
        <Branding />
        <TicketSettings />
        <WorkflowKnowledgebaseSettings />
        <SettingsSection :title="__('User sign-up')">
          <SettingRow
            v-slot="{ id }"
            :label="__('Disable signup')"
            :description="
              __(
                'New users will have to be manually registered by system managers.'
              )
            "
          >
            <Switch :id="id" v-model="disableSignup" />
          </SettingRow>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { useConfigStore } from "@/stores/config";
import { __ } from "@/translation";
import { HDSettings, HDSettingsSymbol } from "@/types";
import { createResource, Switch, toast } from "frappe-ui";
import { computed, provide, ref, watch } from "vue";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";
import Branding from "./components/Branding.vue";
import TicketSettings from "./components/TicketSettings.vue";
import WorkflowKnowledgebaseSettings from "./components/WorkflowKnowledgebaseSettings.vue";

const configStore = useConfigStore();

const isDirty = ref(false);
const initialData = ref<null | string>(null);
const settingsData = ref({
  brandName: "",
  brandLogo: "",
  favicon: "",
  autoCloseAfterDays: "",
  autoCloseStatus: "",
  autoCloseTickets: "",
  assignWithinTeam: false,
  doNotRestrictTicketsWithoutAnAgentGroup: false,
  restrictTicketsByAgentGroup: false,
  updateStatusTo: "",
  autoUpdateStatus: false,
  isFeedbackMandatory: false,
  enableCommentReactions: false,
  allowAnyoneToCreateTickets: false,
  defaultTicketType: "",
  preferKnowledgeBase: false,
  skipEmailWorkflow: false,
  disableSavedRepliesGlobalScope: false,
  enableOutsideHoursBanner: false,
  outsideWorkingHoursBannerMessage: "",
});
const disableSignup = ref(false);

provide(HDSettingsSymbol, settingsData);

const settingsDataResource = createResource({
  url: "frappe.client.get",
  params: {
    doctype: "HD Settings",
    name: "HD Settings",
  },
  auto: true,
  onSuccess(data: HDSettings) {
    settingsData.value = transformData(data);
    initialData.value = JSON.stringify(settingsData.value);
  },
});

const isWebsiteSettingsChanged = computed(() => {
  return (
    disableSignup.value !==
    Boolean(websiteSettingsResource.data?.disable_signup)
  );
});

const saveSettingsResource = createResource({
  url: "frappe.client.set_value",
  makeParams() {
    return {
      doctype: "HD Settings",
      name: "HD Settings",
      fieldname: {
        brand_name: settingsData.value.brandName,
        auto_close_after_days: Number(settingsData.value.autoCloseAfterDays),
        auto_close_status: settingsData.value.autoCloseStatus,
        auto_close_tickets: settingsData.value.autoCloseTickets,
        assign_within_team: settingsData.value.assignWithinTeam,
        do_not_restrict_tickets_without_an_agent_group:
          settingsData.value.doNotRestrictTicketsWithoutAnAgentGroup,
        restrict_tickets_by_agent_group:
          settingsData.value.restrictTicketsByAgentGroup,
        update_status_to: settingsData.value.updateStatusTo,
        auto_update_status: settingsData.value.autoUpdateStatus,
        is_feedback_mandatory: settingsData.value.isFeedbackMandatory,
        enable_comment_reactions: settingsData.value.enableCommentReactions,
        allow_anyone_to_create_tickets:
          settingsData.value.allowAnyoneToCreateTickets,
        default_ticket_type: settingsData.value.defaultTicketType,
        prefer_knowledge_base: settingsData.value.preferKnowledgeBase,
        skip_email_workflow: settingsData.value.skipEmailWorkflow,
        disable_saved_replies_global_scope:
          settingsData.value.disableSavedRepliesGlobalScope,
        enable_outside_hours_banner:
          settingsData.value.enableOutsideHoursBanner,
        outside_working_hours_message:
          settingsData.value.outsideWorkingHoursBannerMessage,
      },
    };
  },
  onSuccess(data: HDSettings) {
    settingsData.value = transformData(data);
    initialData.value = JSON.stringify(settingsData.value);
    configStore.configResource.reload();
  },
});

const transformData = (data: any) => {
  return {
    brandName: data.brand_name,
    brandLogo: data.brand_logo,
    favicon: data.favicon,
    autoCloseAfterDays: data.auto_close_after_days,
    autoCloseStatus: data.auto_close_status,
    autoCloseTickets: data.auto_close_tickets,
    assignWithinTeam: Boolean(data.assign_within_team),
    doNotRestrictTicketsWithoutAnAgentGroup: Boolean(
      data.do_not_restrict_tickets_without_an_agent_group
    ),
    restrictTicketsByAgentGroup: Boolean(data.restrict_tickets_by_agent_group),
    updateStatusTo: data.update_status_to,
    autoUpdateStatus: data.auto_update_status,
    isFeedbackMandatory: Boolean(data.is_feedback_mandatory),
    enableCommentReactions: Boolean(data.enable_comment_reactions),
    allowAnyoneToCreateTickets: Boolean(data.allow_anyone_to_create_tickets),
    defaultTicketType: data.default_ticket_type,
    preferKnowledgeBase: Boolean(data.prefer_knowledge_base),
    skipEmailWorkflow: Boolean(data.skip_email_workflow),
    disableSavedRepliesGlobalScope: Boolean(
      data.disable_saved_replies_global_scope
    ),
    enableOutsideHoursBanner: Boolean(data.enable_outside_hours_banner),
    outsideWorkingHoursBannerMessage: data.outside_working_hours_message || "",
  };
};

const websiteSettingsResource = createResource({
  url: "frappe.client.get",
  params: {
    doctype: "Website Settings",
    name: "Website Settings",
    fields: ["disable_signup"],
  },
  auto: true,
  onSuccess(data: any) {
    disableSignup.value = Boolean(data.disable_signup);
  },
});

const saveWebsiteSettingsResource = createResource({
  url: "frappe.client.set_value",
  makeParams() {
    return {
      doctype: "Website Settings",
      name: "Website Settings",
      fieldname: {
        disable_signup: disableSignup.value,
      },
    };
  },
  onSuccess() {
    websiteSettingsResource.reload();
  },
});

const saveSettings = async () => {
  if (
    settingsData.value.restrictTicketsByAgentGroup &&
    !settingsData.value.doNotRestrictTicketsWithoutAnAgentGroup &&
    !settingsData.value.assignWithinTeam
  ) {
    toast.error(
      __(
        "Please select at least one restriction option for teams in the settings."
      )
    );
    return;
  }
  const promises = [];
  if (isDirty.value) {
    promises.push(saveSettingsResource.submit());
  }
  if (isWebsiteSettingsChanged.value) {
    promises.push(saveWebsiteSettingsResource.submit());
  }
  await Promise.allSettled(promises).then(() => {
    toast.success(__("Settings updated"));
  });
};

const toggleFields = [
  "isFeedbackMandatory",
  "enableCommentReactions",
  "disableSavedRepliesGlobalScope",
  "allowAnyoneToCreateTickets",
  "preferKnowledgeBase",
  "skipEmailWorkflow",
] as const;

// Track dirty state for non-toggle fields only
watch(
  settingsData,
  (data) => {
    if (!initialData.value) return;
    const initial = JSON.parse(initialData.value);
    isDirty.value = Object.keys(data).some(
      (key) =>
        !(toggleFields as readonly string[]).includes(key) &&
        JSON.stringify(data[key as keyof typeof data]) !==
          JSON.stringify(initial[key])
    );
  },
  { deep: true }
);

// auto save when any toggle field changes
watch(
  () => toggleFields.map((f) => settingsData.value[f]),
  async (newVals) => {
    if (!initialData.value) return;
    const initial = JSON.parse(initialData.value);
    if (newVals.some((v, i) => v !== initial[toggleFields[i]])) {
      await saveSettingsResource.submit();
      toast.success(__("Settings updated"));
    }
  }
);

watch(disableSignup, async (newVal) => {
  if (!websiteSettingsResource.data) return;
  if (newVal !== Boolean(websiteSettingsResource.data.disable_signup)) {
    await saveWebsiteSettingsResource.submit();
    toast.success(__("Settings updated"));
  }
});
</script>

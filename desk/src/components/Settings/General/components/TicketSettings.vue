<template>
  <SettingsSection :title="__('Tickets')">
    <SettingRow
      v-slot="{ id }"
      :label="__('Make feedback mandatory')"
      :description="
        __(
          'The feedback dialog will be shown, when a user tries to close a ticket from the customer portal.'
        )
      "
    >
      <Switch :id="id" v-model="settingsData.isFeedbackMandatory" />
    </SettingRow>
    <SettingRow
      v-slot="{ id }"
      :label="__('Enable comment reactions')"
      :description="__('Allow users to react to comments with emojis.')"
    >
      <Switch :id="id" v-model="settingsData.enableCommentReactions" />
    </SettingRow>
    <div class="flex flex-col gap-3">
      <SettingRow
        v-slot="{ id }"
        :label="__('Restrict tickets by team')"
        :description="
          __('Restrict tickets to be viewed and managed by team members only.')
        "
      >
        <Switch :id="id" v-model="settingsData.restrictTicketsByAgentGroup" />
      </SettingRow>
      <div
        v-if="settingsData.restrictTicketsByAgentGroup"
        class="grid grid-cols-1 gap-3 sm:grid-cols-2"
      >
        <Checkbox
          size="sm"
          v-model="settingsData.doNotRestrictTicketsWithoutAnAgentGroup"
          :label="__('Do not restrict tickets without a team')"
        />
        <Checkbox
          size="sm"
          v-model="settingsData.assignWithinTeam"
          :label="__('Restrict agent assignment to selected team')"
        />
      </div>
    </div>
    <SettingRow
      v-if="settingsData.restrictTicketsByAgentGroup"
      v-slot="{ id }"
      :label="__('Disable global saved replies')"
      :description="
        __(
          'Agents will no longer be able to view and create saved replies with global scope.'
        )
      "
    >
      <Switch :id="id" v-model="settingsData.disableSavedRepliesGlobalScope" />
    </SettingRow>
    <SettingRow
      v-slot="{ id, labelledby }"
      :label="__('Auto update status')"
      :description="
        __(
          'The ticket status will automatically change whenever the agent respond to a ticket.'
        )
      "
    >
      <SelectDropdown
        :id="id"
        :labelledby="labelledby"
        :options="autoUpdateTicketStatusList"
        :model-value="settingsData.updateStatusTo"
        @update:model-value="
          (value) => {
            if (value) {
              settingsData.updateStatusTo = value;
              settingsData.autoUpdateStatus = true;
            } else {
              settingsData.updateStatusTo = null;
              settingsData.autoUpdateStatus = 0;
            }
          }
        "
        target-class="max-w-40"
        placement="bottom-start"
      />
    </SettingRow>
    <SettingRow
      v-slot="{ id }"
      :label="__('Allow anyone to create tickets')"
      :description="
        __(
          'Anyone will be able to create tickets without any permission. e.g. from webform.'
        )
      "
    >
      <Switch
        :id="id"
        :model-value="settingsData.allowAnyoneToCreateTickets"
        @update:model-value="
          (value) => (settingsData.allowAnyoneToCreateTickets = value)
        "
      />
    </SettingRow>
    <SettingRow
      v-slot="{ id, labelledby }"
      :label="__('Default ticket type')"
      :description="__('Select what type all tickets get by default.')"
    >
      <SelectDropdown
        :id="id"
        :labelledby="labelledby"
        :options="ticketTypeList.data"
        v-model="settingsData.defaultTicketType"
        target-class="max-w-40"
        placement="bottom-start"
      />
    </SettingRow>
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-1">
        <span class="text-base-medium text-ink-gray-8">{{
          __("Automatically close stale tickets")
        }}</span>
        <span class="text-p-sm text-ink-gray-6">{{
          __(
            "Auto-close tickets that remain in a status for the specified number of days."
          )
        }}</span>
      </div>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div class="flex flex-col gap-1.5">
          <FormLabel :label="__('Ticket status')" size="md" />
          <SelectDropdown
            :options="autoCloseTicketStatusList"
            :model-value="settingsData.autoCloseStatus"
            @update:model-value="
              (value) => {
                if (value) {
                  settingsData.autoCloseStatus = value;
                  settingsData.autoCloseTickets = true;
                } else {
                  settingsData.autoCloseStatus = null;
                  settingsData.autoCloseTickets = 0;
                }
              }
            "
            target-class="w-full"
            placement="bottom-start"
          />
        </div>
        <div class="flex flex-col gap-1.5">
          <FormControl
            :label="__('Auto-close after (Days)')"
            placeholder="e.g. 30"
            v-model="settingsData.autoCloseAfterDays"
            type="number"
            :debounce="300"
            :disabled="!settingsData.autoCloseStatus"
          />
          <ErrorMessage
            role="alert"
            :message="
              settingsData.autoCloseStatus &&
              settingsData.autoCloseAfterDays < 1
                ? __('The number of days must be 1 or more')
                : ''
            "
          />
        </div>
      </div>
    </div>
    <div class="flex flex-col gap-3">
      <SettingRow
        v-slot="{ id }"
        :label="__('Outside working hours notice')"
        :description="
          __(
            'Display a customizable banner message when customers raise tickets outside your working hours.'
          )
        "
      >
        <Switch
          :id="id"
          :model-value="settingsData.enableOutsideHoursBanner"
          @update:model-value="handleShowBannerToggle"
        />
      </SettingRow>
      <template v-if="settingsData.enableOutsideHoursBanner">
        <Textarea
          variant="subtle"
          size="sm"
          :aria-label="__('Notice message')"
          :placeholder="__('Enter Notification Message')"
          :required="true"
          v-model="settingsData.outsideWorkingHoursBannerMessage"
        />
        <div class="flex items-start justify-between gap-x-2">
          <p class="text-p-sm text-ink-gray-7">
            {{
              __(
                "Find out all of the variables that can be used in the content"
              )
            }}
            <a
              href="https://docs.frappe.io/helpdesk/helpdesk/customization/outside-working-hours-banner"
              target="_blank"
              rel="noopener noreferrer"
              class="font-semibold underline"
              >{{ __("here") }}</a
            >
          </p>
          <Button
            type="button"
            size="sm"
            variant="subtle"
            class="w-fit shrink-0"
            :disabled="!hasBannerMessageChanged"
            @click="resetBannerContent"
            :tooltip="
              hasBannerMessageChanged &&
              __('This will reset the content to the default message.')
            "
          >
            {{ __("Reset to default") }}
          </Button>
        </div>
      </template>
    </div>
  </SettingsSection>
</template>

<script setup lang="ts">
import SelectDropdown from "@/components/SelectDropdown.vue";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { HDSettingsSymbol } from "@/types";
import { HDTicketStatus } from "@/types/doctypes";
import {
  Checkbox,
  createListResource,
  createResource,
  ErrorMessage,
  FormControl,
  FormLabel,
  Switch,
  Textarea,
} from "frappe-ui";
import { computed, inject } from "vue";
import SettingRow from "../../SettingRow.vue";
import SettingsSection from "../../SettingsSection.vue";

const settingsData = inject(HDSettingsSymbol);

const { statuses } = useTicketStatusStore();

const bannerMsg = createResource({
  url: "helpdesk.helpdesk.doctype.hd_settings.helpers.get_banner_msg",
  auto: true,
});

const hasBannerMessageChanged = computed(() => {
  return (
    settingsData.value.outsideWorkingHoursBannerMessage !==
    bannerMsg.data?.default
  );
});

function resetBannerContent() {
  settingsData.value.outsideWorkingHoursBannerMessage = bannerMsg.data?.default;
}

function handleShowBannerToggle(value: boolean) {
  if (!bannerMsg.data.current) {
    if (value) {
      settingsData.value.outsideWorkingHoursBannerMessage =
        bannerMsg.data?.default;
    } else {
      settingsData.value.outsideWorkingHoursBannerMessage = "";
    }
  }
  settingsData.value.enableOutsideHoursBanner = value;
}

const ticketTypeList = createListResource({
  doctype: "HD Ticket Type",
  name: "HD Ticket Type",
  auto: true,
  transform: (data) => {
    return data.map((item) => {
      return {
        label: item.name,
        value: item.name,
      };
    });
  },
});

const autoUpdateTicketStatusList = computed(() => {
  return (
    statuses.data?.map((s: HDTicketStatus) => {
      return {
        label: s.label_agent,
        value: s.label_agent,
      };
    }) || []
  );
});

const autoCloseTicketStatusList = computed(() => {
  return (
    statuses.data
      ?.filter(
        (s: HDTicketStatus) =>
          s.category === "Resolved" || s.category === "Paused"
      )
      ?.map((s: HDTicketStatus) => {
        return {
          label: s.label_agent,
          value: s.label_agent,
        };
      }) || []
  );
});
</script>

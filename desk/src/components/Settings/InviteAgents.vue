<template>
  <SettingsLayoutBase
    :title="__('Invite Agents')"
    :description="
      __(
        'Send an invite by email. People join with the role you pick and can sign in once they accept.'
      )
    "
  >
    <template #content>
      <div>
        <SettingsSection :title="__('New invites')">
          <form @submit.prevent="onSubmit" class="flex flex-col gap-5">
            <FormControl
              type="textarea"
              :required="true"
              :label="__('Invite by email')"
              placeholder="user1@example.com, user2@example.com, ..."
              v-model="emails"
              :debounce="100"
              :description="__('Comma separated emails to invite.')"
            />
            <div class="space-y-1.5">
              <label
                :for="roleSelectId"
                class="block text-base text-ink-gray-6"
              >
                {{ __("Role") }}
                <span class="select-none text-danger" aria-hidden="true"
                  >*</span
                >
              </label>
              <Select
                :id="roleSelectId"
                :options="roleOptions"
                v-model="role"
                required
                class="w-full"
              >
                <template #suffix>
                  <LucideChevronDown
                    class="ml-auto size-4 shrink-0 text-ink-gray-4"
                    aria-hidden="true"
                  />
                </template>
              </Select>
              <p class="text-p-xs text-ink-gray-5">{{ roleDescription }}</p>
            </div>
            <Button
              type="submit"
              variant="solid"
              class="w-fit"
              :disabled="cancelInviteResource.loading"
              :loading="inviteByEmailResource.loading"
              :label="__('Send invites')"
            />
          </form>
        </SettingsSection>
        <SettingsSection
          v-if="pendingInvitesResource.data?.length"
          :title="__('Pending invites')"
          :description="__('Invites that haven\'t been accepted yet.')"
        >
          <SettingsList
            :items="pendingInvitesResource.data"
            :label="__('Pending invites')"
            :empty-icon="LucideMail"
            :empty-title="__('No pending invites')"
          >
            <template #default="{ item: invite }">
              <SettingsListItem
                :title="invite.email"
                :subtitle="rolesToLabel(invite.roles)"
              >
                <template #actions>
                  <Button
                    variant="ghost"
                    :tooltip="__('Cancel invitation')"
                    :label="__('Cancel invitation for {0}', invite.email)"
                    :disabled="
                      inviteByEmailResource.loading ||
                      (cancelInviteResource.loading &&
                        cancelInviteResource.params.name !== invite.name)
                    "
                    :loading="
                      cancelInviteResource.loading &&
                      invite.name === cancelInviteResource.params.name
                    "
                    @click="
                      cancelInviteResource.submit({
                        name: invite.name,
                        app_name: 'helpdesk',
                      })
                    "
                  >
                    <template #icon>
                      <LucideX class="size-4" aria-hidden="true" />
                    </template>
                  </Button>
                </template>
              </SettingsListItem>
            </template>
          </SettingsList>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { useAuthStore } from "@/stores/auth";
import { capture } from "@/telemetry";
import { __ } from "@/translation";
import { handleInviteUserSuccess } from "@/utils";
import { Button, FormControl, Select, createResource, toast } from "frappe-ui";
import { useOnboarding } from "frappe-ui/frappe";
import { computed, ref, useId } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideMail from "~icons/lucide/mail";
import LucideX from "~icons/lucide/x";
import SettingsList from "./SettingsList.vue";
import SettingsListItem from "./SettingsListItem.vue";
import SettingsSection from "./SettingsSection.vue";

const authStore = useAuthStore();
const { isAdmin, isManager } = authStore;

// @ts-expect-error
const { updateOnboardingStep } = useOnboarding("helpdesk");

const emails = ref("");
const roleSelectId = `invite-role-${useId()}`;

type Role = "Agent" | "Agent Manager" | "System Manager";
type RoleOption = {
  label: string;
  value: Role;
  description: string;
};

const roleToLabel = (role: Role) => {
  switch (role) {
    case "Agent":
      return "Agent";
    case "Agent Manager":
      return "Manager";
    case "System Manager":
      return "Admin";
    default:
      const x: never = role;
      throw new Error(`Invalid role: ${x}`);
  }
};

const roleOptions: [RoleOption, ...RoleOption[]] = [
  {
    label: roleToLabel("Agent"),
    value: "Agent",
    description: __(
      "Can work on tickets, create custom views and manage private views."
    ),
  },
];
const managerRoleOption: RoleOption = {
  label: roleToLabel("Agent Manager"),
  value: "Agent Manager",
  description: __(
    "Can invite new agents, manage tickets, create custom views and manage public views."
  ),
};
if (isAdmin) {
  roleOptions.push(managerRoleOption, {
    label: roleToLabel("System Manager"),
    value: "System Manager",
    description: __("Can manage all aspects of Helpdesk."),
  });
} else if (isManager) {
  roleOptions.push(managerRoleOption);
}
const role = ref(roleOptions[0].value);

const roleDescription = computed(
  () =>
    roleOptions.find((roleOption) => roleOption.value === role.value)!
      .description
);

const onSubmit = async () => {
  if (emails.value.trim() === "") {
    toast.error(__("Please enter at least one valid email to send an invite."));
    return;
  }
  await inviteByEmailResource.submit({
    emails: emails.value,
    roles: getInviteByEmailRoles(role.value),
    redirect_to_path: "/helpdesk",
    app_name: "helpdesk",
  });
  resetInputValues();
};

const resetInputValues = () => {
  emails.value = "";
  role.value = roleOptions[0].value;
};

const inviteByEmailResource = createResource({
  url: "frappe.core.api.user_invitation.invite_by_email",
  onSuccess(
    data: Record<
      | "disabled_user_emails"
      | "accepted_invite_emails"
      | "pending_invite_emails"
      | "invited_emails",
      string[]
    >
  ) {
    resetInputValues();
    handleInviteUserSuccess(data);
    pendingInvitesResource.reload();
    updateOnboardingStep("invite_your_team");
    capture("agents_invited", {
      data: {
        role: role.value,
      },
    });
  },
});

const pendingInvitesResource = createResource({
  url: "frappe.core.api.user_invitation.get_pending_invitations",
  params: {
    app_name: "helpdesk",
  },
  auto: true,
  method: "GET",
  transform: (data) =>
    data.filter((invite) =>
      invite.roles.some((role) =>
        ["Agent", "Agent Manager", "System Manager"].includes(role)
      )
    ),
});

const cancelInviteResource = createResource({
  url: "frappe.core.api.user_invitation.cancel_invitation",
  method: "PATCH",
  onSuccess() {
    toast.success(__("Invitation cancelled successfully"));
    pendingInvitesResource.fetch();
  },
});

const rolesToLabel = (roles: readonly Role[]) => {
  const rolesSt = new Set(roles);
  if (rolesSt.has("System Manager")) {
    return roleToLabel("System Manager");
  }
  if (rolesSt.has("Agent Manager")) {
    return roleToLabel("Agent Manager");
  }
  if (rolesSt.has("Agent")) {
    return roleToLabel("Agent");
  }
  throw new Error(`Invalid roles: ${roles.join(", ")}`);
};

const getInviteByEmailRoles = (selectedRole: Role) => {
  const res: Role[] = [];
  switch (selectedRole) {
    case "System Manager":
      res.push("Agent", "Agent Manager");
      break;
    case "Agent Manager":
      res.push("Agent");
      break;
    case "Agent":
      break;
    default:
      const x: never = selectedRole;
      throw new Error(`Invalid selected role: ${x}`);
  }
  res.push(selectedRole);
  return res;
};
</script>

<style scoped></style>

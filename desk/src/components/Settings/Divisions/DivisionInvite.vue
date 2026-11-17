<template>
  <SettingsLayoutBase
    :title="__('Invite Agents')"
    :description="
      __(
        'Bring people into your division. Someone who already works here joins it now; anyone else gets an email and joins when they accept.'
      )
    "
  >
    <template #content>
      <div>
        <SettingsSection :title="__('New invites')">
          <form class="flex flex-col gap-5" @submit.prevent="onSubmit">
            <FormControl
              v-if="divisions.length > 1"
              v-model="picked"
              type="select"
              :label="__('Division')"
              :options="
                divisions.map((d) => ({
                  label: d.division_name,
                  value: d.name,
                }))
              "
            />
            <FormControl
              v-model="emails"
              type="textarea"
              :required="true"
              :label="__('Invite by email')"
              placeholder="user1@example.com, user2@example.com, ..."
              :description="__('Comma separated emails to invite.')"
            />
            <FormControl
              v-model="role"
              type="select"
              :required="true"
              :label="__('Role in {0}', divisionName)"
              :options="roleOptions"
              :description="roleDescription"
            />
            <div
              v-if="problems.length"
              role="status"
              class="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-p-sm text-warning"
            >
              <LucideTriangleAlert
                class="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <ul class="list-disc pl-4">
                <li v-for="problem in problems" :key="problem">
                  {{ problem }}
                </li>
              </ul>
            </div>
            <Button
              type="submit"
              variant="solid"
              class="w-fit"
              :disabled="!picked || !role"
              :loading="sending"
              :label="__('Send invites')"
            />
          </form>
        </SettingsSection>
        <SettingsSection
          v-if="invites.length"
          :title="__('Pending invites')"
          :description="__('Invites that haven\'t been accepted yet.')"
        >
          <SettingsList
            :items="invites"
            :label="__('Pending invites')"
            :empty-icon="LucideMail"
            :empty-title="__('No pending invites')"
          >
            <template #default="{ item: invite }">
              <SettingsListItem
                :title="invite.email"
                :subtitle="__(invite.division_role)"
              >
                <template #actions>
                  <Button
                    variant="ghost"
                    :tooltip="__('Cancel invitation')"
                    :label="__('Cancel invitation for {0}', invite.email)"
                    :loading="cancelling === invite.name"
                    :disabled="!!cancelling"
                    @click="cancel(invite)"
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
import { DIVISIONS_API } from "@/pages/divisions/divisions";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, FormControl, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideMail from "~icons/lucide/mail";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSection from "../SettingsSection.vue";
import { type DivisionInvite, useDivisionAgents } from "./divisionAgents";

const DEFAULT_ROLE = "Division Sales User";
const ROLE_HELP: Record<string, string> = {
  "Division Admin": __(
    "Runs the division: every lead of it (a Sales Manager on its ERP site), its people and reports."
  ),
  "Division Sales User": __(
    "Sells in the division: their own leads only (a Sales User on its ERP site)."
  ),
};

const { divisions, picked, agents } = useDivisionAgents();
const emails = ref("");
const role = ref(DEFAULT_ROLE);
const sending = ref(false);
const cancelling = ref("");
const problems = ref<string[]>([]);

const divisionName = computed(
  () =>
    divisions.value.find((d) => d.name === picked.value)?.division_name ??
    picked.value
);
const invites = computed<DivisionInvite[]>(() => agents.data?.invites ?? []);
const roleOptions = computed(() =>
  (agents.data?.roles ?? [DEFAULT_ROLE]).map((r: string) => ({
    label: __(r),
    value: r,
  }))
);
const roleDescription = computed(
  () =>
    ROLE_HELP[role.value] ??
    __("Sees the division's records; what they do in it follows the role.")
);
watch(picked, () => (problems.value = []));

async function onSubmit() {
  if (!emails.value.trim()) {
    toast.error(__("Add at least one email."));
    return;
  }
  sending.value = true;
  problems.value = [];
  try {
    const r = await call(`${DIVISIONS_API}.invite_to_division`, {
      division: picked.value,
      emails: emails.value,
      role: role.value,
    });
    const done = r.added.length + r.invited.length;
    if (done) {
      toast.success(
        __(
          "{0} added, {1} invited",
          String(r.added.length),
          String(r.invited.length)
        )
      );
    }
    problems.value = [
      ...r.already_member.map((e: string) => __("{0} is already in it.", e)),
      ...r.already_invited.map((e: string) =>
        __("{0} already has an invite waiting.", e)
      ),
      ...r.disabled.map((e: string) =>
        __("{0}'s account is disabled. Ask a Super Admin.", e)
      ),
      ...r.erp_problems,
    ];
    if (done) emails.value = "";
    agents.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't send the invites.")));
  } finally {
    sending.value = false;
  }
}

async function cancel(invite: DivisionInvite) {
  cancelling.value = invite.name;
  try {
    await call(`${DIVISIONS_API}.cancel_division_invite`, {
      division: picked.value,
      name: invite.name,
    });
    toast.success(__("Invitation for {0} cancelled", invite.email));
    agents.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't cancel the invitation.")));
  } finally {
    cancelling.value = "";
  }
}
</script>

<template>
  <SettingsLayoutBase
    :title="teamName"
    :description="__('Members of this team, and who can be added to it.')"
    :back-label="__('Back to teams')"
    :loading="team.get.loading && !team.doc"
    :error="team.get.error"
    @retry="team.reload()"
    @back="() => emit('update:step', 'team-list')"
  >
    <template #header-actions>
      <Switch
        v-if="team.doc"
        size="sm"
        :label="__('Enabled')"
        v-model="teamEnabled"
      />
      <Dropdown placement="right" :options="options">
        <Button variant="ghost" :label="__('More actions for {0}', teamName)">
          <template #icon>
            <LucideEllipsis class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </Dropdown>
    </template>
    <template #header-bottom>
      <form class="flex gap-2" @submit.prevent="addMember(invitees)">
        <div class="flex min-w-0 flex-1">
          <AgentSelector
            v-model="invitees"
            :existing-agents="teamMembers.map((m) => m.name)"
          />
        </div>
        <Button
          type="submit"
          variant="solid"
          :label="__('Add members')"
          :disabled="!invitees.length"
          :loading="team.setValue.loading"
        >
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </form>
    </template>
    <template #content>
      <SettingsList
        :items="teamMembers"
        :label="__('Members of {0}', teamName)"
        :empty-icon="UserIcon"
        :empty-title="__('No members yet')"
        :empty-message="__('Add agents above to start routing tickets here.')"
      >
        <template #header>
          {{ __("Members ({0})", teamMembers.length) }}
        </template>
        <template #default="{ item: member }">
          <SettingsListItem :title="member.agent_name" :subtitle="member.name">
            <template #prefix>
              <Avatar
                :image="member.user_image"
                :label="member.agent_name"
                size="lg"
              />
            </template>
            <template v-if="teamMembers.length > 1" #actions>
              <Dropdown
                :options="memberDropdownOptions(member)"
                placement="right"
              >
                <Button
                  variant="ghost"
                  :label="__('More actions for {0}', member.agent_name)"
                  @click="isConfirmingDelete = false"
                >
                  <template #icon>
                    <LucideEllipsis class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </Dropdown>
            </template>
          </SettingsListItem>
        </template>
      </SettingsList>
    </template>
  </SettingsLayoutBase>
  <RenameTeamModal
    v-model="showRename"
    @onRename="
      () => {
        teamsList.reload();
        emit('update:step', 'team-list');
      }
    "
  />
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { useAgentStore } from "@/stores/agent";
import { assignmentRulesActiveScreen } from "@/stores/assignmentRules";
import { useConfigStore } from "@/stores/config";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { TeamListResourceSymbol } from "@/types";
import { ConfirmDelete } from "@/utils";
import {
  Avatar,
  Button,
  createDocumentResource,
  Dropdown,
  Switch,
  toast,
} from "frappe-ui";
import { computed, h, inject, markRaw, onMounted, ref } from "vue";
import RenameTeamModal from "./RenameTeamModal.vue";
import LucideLock from "~icons/lucide/lock";
import Settings from "~icons/lucide/settings-2";
import LucideUnlock from "~icons/lucide/unlock";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucidePlus from "~icons/lucide/plus";
import UserIcon from "~icons/lucide/user";
import { setActiveSettingsTab } from "../settingsModal";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import AgentSelector from "./components/AgentSelector.vue";

const props = defineProps<{
  teamName: string;
}>();

interface E {
  (event: "update:step", step: string, team?: string): void;
}
const emit = defineEmits<E>();

const { getUser } = useUserStore();
const { agents } = useAgentStore();
const teamsList = inject(TeamListResourceSymbol);

const { teamRestrictionApplied } = useConfigStore();
const invitees = ref<string[]>([]);

const team = createDocumentResource({
  doctype: "HD Team",
  name: props.teamName,
  auto: true,
  delete: {
    onSuccess() {
      toast.success(__("Team deleted successfully."));
      emit("update:step", "team-list");
    },
  },
});

const teamEnabled = computed({
  get() {
    return !team.doc?.disabled;
  },
  set(value: boolean) {
    if (!team.doc) return;
    team.doc.disabled = !value;
    team.setValue.submit(
      {
        disabled: !value,
      },
      {
        onSuccess: () => {
          toast.success(
            value
              ? __("Team enabled successfully.")
              : __("Team disabled successfully.")
          );
          team.reload();
        },
      }
    );
  },
});

const ignoreRestrictions = computed({
  get() {
    return !!team.doc?.ignore_restrictions;
  },
  set(value: boolean) {
    if (!team.doc) return;
    team.setValue.submit({
      ignore_restrictions: value,
    });
  },
});

const teamMembers = computed(() => {
  let users = team.doc?.users || [];
  return users.map((user) => {
    let _user = getUser(user.user);
    return {
      name: user.user,
      user_image: _user.user_image,
      agent_name: _user.full_name,
    };
  });
});

function removeMemberFromTeam(member: string) {
  const users = team.doc?.users?.filter((u) => u.user !== member);
  team.setValue.submit({
    users,
  });
}

function addMember(users: string[]) {
  const _users = team.doc.users.concat(users.map((user) => ({ user })));
  team.setValue.submit({
    users: _users,
  });
  invitees.value = [];
}

const showRename = ref({
  show: false,
  teamName: props.teamName,
});

const isConfirmingTeamDelete = ref(false);

const options = computed(() => [
  {
    label: __("View Assignment rule"),
    icon: markRaw(h(Settings, { class: "rotate-90" })),
    onClick: () => {
      assignmentRulesActiveScreen.value = {
        data: { name: team.doc?.assignment_rule },
        screen: "view",
      };
      setActiveSettingsTab("Assignment Rules");
    },
  },
  {
    label: __("Rename"),
    icon: "lucide-edit-3",
    onClick: () => {
      showRename.value = { show: true, teamName: props.teamName };
    },
  },
  ...(teamRestrictionApplied
    ? [
        {
          label: ignoreRestrictions.value
            ? __("Access only this team's tickets")
            : __("Access all team tickets"),
          icon: markRaw(ignoreRestrictions.value ? LucideLock : LucideUnlock),
          onClick: () => {
            ignoreRestrictions.value = !ignoreRestrictions.value;
            toast.success(
              ignoreRestrictions.value
                ? __("Team can now access all tickets.")
                : __("Team will only see their own tickets.")
            );
          },
        },
      ]
    : []),
  ...ConfirmDelete({
    isConfirmingDelete: isConfirmingTeamDelete,
    onConfirmDelete: () => team.delete.submit(),
  }),
]);

const isConfirmingDelete = ref(false);

const memberDropdownOptions = (member) => {
  return ConfirmDelete({
    onConfirmDelete: () => removeMemberFromTeam(member.name),
    isConfirmingDelete,
  });
};

onMounted(() => {
  if (agents.loading || agents.data?.length || agents.list.promise) {
    return;
  }
  agents.fetch();
});
</script>

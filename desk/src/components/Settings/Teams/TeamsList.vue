<template>
  <SettingsLayoutBase
    :title="__('Teams')"
    :description="
      __(
        'Group agents into teams; tickets and assignment rules can go to a team.'
      )
    "
  >
    <template #header-actions>
      <Button
        variant="solid"
        :label="__('New team')"
        @click="emit('update:step', 'new-team', '')"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template
      v-if="teams.data?.length > 9 || teamsSearchQuery.length"
      #header-bottom
    >
      <SettingsSearch
        v-model="teamsSearchQuery"
        :placeholder="__('Search teams')"
      />
    </template>
    <template #content>
      <SettingsList
        :items="teams.data"
        :label="__('Teams')"
        :loading="teams.list.loading"
        :error="teams.list.error"
        :filtered="Boolean(teamsSearchQuery)"
        :has-more="teams.hasNextPage"
        :empty-icon="AgentIcon"
        :empty-title="__('No teams yet')"
        :empty-message="
          __('Create a team to route tickets to a group of agents.')
        "
        @retry="teams.reload()"
        @more="teams.next()"
        @clear-filters="teamsSearchQuery = ''"
      >
        <template #default="{ item: team }">
          <SettingsListItem
            :title="team.name"
            :muted="Boolean(team.disabled)"
            @open="emit('update:step', 'team-edit', team.name)"
          >
            <template v-if="team.disabled" #badges>
              <TaskyBadge :label="__('Disabled')" />
            </template>
            <template #actions>
              <Dropdown placement="right" :options="dropdownOptions(team)">
                <Button
                  variant="ghost"
                  :label="__('More actions for {0}', team.name)"
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
  <RenameTeamModal v-model="showRename" @onRename="() => teams.reload()" />
</template>

<script setup lang="ts">
import AgentIcon from "@/components/icons/AgentIcon.vue";
import EditIcon from "@/components/icons/EditIcon.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { TeamListResourceSymbol } from "@/types";
import { ConfirmDelete } from "@/utils";
import { Button, Dropdown, toast } from "frappe-ui";
import { inject, markRaw, Ref, ref, watch } from "vue";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucidePlus from "~icons/lucide/plus";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSearch from "../SettingsSearch.vue";
import RenameTeamModal from "./RenameTeamModal.vue";

interface E {
  (event: "update:step", step: string, team: string): void;
}

const emit = defineEmits<E>();
const teamsSearchQuery = inject<Ref>("teamsSearchQuery");

const teams = inject(TeamListResourceSymbol)!;
const showRename = ref({
  show: false,
  teamName: "",
});
const isConfirmingDelete = ref(false);

const dropdownOptions = (team: any) => {
  return [
    {
      label: __("Rename"),
      icon: markRaw(EditIcon),
      onClick: () => {
        showRename.value = {
          show: true,
          teamName: team.name,
        };
      },
    },
    ...ConfirmDelete({
      onConfirmDelete: () => deleteTeam(team),
      isConfirmingDelete,
    }),
  ];
};

const deleteTeam = (team: any) => {
  if (!isConfirmingDelete.value) {
    isConfirmingDelete.value = true;
    return;
  }

  teams.delete.submit(team.name, {
    onSuccess: () => {
      toast.success(__("Team deleted successfully."));
    },
  });
};

watch(teamsSearchQuery, (newValue) => {
  teams.filters = {
    ...teams.filters,
    name: ["like", `%${newValue}%`],
  };
  teams.reload();
});
</script>

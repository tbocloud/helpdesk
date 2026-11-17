<template>
  <SettingsLayoutBase
    :title="__('Agents')"
    :description="
      __(
        'The people of your division and their role in it. Change a role in Divisions → People.'
      )
    "
  >
    <template #header-actions>
      <Button
        variant="solid"
        :label="__('Invite agents')"
        @click="setActiveSettingsTab('Invite Agents')"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template #header-bottom>
      <div class="flex flex-wrap items-center gap-2">
        <FormControl
          v-if="divisions.length > 1"
          v-model="picked"
          type="select"
          class="w-48"
          :aria-label="__('Division')"
          :options="
            divisions.map((d) => ({ label: d.division_name, value: d.name }))
          "
        />
        <SettingsSearch v-model="search" :placeholder="__('Search agents')" />
      </div>
    </template>
    <template #content>
      <SettingsList
        :items="shown"
        :label="__('Agents of the division')"
        row-key="user"
        :loading="agents.loading"
        :error="agents.error"
        :filtered="Boolean(search)"
        :empty-icon="AgentIcon"
        :empty-title="__('No one in this division yet')"
        :empty-message="__('Invite the people who work in it.')"
        @retry="agents.reload()"
        @clear-filters="search = ''"
      >
        <template #default="{ item: agent }">
          <SettingsListItem
            :title="agent.full_name"
            :subtitle="agent.user"
            :muted="!agent.is_active"
          >
            <template #prefix>
              <Avatar
                :image="agent.user_image"
                :label="agent.full_name"
                size="lg"
              />
            </template>
            <template #badges>
              <TaskyBadge v-if="!agent.is_active" :label="__('Inactive')" />
            </template>
            <template #actions>
              <span class="text-sm text-ink-gray-7">{{ __(agent.role) }}</span>
            </template>
          </SettingsListItem>
        </template>
      </SettingsList>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { Avatar, Button, FormControl } from "frappe-ui";
import { computed, ref } from "vue";
import LucidePlus from "~icons/lucide/plus";
import AgentIcon from "../../icons/AgentIcon.vue";
import { setActiveSettingsTab } from "../settingsModal";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSearch from "../SettingsSearch.vue";
import { type DivisionAgent, useDivisionAgents } from "./divisionAgents";

const { divisions, picked, agents } = useDivisionAgents();
const search = ref("");

const shown = computed(() => {
  const all: DivisionAgent[] = agents.data?.agents ?? [];
  const q = search.value.trim().toLowerCase();
  if (!q) return all;
  return all.filter(
    (a) =>
      a.full_name.toLowerCase().includes(q) || a.user.toLowerCase().includes(q)
  );
});
</script>

<template>
  <SettingsLayoutBase
    :title="__('Agents')"
    :description="
      __(
        'Everyone who works on tickets, and whether they are an agent or a manager.'
      )
    "
  >
    <template #header-actions>
      <Button
        variant="solid"
        :label="__('Invite agents')"
        @click="() => setActiveSettingsTab('Invite Agents')"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template #header-bottom>
      <div class="flex items-center gap-2">
        <SettingsSearch v-model="search" :placeholder="__('Search agents')" />
        <Dropdown :options="dropdownOptions" placement="right">
          <Button :aria-label="__('Show agents: {0}', __(activeFilter))">
            {{ __(activeFilter) }}
            <template #suffix>
              <LucideChevronDown class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
      </div>
    </template>
    <template #content>
      <SettingsList
        :items="agents.data"
        :label="__('Agents')"
        row-key="name"
        :loading="agents.list.loading"
        :error="agents.list.error"
        :filtered="Boolean(search) || activeFilter !== 'All'"
        :has-more="agents.hasNextPage"
        :empty-icon="AgentIcon"
        :empty-title="__('No agents yet')"
        :empty-message="__('Invite the people who will answer tickets.')"
        @retry="agents.reload()"
        @more="agents.next()"
        @clear-filters="clearFilters"
      >
        <template #default="{ item: agent }">
          <SettingsListItem
            :title="agent.agent_name"
            :subtitle="agent.name"
            :muted="!agent.is_active"
          >
            <template #prefix>
              <Avatar
                :image="agent.user_image"
                :label="agent.agent_name"
                size="lg"
              />
            </template>
            <template v-if="!agent.is_active" #badges>
              <TaskyBadge :label="__('Inactive')" />
            </template>
            <template #actions>
              <Dropdown
                v-if="isManager"
                :options="getRoles(agent.name)"
                placement="right"
              >
                <Button
                  :aria-label="
                    __(
                      'Role of {0}: {1}',
                      agent.agent_name,
                      getUserRole(agent.name)
                    )
                  "
                >
                  {{ __(getUserRole(agent.name)) }}
                  <template #suffix>
                    <LucideChevronDown class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </Dropdown>
              <Dropdown :options="getOptions(agent)" placement="right">
                <Button
                  variant="ghost"
                  :label="__('More actions for {0}', agent.agent_name)"
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
</template>

<script setup lang="ts">
import { useAuthStore } from "@/stores/auth";
import { useUserStore } from "@/stores/user";
import { Avatar, Button, call, Dropdown, toast } from "frappe-ui";
import { h, onUnmounted } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucidePlus from "~icons/lucide/plus";
import { activeFilter, useAgents } from "./agents";
import AgentIcon from "../icons/AgentIcon.vue";
import { setActiveSettingsTab } from "./settingsModal";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import SettingsList from "./SettingsList.vue";
import SettingsListItem from "./SettingsListItem.vue";
import SettingsSearch from "./SettingsSearch.vue";
import { __ } from "@/translation";
import { renderOptionIcon } from "@/utils";

const { getUserRole, updateUserRoleCache } = useUserStore();
const { isManager } = useAuthStore();

const agentStore = useAgents();
const search = agentStore.search;
const agents = agentStore.agents;

function getRoles(agent: string) {
  const agentRole = getUserRole(agent);
  const roles = [
    {
      label: "Agent",
      component: (props) =>
        RoleOption({
          role: "Agent",
          active: props.active,
          selected: agentRole === "Agent",
          icon: "lucide-user",
          onClick: () => {
            updateRole(agent, "Agent");
          },
        }),
    },
  ];
  if (isManager) {
    roles.unshift({
      label: "Manager",
      component: (props) =>
        RoleOption({
          role: "Manager",
          active: props.active,
          selected: agentRole === "Manager",
          icon: "lucide-briefcase",
          onClick: () => {
            updateRole(agent, "Manager");
          },
        }),
    });
  }

  return roles;
}

function RoleOption({ active, role, onClick, selected, icon = null }) {
  return h(
    "button",
    {
      class: [
        active ? "bg-surface-gray-2" : "text-ink-gray-7",

        "group flex w-full text-ink-gray-8 justify-between items-center rounded-md px-2 py-2 text-sm hover:bg-surface-gray-3",
      ],
      onClick: !selected ? onClick : null,
    },
    [
      h("div", { class: "flex gap-2" }, [
        renderOptionIcon(icon),
        h("span", { class: "whitespace-nowrap" }, role),
      ]),
      selected
        ? h(LucideCheck, {
            class: ["h-4 w-4 shrink-0 text-ink-gray-7"],
            "aria-hidden": true,
          })
        : null,
    ]
  );
}
function updateRole(agent: string, newRole: string) {
  const currentRole = getUserRole(agent);
  if (currentRole === newRole) {
    return;
  }

  call("helpdesk.helpdesk.doctype.hd_agent.hd_agent.update_agent_role", {
    user: agent,
    new_role: newRole,
  }).then(() => {
    updateUserRoleCache(agent, newRole);
    toast.success(__(`Role updated to ${newRole} successfully.`));
  });
}

function getOptions(agent) {
  let filters = agentStore.filters;
  return [
    {
      label: __("Deactivate agent"),
      icon: "lucide-x-circle",
      onClick: async () => {
        await agentStore.updateAgent(agent.name, 0);
        agents.reload({ ...filters, search: search.value });
      },
      condition: () => agent.is_active,
    },
    {
      label: __("Reactivate agent"),
      icon: "lucide-check-circle",
      onClick: async () => {
        await agentStore.updateAgent(agent.name, 1);
        agents.reload({ ...filters, search: search.value });
      },
      condition: () => !agent.is_active,
    },
  ];
}

const dropdownOptions = [
  {
    label: "All",
    onClick: () => {
      agentStore.filters["is_active"] = ["in", [0, 1]];
      activeFilter.value = "All";
    },
  },
  {
    label: "Active",
    onClick: () => {
      agentStore.filters["is_active"] = ["=", 1];
      activeFilter.value = "Active";
    },
  },
  {
    label: "Inactive",
    onClick: () => {
      agentStore.filters["is_active"] = ["=", 0];
      activeFilter.value = "Inactive";
    },
  },
];

function clearFilters() {
  search.value = "";
  dropdownOptions[0].onClick();
}

onUnmounted(() => {
  agents.filters = {};
});
</script>

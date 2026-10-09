<template>
  <SettingsLayoutBase
    :title="__('Agents')"
    :description="
      __(
        'Everyone who works here: agent or manager, and their department wall (ERP or Digital team), set from each agent\'s menu.'
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
            <template #badges>
              <TaskyBadge v-if="!agent.is_active" :label="__('Inactive')" />
              <TaskyBadge
                v-if="wallLabel(agent.name)"
                :label="wallLabel(agent.name)"
                :icon="LucideBrickWall"
              />
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
import { errorText } from "@/utils";
import {
  Avatar,
  Button,
  call,
  createResource,
  Dropdown,
  toast,
} from "frappe-ui";
import { h, onUnmounted, ref, watch } from "vue";
import LucideBrickWall from "~icons/lucide/brick-wall";
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
  const agentOptions = [
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
  if (!isManager) return agentOptions;
  return [
    { group: __("Agent"), hideLabel: true, options: agentOptions },
    { group: __("Department wall"), options: wallOptions(agent.name) },
  ];
}

// --- department walls (docs/departments.md): keep an agent out of the other team's work ---

const WALLS = [
  { role: "", label: __("No wall: every department") },
  { role: "ERP Employee", label: __("ERP team: no Digital or content") },
  { role: "DM Employee", label: __("Digital team: no ERP") },
];

const walls = createResource({
  url: "helpdesk.api.departments.get_department_walls",
  // shown in the menu instead, with Retry
  onError() {},
});
// the agent whose wall is being saved; their choices wait so saves can't cross
const savingWall = ref("");

function loadWalls() {
  const names = (agents.data ?? []).map((a) => a.name);
  if (isManager && names.length) walls.submit({ users: names });
}

watch(() => (agents.data ?? []).map((a) => a.name).join(","), loadWalls, {
  immediate: true,
});

function wallOptions(agent: string) {
  const current: string[] | undefined = walls.data?.[agent];
  if (!current && walls.error && !walls.loading) {
    return [
      {
        label: __("Couldn't load the walls. Retry"),
        icon: "lucide-refresh-cw",
        onClick: loadWalls,
      },
    ];
  }
  return WALLS.map((wall) => ({
    label: wall.label,
    // nothing is marked until the agent's roles have loaded
    selected:
      !!current &&
      (wall.role
        ? current.length === 1 && current[0] === wall.role
        : !current.length),
    disabled: !current || savingWall.value === agent,
    onClick: () => setWall(agent, wall.role),
  }));
}

function wallLabel(agent: string) {
  const roles: string[] = walls.data?.[agent] ?? [];
  if (roles.length > 1) return __("ERP and Digital walls");
  if (roles[0] === "ERP Employee") return __("ERP team");
  if (roles[0] === "DM Employee") return __("Digital team");
  return "";
}

function setWall(agent: string, role: string) {
  if (savingWall.value) return;
  savingWall.value = agent;
  call("helpdesk.api.departments.set_department_wall", { user: agent, role })
    .then((roles: string[]) => {
      walls.setData({ ...(walls.data ?? {}), [agent]: roles });
      toast.success(
        role
          ? __("{0} is now on the {1}", agent, wallLabel(agent))
          : __("{0} now sees every department", agent)
      );
    })
    .catch((e) =>
      toast.error(errorText(e, __("Couldn't change the department wall.")))
    )
    .finally(() => (savingWall.value = ""));
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

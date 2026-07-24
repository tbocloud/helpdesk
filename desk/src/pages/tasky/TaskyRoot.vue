<template>
  <div class="flex h-full">
    <aside
      class="flex w-[240px] shrink-0 flex-col border-r border-outline-gray-2 bg-surface-white"
    >
      <div class="flex h-12 items-center gap-2 border-b border-outline-gray-2 px-4">
        <span class="text-base font-semibold text-ink-gray-9">Tasky</span>
      </div>

      <nav class="flex flex-1 flex-col gap-0.5 overflow-auto p-2">
        <button
          v-for="item in navItems"
          :key="item.to"
          class="flex items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors"
          :class="
            item.isActive
              ? 'bg-surface-gray-3 text-ink-gray-9'
              : 'text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9'
          "
          @click="navigate(item.to)"
        >
          <component :is="item.icon" class="size-4 shrink-0" />
          <span>{{ item.label }}</span>
        </button>
      </nav>
    </aside>

    <main class="flex flex-1 flex-col overflow-auto">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { createResource } from "frappe-ui";

import LayoutDashboard from "~icons/lucide/layout-dashboard";
import FolderKanban from "~icons/lucide/folder-kanban";
import ListTodo from "~icons/lucide/list-todo";
import ClipboardList from "~icons/lucide/clipboard-list";
import GanttChartSquare from "~icons/lucide/gantt-chart-square";

const route = useRoute();
const router = useRouter();

const user = createResource({
  url: "helpdesk.api.auth.get_user",
  auto: true,
});

interface NavItem {
  label: string;
  icon: unknown;
  to: string;
  isActive: boolean;
}

const navItems = computed<NavItem[]>(() => {
  const items: NavItem[] = [
    {
      label: "Dashboard",
      icon: LayoutDashboard,
      to: "TaskyDashboard",
      isActive: route.name === "TaskyDashboard",
    },
    {
      label: "Projects",
      icon: FolderKanban,
      to: "TaskyProjects",
      isActive: route.name === "TaskyProjects",
    },
  ];

  if (user.data?.is_agent) {
    items.push({
      label: "My Tasks",
      icon: ListTodo,
      to: "TaskyMyTasks",
      isActive: route.name === "TaskyMyTasks",
    });
  }

  items.push(
    {
      label: "Checklist",
      icon: ClipboardList,
      to: "TaskyChecklist",
      isActive: route.name === "TaskyChecklist",
    },
    {
      label: "Kanban",
      icon: GanttChartSquare,
      to: "TaskyKanban",
      isActive: route.name === "TaskyKanban",
    }
  );

  return items;
});

function navigate(to: string) {
  if (route.name === to) return;
  router.push({ name: to });
}
</script>

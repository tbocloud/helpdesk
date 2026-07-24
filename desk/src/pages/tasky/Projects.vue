<template>
  <div class="flex flex-col h-full">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">
          {{ __("Projects") }}
        </div>
      </template>
      <template #right-header>
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm bg-surface-gray-3 text-ink-gray-8 hover:bg-surface-gray-4 transition-colors"
          @click="showNewForm = !showNewForm"
        >
          <Plus class="size-4" />
          <span>{{ __("New Project") }}</span>
        </button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto p-5">
      <div
        v-if="showNewForm"
        class="bg-surface-white border border-outline-gray-2 rounded-lg p-5 mb-6"
      >
        <div class="text-sm-medium text-ink-gray-8 mb-4">{{ __("New Project") }}</div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div class="flex flex-col gap-1">
            <label class="text-xs text-ink-gray-5">{{ __("Project Name") }}</label>
            <input
              v-model="newProject.project_name"
              class="border border-outline-gray-2 rounded px-3 py-1.5 text-sm text-ink-gray-9 bg-surface-white placeholder-ink-gray-4 focus:outline-none focus:border-outline-gray-3"
              placeholder="Enter project name"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs text-ink-gray-5">{{ __("Start Date") }}</label>
            <input
              v-model="newProject.start_date"
              type="date"
              class="border border-outline-gray-2 rounded px-3 py-1.5 text-sm text-ink-gray-9 bg-surface-white focus:outline-none focus:border-outline-gray-3"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs text-ink-gray-5">{{ __("Expected End Date") }}</label>
            <input
              v-model="newProject.expected_end_date"
              type="date"
              class="border border-outline-gray-2 rounded px-3 py-1.5 text-sm text-ink-gray-9 bg-surface-white focus:outline-none focus:border-outline-gray-3"
            />
          </div>
          <div class="flex flex-col gap-1 md:col-span-2">
            <label class="text-xs text-ink-gray-5">{{ __("Team Members") }}</label>
            <input
              v-model="newProject.team_members"
              class="border border-outline-gray-2 rounded px-3 py-1.5 text-sm text-ink-gray-9 bg-surface-white placeholder-ink-gray-4 focus:outline-none focus:border-outline-gray-3"
              placeholder="Enter team member emails (comma separated)"
            />
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="px-4 py-1.5 rounded text-sm bg-surface-gray-3 text-ink-gray-8 hover:bg-surface-gray-4 transition-colors disabled:opacity-50"
            :disabled="createProject.loading"
            @click="onCreateProject"
          >
            {{ createProject.loading ? __("Creating...") : __("Create") }}
          </button>
          <button
            class="px-4 py-1.5 rounded text-sm text-ink-gray-6 hover:text-ink-gray-8 transition-colors"
            @click="showNewForm = false"
          >
            {{ __("Cancel") }}
          </button>
        </div>
      </div>

      <div v-if="projects.loading" class="flex items-center justify-center h-64">
        <div class="text-p-base text-ink-gray-6">{{ __("Loading...") }}</div>
      </div>

      <div v-else-if="projects.error" class="flex items-center justify-center h-64">
        <div class="flex flex-col items-center gap-2">
          <AlertTriangle class="size-10 text-ink-gray-5" />
          <div class="text-p-base text-ink-gray-7">
            {{ __("Failed to load projects. Please try again.") }}
          </div>
        </div>
      </div>

      <div
        v-else-if="!projects.data?.length"
        class="flex items-center justify-center h-64"
      >
        <div class="flex flex-col items-center gap-2">
          <FolderKanban class="size-12 text-ink-gray-4" />
          <div class="text-lg-medium text-ink-gray-8">{{ __("No projects yet") }}</div>
          <div class="text-p-base text-ink-gray-6">
            {{ __("Create your first project to get started.") }}
          </div>
        </div>
      </div>

      <template v-else>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <div
            v-for="project in projects.data"
            :key="project.name"
            class="bg-surface-white border border-outline-gray-2 rounded-xl overflow-hidden hover:shadow-lg transition-all duration-200 group cursor-pointer"
            @click="navigateToProject(project.name)"
          >
            <div class="p-5">
              <div class="flex items-start justify-between mb-4">
                <div class="flex-1 min-w-0 mr-3">
                  <div class="text-base-semibold text-ink-gray-9 truncate mb-0.5">
                    {{ project.project_name }}
                  </div>
                  <div class="text-xs text-ink-gray-5">
                    {{ formatDateRange(project) }}
                  </div>
                </div>
                <span
                  class="text-xs font-medium px-2.5 py-1 rounded-full shrink-0"
                  :class="statusBadgeClass(project.status)"
                >
                  {{ project.status || "Open" }}
                </span>
              </div>

              <div class="mb-4" v-if="dashboards[project.name]?.data">
                <div class="flex items-center justify-between mb-1.5">
                  <span class="text-xs text-ink-gray-5 font-medium">Progress</span>
                  <span class="text-xs text-ink-gray-7 font-medium">
                    {{ dashboards[project.name].data.stats.completed }}/{{ dashboards[project.name].data.stats.total }} tasks
                  </span>
                </div>
                <div class="w-full h-2 rounded-full bg-surface-gray-2 overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all duration-700"
                    :class="progressColor(dashboards[project.name].data.stats.completion_pct)"
                    :style="{ width: dashboards[project.name].data.stats.completion_pct + '%' }"
                  />
                </div>
                <div class="flex items-center gap-3 mt-2 text-xs text-ink-gray-5">
                  <span class="flex items-center gap-1">
                    <span class="size-1.5 rounded-full bg-ink-green-5" />
                    {{ dashboards[project.name].data.stats.completed }} done
                  </span>
                  <span class="flex items-center gap-1">
                    <span class="size-1.5 rounded-full bg-ink-amber-5" />
                    {{ dashboards[project.name].data.stats.in_progress }} active
                  </span>
                  <span v-if="dashboards[project.name].data.stats.overdue" class="flex items-center gap-1">
                    <span class="size-1.5 rounded-full bg-ink-red-5" />
                    {{ dashboards[project.name].data.stats.overdue }} overdue
                  </span>
                </div>
              </div>

              <div class="flex flex-wrap gap-1.5 mb-3" v-if="dashboards[project.name]?.data?.phases?.length">
                <span
                  v-for="phase in dashboards[project.name].data.phases.slice(0, 4)"
                  :key="phase.name"
                  class="text-xs px-2 py-0.5 rounded-full bg-surface-gray-1 text-ink-gray-6 border border-outline-gray-2"
                >
                  {{ phase.phase_name }} {{ phase.completed_count }}/{{ phase.total_count }}
                </span>
                <span v-if="dashboards[project.name].data.phases.length > 4" class="text-xs text-ink-gray-4 py-0.5">
                  +{{ dashboards[project.name].data.phases.length - 4 }} more
                </span>
              </div>
            </div>

            <div class="flex border-t border-outline-gray-2 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
              <button
                class="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs text-ink-gray-6 hover:bg-surface-gray-1 transition-colors"
                @click.stop="navigateToProject(project.name)"
              >
                <FolderKanban class="size-3.5" /> Open
              </button>
              <button
                class="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs text-ink-gray-6 hover:bg-surface-gray-1 transition-colors border-x border-outline-gray-2"
                @click.stop="onGenerateChecklist(project)"
              >
                <ClipboardList class="size-3.5" /> Checklist
              </button>
              <button
                class="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs text-ink-gray-6 hover:bg-surface-gray-1 transition-colors"
                @click.stop="navigateToKanban(project.name)"
              >
                <Layout class="size-3.5" /> Board
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>
    <GenerateChecklistModal
      v-if="showChecklistModal"
      :show="showChecklistModal"
      :project-id="selectedProjectId"
      @close="showChecklistModal = false"
      @generated="showChecklistModal = false; projects.reload()"
    />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { createListResource, createResource } from "frappe-ui";
import { __ } from "@/translation";
import LayoutHeader from "@/components/LayoutHeader.vue";
import GenerateChecklistModal from "./components/GenerateChecklistModal.vue";
import Plus from "~icons/lucide/plus";
import FolderKanban from "~icons/lucide/folder-kanban";
import AlertTriangle from "~icons/lucide/alert-triangle";
import ClipboardList from "~icons/lucide/clipboard-list";
import Layout from "~icons/lucide/layout";

const router = useRouter();

interface Project {
  name: string;
  project_name?: string;
  title?: string;
  status?: string;
  expected_start_date?: string;
  expected_end_date?: string;
  priority?: string;
  start_date?: string;
}

const projects = createListResource({
  doctype: "Project",
  fields: ["name", "project_name", "status", "expected_start_date", "expected_end_date", "priority"],
  auto: true,
  transform: (data: Project[]) => data ?? [],
});

const createProject = createResource({
  url: "helpdesk.tasky.api.create_project",
  onSuccess() {
    showNewForm.value = false;
    resetForm();
    projects.reload();
  },
});


const showNewForm = ref(false);
const showChecklistModal = ref(false);
const selectedProjectId = ref("");

const newProject = reactive({
  project_name: "",
  start_date: "",
  expected_end_date: "",
  team_members: "",
});

function resetForm() {
  newProject.project_name = "";
  newProject.start_date = "";
  newProject.expected_end_date = "";
  newProject.team_members = "";
}

function onCreateProject() {
  if (!newProject.project_name.trim()) return;
  createProject.submit({
    project_name: newProject.project_name,
    expected_start_date: newProject.start_date,
    expected_end_date: newProject.expected_end_date,
    team_members: newProject.team_members
      ? newProject.team_members.split(",").map((s) => s.trim()).filter(Boolean)
      : [],
  });
}

function navigateToProject(projectName: string) {
  router.push({ name: "TaskyProject", params: { projectId: projectName } });
}

function navigateToKanban(projectName: string) {
  router.push({ name: "TaskyKanban", params: { projectId: projectName } });
}

const dashboards = reactive<Record<string, ReturnType<typeof createResource>>>({});

watch(
  () => projects.data,
  (list) => {
    list?.forEach((p) => {
      if (!dashboards[p.name]) {
        dashboards[p.name] = createResource({
          url: "helpdesk.tasky.api.get_project_dashboard",
          params: { project: p.name },
          auto: true,
        });
      }
    });
  },
  { immediate: true }
);

function formatDateRange(p: Project) {
  const parts = [];
  if (p.expected_start_date) parts.push(p.expected_start_date);
  if (p.expected_end_date) parts.push("→ " + p.expected_end_date);
  return parts.join(" ") || "No dates set";
}

function progressColor(pct: number) {
  if (pct >= 100) return "bg-ink-green-5";
  if (pct >= 60) return "bg-ink-blue-4";
  if (pct >= 30) return "bg-ink-amber-5";
  return "bg-ink-gray-4";
}

function statusBadgeClass(status: string) {
  const m: Record<string, string> = {
    Open: "bg-ink-blue-1 text-ink-blue-8",
    Completed: "bg-ink-green-1 text-ink-green-8",
    Cancelled: "bg-ink-red-1 text-ink-red-8",
  };
  return m[status] || "bg-ink-gray-2 text-ink-gray-7";
}

function onGenerateChecklist(project: Project) {
  selectedProjectId.value = project.name;
  showChecklistModal.value = true;
}
</script>

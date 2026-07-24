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
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="project in projects.data"
            :key="project.name"
            class="bg-surface-white border border-outline-gray-2 rounded-lg hover:shadow-md transition-shadow group"
          >
            <button
              class="w-full text-left p-5"
              @click="navigateToProject(project.name)"
            >
              <div class="flex items-center justify-between mb-3">
                <div class="flex-1 min-w-0">
                  <div class="text-sm-medium text-ink-gray-9 truncate">
                    {{ project.project_name || project.title }}
                  </div>
                </div>
                <span
                  class="text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ml-2"
                  :class="statusPillClass(project.status)"
                >
                  {{ __(project.status || "Active") }}
                </span>
              </div>

              <div class="mb-3">
                <div class="flex items-center justify-between mb-1">
                  <span class="text-xs text-ink-gray-5">{{ __("Progress") }}</span>
                  <span class="text-xs text-ink-gray-6">
                    {{ projectProgress(project.name) }}%
                  </span>
                </div>
                <div class="w-full h-2 rounded-full bg-surface-gray-2 overflow-hidden">
                  <div
                    class="h-full rounded-full bg-surface-gray-5 transition-all duration-500"
                    :style="{ width: projectProgress(project.name) + '%' }"
                  />
                </div>
              </div>

              <div class="flex items-center gap-4 text-xs text-ink-gray-5">
                <div v-if="project.expected_start_date" class="flex items-center gap-1">
                  <CalendarDays class="size-3.5" />
                  <span>{{ project.expected_start_date }}</span>
                </div>
                <div v-if="project.expected_end_date" class="flex items-center gap-1">
                  <Flag class="size-3.5" />
                  <span>{{ project.expected_end_date }}</span>
                </div>
              </div>
            </button>

            <div class="px-5 pb-4">
              <button
                class="w-full text-xs text-ink-gray-5 px-3 py-1.5 rounded border border-outline-gray-2 hover:bg-surface-gray-1 transition-colors"
                @click="onGenerateChecklist(project)"
              >
                <span class="flex items-center justify-center gap-1.5">
                  <ClipboardList class="size-3.5" />
                  {{ __("Generate Checklist") }}
                </span>
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
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { createListResource, createResource } from "frappe-ui";
import { __ } from "@/translation";
import LayoutHeader from "@/components/LayoutHeader.vue";
import GenerateChecklistModal from "./components/GenerateChecklistModal.vue";
import Plus from "~icons/lucide/plus";
import FolderKanban from "~icons/lucide/folder-kanban";
import AlertTriangle from "~icons/lucide/alert-triangle";
import CalendarDays from "~icons/lucide/calendar-days";
import Flag from "~icons/lucide/flag";
import ClipboardList from "~icons/lucide/clipboard-list";

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

const projectDashboards = reactive<Record<string, ReturnType<typeof createResource>>>({});

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

function ensureDashboard(projectName: string) {
  if (!projectDashboards[projectName]) {
    projectDashboards[projectName] = createResource({
      url: "helpdesk.tasky.api.get_project_dashboard",
      params: { project: projectName },
      auto: true,
    });
  }
  return projectDashboards[projectName];
}

const progressCache = reactive<Record<string, number>>({});

function projectProgress(projectName: string): number {
  if (progressCache[projectName] !== undefined) return progressCache[projectName];

  const resource = ensureDashboard(projectName);
  if (resource.data?.stats?.completion_pct != null) {
    progressCache[projectName] = resource.data.stats.completion_pct;
    return progressCache[projectName];
  }
  return 0;
}

function statusPillClass(status: string) {
  const lowered = status.toLowerCase();
  if (lowered === "completed") {
    return "bg-surface-gray-2 text-ink-gray-7";
  }
  if (lowered === "open") {
    return "bg-surface-gray-3 text-ink-gray-8";
  }
  if (lowered === "cancelled") {
    return "bg-surface-gray-4 text-ink-gray-9";
  }
  return "bg-surface-gray-1 text-ink-gray-6";
}

function onGenerateChecklist(project: Project) {
  selectedProjectId.value = project.name;
  showChecklistModal.value = true;
}
</script>

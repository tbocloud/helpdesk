<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Projects") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="projects.loading && !!projects.data"
          @click="reloadAll"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
        <Button
          v-if="authStore.isProjectManager"
          variant="solid"
          :label="__('New project')"
          @click="openNewProject"
        >
          <template #prefix
            ><LucidePlus class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="projects.error"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load projects')"
          :message="__('Check your connection and try again.')"
        >
          <Button :label="__('Retry')" @click="projects.reload()" />
        </TaskyState>

        <template v-else>
          <!-- Filters -->
          <div
            class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
          >
            <div
              class="-mx-1 flex gap-1 overflow-x-auto px-1"
              role="tablist"
              :aria-label="__('Filter projects by status')"
            >
              <button
                v-for="tab in statusTabs"
                :key="tab"
                type="button"
                role="tab"
                :aria-selected="activeStatus === tab"
                class="flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                :class="
                  activeStatus === tab
                    ? 'bg-surface-gray-3 text-ink-gray-9'
                    : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8'
                "
                @click="activeStatus = tab"
              >
                {{ __(tab) }}
                <span
                  class="rounded px-1 font-mono text-xs tabular-nums"
                  :class="
                    activeStatus === tab
                      ? 'bg-surface-base text-ink-gray-8'
                      : 'text-ink-gray-5'
                  "
                >
                  {{ countFor(tab) }}
                </span>
              </button>
            </div>
            <TextInput
              v-model="search"
              type="search"
              class="w-full md:w-64"
              :placeholder="__('Search projects or customers')"
              :aria-label="__('Search projects')"
            >
              <template #prefix>
                <LucideSearch
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
              </template>
            </TextInput>
          </div>

          <!-- Loading -->
          <div
            v-if="projects.loading && !projects.data"
            class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
            aria-busy="true"
          >
            <div
              v-for="i in 6"
              :key="i"
              class="flex flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-4 shadow-sm"
            >
              <div class="h-5 w-16 animate-pulse rounded bg-surface-gray-2" />
              <div class="h-4 w-3/5 animate-pulse rounded bg-surface-gray-2" />
              <div class="h-3 w-2/5 animate-pulse rounded bg-surface-gray-2" />
              <div
                class="h-1.5 w-full animate-pulse rounded-full bg-surface-gray-2"
              />
            </div>
          </div>

          <!-- Empty -->
          <div
            v-else-if="!visibleProjects.length"
            class="mt-4 rounded-xl border border-outline-gray-2 bg-surface-base"
          >
            <TaskyState
              v-if="!allProjects.length"
              :icon="LucideFolderKanban"
              :title="__('No projects yet')"
              :message="
                authStore.isProjectManager
                  ? __(
                      'Create a project to start planning tasks with your team.'
                    )
                  : __('Projects you are added to will show up here.')
              "
            >
              <Button
                v-if="authStore.isProjectManager"
                variant="solid"
                :label="__('New project')"
                @click="openNewProject"
              >
                <template #prefix
                  ><LucidePlus class="size-4" aria-hidden="true"
                /></template>
              </Button>
            </TaskyState>
            <TaskyState
              v-else
              :icon="LucideSearchX"
              :title="__('No matching projects')"
              :message="__('Try a different search, or clear the filters.')"
            >
              <Button :label="__('Show all projects')" @click="resetFilters" />
            </TaskyState>
          </div>

          <!-- Cards -->
          <ul
            v-else
            role="list"
            class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
          >
            <li
              v-for="project in visibleProjects"
              :key="project.name"
              class="flex flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base shadow-sm transition-colors hover:border-outline-gray-3"
            >
              <div class="flex flex-1 flex-col gap-3 p-4">
                <div class="flex items-center justify-between gap-2">
                  <TaskStatusBadge kind="project" :status="project.status" />
                  <span class="truncate font-mono text-xs text-ink-gray-5">{{
                    project.name
                  }}</span>
                </div>

                <div class="min-w-0">
                  <router-link
                    :to="{
                      name: 'TaskyProject',
                      params: { projectId: project.name },
                    }"
                    class="block truncate rounded text-base-semibold text-ink-gray-9 hover:underline"
                  >
                    {{ project.project_name || project.name }}
                  </router-link>
                  <div
                    class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-gray-6"
                  >
                    <span
                      v-if="project.customer"
                      class="flex min-w-0 items-center gap-1"
                    >
                      <LucideBuilding2
                        class="size-3.5 shrink-0"
                        aria-hidden="true"
                      />
                      <span class="truncate">{{ project.customer }}</span>
                    </span>
                    <span class="flex items-center gap-1 tabular-nums">
                      <LucideCalendar
                        class="size-3.5 shrink-0"
                        aria-hidden="true"
                      />
                      {{ formatDateRange(project) }}
                    </span>
                  </div>
                </div>

                <!-- Progress -->
                <div
                  v-if="
                    dashboards[project.name]?.loading &&
                    !dashboards[project.name]?.data
                  "
                  class="flex flex-col gap-2"
                >
                  <div
                    class="h-3 w-1/3 animate-pulse rounded bg-surface-gray-2"
                  />
                  <div
                    class="h-1.5 w-full animate-pulse rounded-full bg-surface-gray-2"
                  />
                </div>
                <div v-else-if="statsFor(project)" class="flex flex-col gap-2">
                  <div class="flex items-center justify-between text-xs">
                    <span class="text-ink-gray-5">{{ __("Progress") }}</span>
                    <span class="font-mono tabular-nums text-ink-gray-7">
                      {{ statsFor(project).completed }}/{{
                        statsFor(project).total
                      }}
                      <span class="text-ink-gray-5"
                        >· {{ statsFor(project).completion_pct }}%</span
                      >
                    </span>
                  </div>
                  <div
                    class="flex h-1.5 w-full overflow-hidden rounded-full bg-surface-gray-2"
                    role="img"
                    :aria-label="progressLabel(project)"
                  >
                    <div
                      v-for="seg in segments(project)"
                      :key="seg.key"
                      class="h-full"
                      :class="seg.bar"
                      :style="{ width: seg.pct + '%' }"
                    />
                  </div>
                  <div
                    class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-6"
                  >
                    <span
                      v-for="seg in legend(project)"
                      :key="seg.key"
                      class="flex items-center gap-1.5 tabular-nums"
                    >
                      <span
                        class="size-2 rounded-full"
                        :class="seg.bar"
                        aria-hidden="true"
                      />
                      {{ seg.count }} {{ seg.label }}
                    </span>
                    <span
                      v-if="statsFor(project).overdue"
                      class="flex items-center gap-1 font-medium text-danger tabular-nums"
                    >
                      <LucideAlarmClock class="size-3.5" aria-hidden="true" />
                      {{ statsFor(project).overdue }} {{ __("overdue") }}
                    </span>
                  </div>
                </div>

                <!-- Phases -->
                <div v-if="phasesFor(project).length">
                  <button
                    type="button"
                    class="flex items-center gap-1 rounded text-xs text-ink-gray-6 hover:text-ink-gray-8"
                    :aria-expanded="expandedCards.has(project.name)"
                    :aria-controls="`phases-${project.name}`"
                    @click="toggleExpand(project.name)"
                  >
                    <component
                      :is="
                        expandedCards.has(project.name)
                          ? LucideChevronDown
                          : LucideChevronRight
                      "
                      class="size-3.5"
                      aria-hidden="true"
                    />
                    {{ __("Phases") }}
                    <span class="font-mono tabular-nums text-ink-gray-5">{{
                      phasesFor(project).length
                    }}</span>
                  </button>
                  <div
                    v-if="expandedCards.has(project.name)"
                    :id="`phases-${project.name}`"
                    class="mt-2 flex flex-wrap gap-1.5"
                  >
                    <span
                      v-for="phase in phasesFor(project)"
                      :key="phase.name"
                      class="inline-flex items-center gap-1.5 rounded-md bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
                    >
                      {{ phase.phase_name }}
                      <span class="font-mono tabular-nums text-ink-gray-5">
                        {{ phase.completed_count }}/{{ phase.total_count }}
                      </span>
                    </span>
                  </div>
                </div>
              </div>

              <div
                class="flex flex-wrap items-center gap-1 border-t border-outline-gray-2 bg-surface-gray-1 px-2 py-1.5"
              >
                <Button
                  variant="ghost"
                  :label="__('Open')"
                  @click="navigateToProject(project.name)"
                >
                  <template #prefix
                    ><LucideLayoutDashboard class="size-4" aria-hidden="true"
                  /></template>
                </Button>
                <Button
                  variant="ghost"
                  :label="__('Board')"
                  @click="navigateToKanban(project.name)"
                >
                  <template #prefix
                    ><LucideKanban class="size-4" aria-hidden="true"
                  /></template>
                </Button>
                <template v-if="project.can_manage">
                  <Button
                    variant="ghost"
                    class="ml-auto"
                    :label="__('Checklist')"
                    @click="onGenerateChecklist(project)"
                  >
                    <template #prefix
                      ><LucideClipboardList class="size-4" aria-hidden="true"
                    /></template>
                  </Button>
                  <Button
                    :label="__('New task')"
                    @click="openNewTask(project.name)"
                  >
                    <template #prefix
                      ><LucidePlus class="size-4" aria-hidden="true"
                    /></template>
                  </Button>
                </template>
              </div>
            </li>
          </ul>
        </template>
      </div>
    </div>

    <!-- New project -->
    <Dialog v-model:open="showNewForm" :title="__('New project')" size="xl">
      <form
        id="tasky-new-project"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="onCreateProject"
      >
        <TextInput
          v-model="newProject.project_name"
          :label="__('Project name')"
          :placeholder="__('e.g. Acme ERP rollout')"
          required
        />
        <Link
          v-model="newProject.customer"
          doctype="HD Customer"
          :label="__('Customer')"
          :placeholder="__('Select customer')"
        />
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextInput
            v-model="newProject.start_date"
            type="date"
            :label="__('Start date')"
          />
          <TextInput
            v-model="newProject.expected_end_date"
            type="date"
            :label="__('Expected end date')"
          />
        </div>

        <fieldset class="flex flex-col gap-2">
          <legend class="mb-1.5 text-base text-ink-gray-5">
            {{ __("Team members") }}
          </legend>
          <p
            v-if="!newProject.members.length"
            class="text-p-xs text-ink-gray-5"
          >
            {{
              __(
                "Add the people who will work on this project so tasks can be assigned to them."
              )
            }}
          </p>
          <div
            v-for="(member, idx) in newProject.members"
            :key="idx"
            class="flex items-center gap-2"
          >
            <FormControl
              v-model="member.user"
              type="select"
              class="min-w-0 flex-1"
              :placeholder="__('Select user…')"
              :options="userOptions"
              :aria-label="__('Member {0}', String(idx + 1))"
            />
            <FormControl
              v-model="member.custom_role"
              type="select"
              class="!w-48 shrink-0"
              :options="roleOptions"
              :aria-label="__('Role for member {0}', String(idx + 1))"
            />
            <Button
              variant="ghost"
              :label="__('Remove member')"
              @click="newProject.members.splice(idx, 1)"
            >
              <template #icon><LucideX class="size-4" /></template>
            </Button>
          </div>
          <div>
            <Button
              variant="subtle"
              :label="__('Add member')"
              @click="newProject.members.push({ user: '', custom_role: '' })"
            >
              <template #prefix
                ><LucideUserPlus class="size-4" aria-hidden="true"
              /></template>
            </Button>
          </div>
        </fieldset>

        <div
          v-if="createProject.error"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          {{ errorText(createProject.error) }}
        </div>
      </form>

      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            form="tasky-new-project"
            :label="__('Create project')"
            :loading="createProject.loading"
            :disabled="!newProject.project_name.trim()"
          />
        </div>
      </template>
    </Dialog>

    <GenerateChecklistModal
      v-if="showChecklistModal"
      :show="showChecklistModal"
      :project-id="selectedProjectId"
      @close="showChecklistModal = false"
      @generated="onChecklistGenerated"
      @add-task="onChecklistAddTask"
    />

    <NewTaskDialog
      v-if="newTaskProject"
      v-model:open="showNewTask"
      :project-id="newTaskProject"
      :phases="phasesFor({ name: newTaskProject }).map((p) => p.phase_name)"
      @created="dashboards[newTaskProject]?.reload()"
    />
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  FormControl,
  TextInput,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCalendar from "~icons/lucide/calendar";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import LucideKanban from "~icons/lucide/square-kanban";
import LucideUserPlus from "~icons/lucide/user-plus";
import LucideX from "~icons/lucide/x";
import GenerateChecklistModal from "./components/GenerateChecklistModal.vue";
import NewTaskDialog from "./components/NewTaskDialog.vue";
import TaskStatusBadge from "./components/TaskStatusBadge.vue";
import TaskyState from "./components/TaskyState.vue";

const router = useRouter();
const authStore = useAuthStore();

interface Project {
  name: string;
  project_name?: string;
  status?: string;
  expected_start_date?: string;
  expected_end_date?: string;
  priority?: string;
  customer?: string;
  can_manage?: boolean;
}

interface Phase {
  name: string;
  phase_name: string;
  completed_count: number;
  total_count: number;
}

type StatusTab = "All" | "Open" | "Completed" | "Cancelled";

const projects = createResource({
  url: "helpdesk.tasky.api.get_projects",
  auto: true,
  transform: (d: Project[]) => d ?? [],
});

const userList = createResource({
  url: "helpdesk.tasky.api.get_users",
  auto: true,
  transform: (d: any[]) => d ?? [],
});

const userOptions = computed(() =>
  (userList.data ?? []).map((u: any) => ({
    label: u.full_name || u.name,
    value: u.name,
  }))
);

const roleOptions = computed(() => [
  { label: __("Manager (no role)"), value: "" },
  { label: __("Functional Consultant"), value: "Functional Consultant" },
  { label: __("Developer"), value: "Developer" },
  { label: __("Support Engineer"), value: "Support Engineer" },
]);

const createProject = createResource({
  url: "helpdesk.tasky.api.create_project",
  onSuccess() {
    toast.success(__("Project created"));
    showNewForm.value = false;
    resetForm();
    projects.reload();
  },
  // shown inline in the dialog
  onError() {},
});

const allProjects = computed<Project[]>(() => projects.data ?? []);

// --- filters ---

const statusTabs: StatusTab[] = ["All", "Open", "Completed", "Cancelled"];
const activeStatus = ref<StatusTab>("All");
const search = ref("");

function matchesStatus(p: Project, tab: StatusTab) {
  return tab === "All" || (p.status || "Open") === tab;
}

function countFor(tab: StatusTab) {
  return allProjects.value.filter((p) => matchesStatus(p, tab)).length;
}

const visibleProjects = computed(() => {
  const q = search.value.trim().toLowerCase();
  return allProjects.value.filter(
    (p) =>
      matchesStatus(p, activeStatus.value) &&
      (!q ||
        (p.project_name || "").toLowerCase().includes(q) ||
        p.name.toLowerCase().includes(q) ||
        (p.customer || "").toLowerCase().includes(q))
  );
});

function resetFilters() {
  activeStatus.value = "All";
  search.value = "";
}

// --- per-project dashboard stats ---

const dashboards = reactive<Record<string, ReturnType<typeof createResource>>>(
  {}
);

watch(
  () => projects.data,
  (list: Project[] | null) => {
    list?.forEach((p) => {
      if (!dashboards[p.name]) {
        dashboards[p.name] = createResource({
          url: "helpdesk.tasky.api.get_project_dashboard",
          params: { project: p.name },
          auto: true,
          // a card without stats is still usable; don't toast once per project
          onError() {},
        });
      }
    });
  },
  { immediate: true }
);

function reloadAll() {
  projects.reload();
  Object.values(dashboards).forEach((d) => d.reload());
}

function statsFor(project: Project) {
  return dashboards[project.name]?.data?.stats;
}

function phasesFor(project: Pick<Project, "name">): Phase[] {
  return dashboards[project.name]?.data?.phases ?? [];
}

function segments(project: Project) {
  const s = statsFor(project);
  const total = s?.total || 1;
  return [
    {
      key: "done",
      pct: ((s?.completed || 0) / total) * 100,
      bar: "bg-success",
    },
    {
      key: "active",
      pct: ((s?.in_progress || 0) / total) * 100,
      bar: "bg-info",
    },
    {
      key: "review",
      pct: ((s?.reviewing || 0) / total) * 100,
      bar: "bg-warning",
    },
    {
      key: "cancelled",
      pct: ((s?.cancelled || 0) / total) * 100,
      bar: "bg-surface-gray-5",
    },
  ].filter((seg) => seg.pct > 0);
}

function legend(project: Project) {
  const s = statsFor(project);
  return [
    {
      key: "done",
      count: s?.completed || 0,
      label: __("done"),
      bar: "bg-success",
    },
    {
      key: "active",
      count: s?.in_progress || 0,
      label: __("in progress"),
      bar: "bg-info",
    },
    {
      key: "review",
      count: s?.reviewing || 0,
      label: __("in review"),
      bar: "bg-warning",
    },
  ].filter((seg) => seg.count > 0);
}

function progressLabel(project: Project) {
  const s = statsFor(project);
  return __(
    "{0} of {1} tasks completed",
    String(s?.completed || 0),
    String(s?.total || 0)
  );
}

function formatDateRange(p: Project) {
  const fmt = (d: string) => dayjs(d).format("D MMM YYYY");
  if (p.expected_start_date && p.expected_end_date) {
    return `${fmt(p.expected_start_date)} – ${fmt(p.expected_end_date)}`;
  }
  if (p.expected_start_date) return __("From {0}", fmt(p.expected_start_date));
  if (p.expected_end_date) return __("Due {0}", fmt(p.expected_end_date));
  return __("No dates set");
}

// --- card toggles & navigation ---

const expandedCards = reactive<Set<string>>(new Set());

function toggleExpand(name: string) {
  if (expandedCards.has(name)) expandedCards.delete(name);
  else expandedCards.add(name);
}

function navigateToProject(projectName: string) {
  router.push({ name: "TaskyProject", params: { projectId: projectName } });
}

function navigateToKanban(projectName: string) {
  router.push({ name: "TaskyKanban", params: { projectId: projectName } });
}

// --- new project ---

const showNewForm = ref(false);

const newProject = reactive({
  project_name: "",
  start_date: "",
  expected_end_date: "",
  customer: "",
  members: [] as { user: string; custom_role: string }[],
});

function resetForm() {
  newProject.project_name = "";
  newProject.start_date = "";
  newProject.expected_end_date = "";
  newProject.customer = "";
  newProject.members = [];
}

function openNewProject() {
  createProject.reset();
  showNewForm.value = true;
}

function onCreateProject() {
  if (!newProject.project_name.trim() || createProject.loading) return;
  createProject.submit({
    project_name: newProject.project_name.trim(),
    expected_start_date: newProject.start_date,
    expected_end_date: newProject.expected_end_date,
    customer: newProject.customer,
    members: JSON.stringify(newProject.members.filter((m) => m.user.trim())),
  });
}

function errorText(err: { messages?: string[]; message?: string }) {
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || __("Something went wrong.");
}

// --- checklist & new task ---

const showChecklistModal = ref(false);
const selectedProjectId = ref("");
const showNewTask = ref(false);
const newTaskProject = ref("");

function onGenerateChecklist(project: Project) {
  selectedProjectId.value = project.name;
  showChecklistModal.value = true;
}

function onChecklistGenerated() {
  showChecklistModal.value = false;
  projects.reload();
  dashboards[selectedProjectId.value]?.reload();
}

function onChecklistAddTask() {
  showChecklistModal.value = false;
  openNewTask(selectedProjectId.value);
}

function openNewTask(projectName: string) {
  newTaskProject.value = projectName;
  showNewTask.value = true;
}
</script>

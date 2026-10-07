<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Projects") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :aria-label="__('Refresh')"
          :loading="projects.loading && !!projects.data"
          @click="reloadAll"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="authStore.isProjectManager"
          variant="solid"
          :label="__('New project')"
          @click="showNewForm = true"
        >
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "Every project you're on, by department. Open one to plan its tasks, or go straight to its board."
            )
          }}
        </p>

        <TaskyState
          v-if="projects.error && !projects.data"
          class="mt-6"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load projects')"
          :message="__('Check your connection and try again.')"
        >
          <Button :label="__('Retry')" @click="projects.reload()" />
        </TaskyState>

        <template v-else>
          <!-- Summary: the two that count work narrow the cards to what they count -->
          <div
            class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3"
            role="group"
            :aria-label="__('Project summary')"
          >
            <StatTile
              :label="__('Open projects')"
              :value="openInScope.length"
              :icon="LucideFolderOpen"
              :loading="isLoading"
            />
            <StatTile
              :label="__('Overdue tasks')"
              :value="overdueTotal"
              :sub="overdueSub"
              :icon="LucideAlarmClock"
              :icon-tone="overdueTotal ? 'danger' : 'neutral'"
              :value-tone="overdueTotal ? 'danger' : 'neutral'"
              :loading="isLoading || statsLoading"
              :pressed="show === 'overdue'"
              :aria-controls="listId"
              @click="toggleShow('overdue')"
            />
            <StatTile
              :label="__('Ending in 14 days')"
              :value="endingSoon.length"
              :sub="pastEnd.length ? pastEndSub : undefined"
              :icon="LucideCalendarClock"
              :loading="isLoading"
              :pressed="show === 'ending'"
              :aria-controls="listId"
              @click="toggleShow('ending')"
            />
          </div>

          <!-- Filters -->
          <div
            class="mt-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
          >
            <div
              class="-mx-1 flex min-w-0 gap-1 overflow-x-auto px-1"
              role="tablist"
              :aria-label="__('Filter projects by status')"
            >
              <button
                v-for="tab in STATUS_TABS"
                :key="tab"
                type="button"
                role="tab"
                :aria-selected="activeStatus === tab"
                :aria-controls="listId"
                class="flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                :class="
                  activeStatus === tab
                    ? 'bg-surface-gray-3 text-ink-gray-9'
                    : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8'
                "
                @click="setStatus(tab)"
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

          <div
            v-if="departmentChips.length"
            class="-mx-1 mt-3 flex gap-1.5 overflow-x-auto px-1 pb-1"
            role="group"
            :aria-label="__('Filter projects by department')"
          >
            <button
              v-for="chip in departmentChips"
              :key="chip.key"
              type="button"
              :aria-pressed="activeDepartment === chip.key"
              class="flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :class="
                activeDepartment === chip.key
                  ? 'border-outline-gray-4 bg-surface-gray-3 text-ink-gray-9'
                  : 'border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8'
              "
              @click="activeDepartment = chip.key"
            >
              {{ chip.label }}
              <span class="font-mono text-xs tabular-nums text-ink-gray-5">
                {{ departmentCount(chip.key) }}
              </span>
            </button>
          </div>

          <div
            v-if="showTile"
            class="mt-3 flex flex-wrap items-center gap-2 text-sm text-ink-gray-6"
            role="status"
          >
            {{ showTile }}
            <Button
              variant="ghost"
              size="sm"
              :label="__('Show all')"
              @click="toggleShow(show)"
            >
              <template #prefix>
                <LucideX class="size-3.5" aria-hidden="true" />
              </template>
            </Button>
          </div>

          <div :id="listId" :aria-busy="listLoading">
            <!-- Loading -->
            <div
              v-if="listLoading"
              class="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
              :aria-label="__('Loading')"
            >
              <div
                v-for="i in 6"
                :key="i"
                class="flex flex-col gap-4 rounded-lg border border-outline-gray-2 bg-surface-base p-4"
              >
                <div
                  class="h-4 w-3/5 animate-pulse rounded bg-surface-gray-2"
                />
                <div
                  class="h-3 w-2/5 animate-pulse rounded bg-surface-gray-2"
                />
                <div
                  class="h-1.5 w-full animate-pulse rounded-full bg-surface-gray-2"
                />
              </div>
            </div>

            <!-- Empty: first use, or filtered to nothing -->
            <div
              v-else-if="!visibleProjects.length"
              class="mt-5 rounded-lg border border-outline-gray-2 bg-surface-base"
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
                    : __(
                        'Projects you are added to will show up here. Ask a project manager to add you.'
                      )
                "
              >
                <Button
                  v-if="authStore.isProjectManager"
                  variant="solid"
                  :label="__('New project')"
                  @click="showNewForm = true"
                >
                  <template #prefix>
                    <LucidePlus class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </TaskyState>
              <TaskyState
                v-else
                :icon="LucideSearchX"
                :title="__('No matching projects')"
                :message="__('Try a different search, or clear the filters.')"
              >
                <Button
                  :label="__('Show all projects')"
                  @click="resetFilters"
                />
              </TaskyState>
            </div>

            <!-- Cards, one section per department -->
            <div v-else class="mt-5 flex flex-col gap-8">
              <section
                v-for="(group, groupIdx) in groups"
                :key="group.key"
                :aria-labelledby="`department-heading-${groupIdx}`"
              >
                <h2
                  :id="`department-heading-${groupIdx}`"
                  class="flex items-center gap-2 text-base-semibold text-ink-gray-9"
                >
                  {{ group.label }}
                  <span class="font-mono text-sm tabular-nums text-ink-gray-5">
                    {{ group.projects.length }}
                    <span class="sr-only">{{ __("projects") }}</span>
                  </span>
                </h2>
                <ul
                  role="list"
                  class="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
                >
                  <li
                    v-for="project in group.projects"
                    :key="project.name"
                    class="flex min-w-0"
                  >
                    <ProjectCard
                      class="flex-1"
                      :project="project"
                      :stats="statsFor(project)"
                      :phases="phasesFor(project)"
                      :loading="isStatsLoading(project)"
                      :failed="!!dashboards[project.name]?.error"
                      @edit="openEdit(project.name)"
                      @checklist="openChecklist(project.name)"
                      @new-task="openNewTask(project.name)"
                    />
                  </li>
                </ul>
              </section>
            </div>
          </div>
        </template>
      </div>
    </div>

    <ProjectFormDialog
      v-model:open="showNewForm"
      :default-department="selectedDepartmentName"
      @saved="projects.reload()"
    />
    <ProjectFormDialog
      v-model:open="showEdit"
      :project-id="editingProject"
      @saved="projects.reload()"
    />

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
import LayoutHeader from "@/components/LayoutHeader.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { watchDebounced } from "@vueuse/core";
import { Button, TextInput, createResource } from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideFolderOpen from "~icons/lucide/folder-open";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import LucideX from "~icons/lucide/x";
import GenerateChecklistModal from "./components/GenerateChecklistModal.vue";
import NewTaskDialog from "./components/NewTaskDialog.vue";
import ProjectCard, {
  type ProjectPhase,
  type ProjectStats,
  type ProjectSummary,
} from "./components/ProjectCard.vue";
import ProjectFormDialog from "./components/ProjectFormDialog.vue";
import { daysUntil } from "./taskMeta";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const listId = `projects-list-${useId()}`;

interface Department {
  name: string;
  is_active: boolean;
}

const STATUS_TABS = ["Open", "Completed", "Cancelled", "All"] as const;
type StatusTab = typeof STATUS_TABS[number];
type Show = "" | "overdue" | "ending";

const projects = createResource({
  url: "helpdesk.tasky.api.get_projects",
  auto: true,
  transform: (d: ProjectSummary[]) => d ?? [],
});

const allProjects = computed<ProjectSummary[]>(() => projects.data ?? []);
const isLoading = computed(() => projects.loading && !projects.data);

// inactive ones too, so projects still in one keep their section
const departments = createResource({
  url: "helpdesk.api.departments.get_departments",
  params: { include_inactive: true },
  auto: true,
  transform: (d: Department[]) => d ?? [],
});
const departmentList = computed<Department[]>(() => departments.data ?? []);

// --- filters, kept in the URL so a view can be shared ---

const ALL_DEPARTMENTS = "";
// a key no department name can be: names are trimmed, and this one is a space
const NO_DEPARTMENT = " ";
// the URL can't carry a lone space, so "no department" travels as this
const NO_DEPARTMENT_PARAM = "__none__";

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const activeStatus = ref<StatusTab>(
  STATUS_TABS.find((t) => t === queryValue("status")) ?? "Open"
);
const activeDepartment = ref(
  queryValue("department") === NO_DEPARTMENT_PARAM
    ? NO_DEPARTMENT
    : queryValue("department")
);
const search = ref(queryValue("q"));
const show = ref<Show>(
  (["overdue", "ending"] as const).find((s) => s === queryValue("show")) ?? ""
);

watchDebounced(
  [activeStatus, activeDepartment, search, show],
  () => {
    router.replace({
      query: {
        ...route.query,
        status: activeStatus.value === "Open" ? undefined : activeStatus.value,
        department:
          activeDepartment.value === NO_DEPARTMENT
            ? NO_DEPARTMENT_PARAM
            : activeDepartment.value || undefined,
        q: search.value.trim() || undefined,
        show: show.value || undefined,
      },
    });
  },
  { debounce: 250 }
);

function departmentKey(p: ProjectSummary) {
  return p.department || NO_DEPARTMENT;
}

function isOpen(p: ProjectSummary) {
  return (p.status || "Open") === "Open";
}

function matchesStatus(p: ProjectSummary, tab: StatusTab) {
  return tab === "All" || (p.status || "Open") === tab;
}

function matchesDepartment(p: ProjectSummary, key: string) {
  return key === ALL_DEPARTMENTS || departmentKey(p) === key;
}

function matchesShow(p: ProjectSummary) {
  if (show.value === "overdue") return (statsFor(p)?.overdue ?? 0) > 0;
  if (show.value === "ending") return isEndingSoon(p);
  return true;
}

function countFor(tab: StatusTab) {
  return allProjects.value.filter(
    (p) =>
      matchesStatus(p, tab) &&
      matchesDepartment(p, activeDepartment.value) &&
      matchesShow(p)
  ).length;
}

function departmentCount(key: string) {
  return allProjects.value.filter(
    (p) =>
      matchesStatus(p, activeStatus.value) &&
      matchesDepartment(p, key) &&
      matchesShow(p)
  ).length;
}

function setStatus(tab: StatusTab) {
  activeStatus.value = tab;
  // the summary filters count open projects only
  if (tab !== "Open") show.value = "";
}

const departmentChips = computed(() => {
  const used = new Set(allProjects.value.map(departmentKey));
  const named = departmentList.value
    .filter((d) => d.is_active || used.has(d.name))
    .map((d) => ({ key: d.name, label: d.name }));
  if (!named.length) return [];
  return [
    { key: ALL_DEPARTMENTS, label: __("All departments") },
    ...named,
    ...(used.has(NO_DEPARTMENT)
      ? [{ key: NO_DEPARTMENT, label: __("No department") }]
      : []),
  ];
});

// a department can lose its chip (inactive, last project moved away); don't keep filtering by it
watch(departmentChips, (chips) => {
  if (
    // a department from the URL waits until both lists are in
    departments.data &&
    projects.data &&
    activeDepartment.value !== ALL_DEPARTMENTS &&
    !chips.some((c) => c.key === activeDepartment.value)
  )
    activeDepartment.value = ALL_DEPARTMENTS;
});

const selectedDepartmentName = computed(() =>
  activeDepartment.value === NO_DEPARTMENT ? "" : activeDepartment.value
);

const visibleProjects = computed(() => {
  const q = search.value.trim().toLowerCase();
  return allProjects.value.filter(
    (p) =>
      matchesStatus(p, activeStatus.value) &&
      matchesDepartment(p, activeDepartment.value) &&
      matchesShow(p) &&
      (!q ||
        (p.project_name || "").toLowerCase().includes(q) ||
        p.name.toLowerCase().includes(q) ||
        (p.customer || "").toLowerCase().includes(q))
  );
});

interface ProjectGroup {
  key: string;
  label: string;
  projects: ProjectSummary[];
}

// departments in their set order, empty ones left out, projects without one last
const groups = computed<ProjectGroup[]>(() => {
  const byDepartment = new Map<string, ProjectSummary[]>();
  for (const p of visibleProjects.value) {
    const key = departmentKey(p);
    if (!byDepartment.has(key)) byDepartment.set(key, []);
    byDepartment.get(key)!.push(p);
  }
  const order = departmentList.value.map((d) => d.name);
  const unlisted = [...byDepartment.keys()]
    .filter((key) => key !== NO_DEPARTMENT && !order.includes(key))
    .sort();
  const named = [...order, ...unlisted]
    .filter((key) => byDepartment.has(key))
    .map((key) => ({ key, label: key, projects: byDepartment.get(key)! }));
  const none = byDepartment.get(NO_DEPARTMENT);
  return none
    ? [
        ...named,
        { key: NO_DEPARTMENT, label: __("No department"), projects: none },
      ]
    : named;
});

function resetFilters() {
  activeStatus.value = "All";
  activeDepartment.value = ALL_DEPARTMENTS;
  search.value = "";
  show.value = "";
}

// --- per-project task stats ---

const dashboards = reactive<Record<string, ReturnType<typeof createResource>>>(
  {}
);

watch(
  () => projects.data,
  (list: ProjectSummary[] | null) => {
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
  departments.reload();
  Object.values(dashboards).forEach((d) => d.reload());
}

function statsFor(project: ProjectSummary): ProjectStats | null {
  return dashboards[project.name]?.data?.stats ?? null;
}

function phasesFor(project: Pick<ProjectSummary, "name">): ProjectPhase[] {
  return dashboards[project.name]?.data?.phases ?? [];
}

function isStatsLoading(project: ProjectSummary) {
  const d = dashboards[project.name];
  return !d || (d.loading && !d.data);
}

// --- summary: open projects under the department filter ---

const openInScope = computed(() =>
  allProjects.value.filter(
    (p) => isOpen(p) && matchesDepartment(p, activeDepartment.value)
  )
);

const statsLoading = computed(() => openInScope.value.some(isStatsLoading));
// the overdue view depends on each project's stats, so it loads until they're in
const listLoading = computed(
  () => isLoading.value || (show.value === "overdue" && statsLoading.value)
);

const overdueTotal = computed(() =>
  openInScope.value.reduce((sum, p) => sum + (statsFor(p)?.overdue ?? 0), 0)
);

const overdueSub = computed(() => {
  const failed = openInScope.value.filter(
    (p) => dashboards[p.name]?.error
  ).length;
  if (failed)
    return failed === 1
      ? __("1 project didn't load")
      : __("{0} projects didn't load", String(failed));
  const projectsWith = openInScope.value.filter(
    (p) => (statsFor(p)?.overdue ?? 0) > 0
  ).length;
  if (!projectsWith) return __("Nothing late");
  return projectsWith === 1
    ? __("In 1 project")
    : __("In {0} projects", String(projectsWith));
});

function isEndingSoon(p: ProjectSummary) {
  if (!isOpen(p) || !p.expected_end_date) return false;
  const days = daysUntil(p.expected_end_date);
  return days >= 0 && days <= 14;
}

const endingSoon = computed(() => openInScope.value.filter(isEndingSoon));

const pastEnd = computed(() =>
  openInScope.value.filter(
    (p) => p.expected_end_date && daysUntil(p.expected_end_date) < 0
  )
);

const pastEndSub = computed(() =>
  pastEnd.value.length === 1
    ? __("1 more is past its end date")
    : __("{0} more are past their end date", String(pastEnd.value.length))
);

const showTile = computed(() => {
  if (show.value === "overdue")
    return __("Showing open projects with overdue tasks.");
  if (show.value === "ending")
    return __("Showing open projects ending in the next 14 days.");
  return "";
});

function toggleShow(next: Show) {
  show.value = show.value === next ? "" : next;
  if (show.value) activeStatus.value = "Open";
}

// --- dialogs ---

const showNewForm = ref(false);

const showEdit = ref(false);
const editingProject = ref("");

function openEdit(name: string) {
  editingProject.value = name;
  showEdit.value = true;
}

const showChecklistModal = ref(false);
const selectedProjectId = ref("");
const showNewTask = ref(false);
const newTaskProject = ref("");

function openChecklist(name: string) {
  selectedProjectId.value = name;
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

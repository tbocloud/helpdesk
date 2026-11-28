<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Handover')"
      :subtitle="
        __(
          'When someone leaves: who takes over each of their projects and tasks.'
        )
      "
    />

    <div class="relative flex-1 overflow-auto">
      <div class="flex w-full max-w-4xl flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="people.error && !people.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the team')"
          :message="
            errorText(people.error, __('Check your connection and try again.'))
          "
        >
          <Button :label="__('Retry')" @click="people.reload()" />
        </TaskyState>

        <section
          v-else
          class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
          :aria-labelledby="pickId"
        >
          <h2 :id="pickId" class="text-base font-semibold text-ink-gray-9">
            {{ __("Who is leaving?") }}
          </h2>
          <FormControl
            v-model="employee"
            type="select"
            :label="__('Person')"
            :options="personOptions"
            :disabled="people.loading"
          />
          <p
            v-if="people.data && !holders.length"
            class="text-p-sm text-ink-gray-6"
          >
            {{ __("Nobody holds open projects or tasks.") }}
          </p>
        </section>

        <div
          v-if="employee && preview.loading && !preview.data"
          class="h-40 animate-pulse rounded-xl bg-surface-gray-3"
          aria-busy="true"
        />

        <TaskyState
          v-else-if="employee && preview.error"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load their work')"
          :message="errorText(preview.error, __('Try again.'))"
        >
          <Button :label="__('Retry')" @click="preview.reload()" />
        </TaskyState>

        <template v-else-if="employee && plan">
          <div
            v-if="result"
            role="status"
            class="flex items-start gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
          >
            <span
              class="grid size-9 shrink-0 place-items-center rounded-full bg-success-soft text-success"
              aria-hidden="true"
            >
              <LucideCheck class="size-5" />
            </span>
            <div class="flex flex-col gap-1 text-p-sm text-ink-gray-8">
              <p class="font-semibold text-ink-gray-9">
                {{ __("Handover done ({0})", result.name) }}
              </p>
              <p v-for="row in result.projects" :key="row.project">
                {{
                  __(
                    "{0}: {1} open tasks to {2}",
                    projectName(row.project),
                    String(row.tasks_moved),
                    takerName(row.new_owner)
                  )
                }}
              </p>
              <p v-if="result.other_tasks_moved">
                {{
                  __(
                    "{0} tasks outside projects moved",
                    String(result.other_tasks_moved)
                  )
                }}
              </p>
            </div>
          </div>

          <TaskyState
            v-if="!plan.projects.length && !plan.other_tasks"
            class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
            :icon="LucideCircleCheck"
            :title="__('Nothing left to hand over')"
            :message="__('{0} has no open projects or tasks.', plan.full_name)"
          />

          <form
            v-else
            class="flex flex-col gap-4"
            novalidate
            @submit.prevent="confirming = true"
          >
            <section
              v-if="plan.projects.length"
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="projectsId"
            >
              <h2
                :id="projectsId"
                class="border-b border-outline-gray-2 px-4 py-3 text-base font-semibold text-ink-gray-9"
              >
                {{ __("Their projects") }}
                <span class="font-normal tabular-nums text-ink-gray-5">{{
                  plan.projects.length
                }}</span>
              </h2>
              <ul role="list">
                <li
                  v-for="row in plan.projects"
                  :key="row.project"
                  class="flex flex-col gap-3 border-b border-outline-gray-1 px-4 py-4 last:border-b-0"
                >
                  <div class="flex flex-wrap items-center gap-2">
                    <RouterLink
                      :to="{
                        name: 'TaskyProject',
                        params: { projectId: row.project },
                      }"
                      class="rounded text-[13px] font-semibold text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                      >{{ row.project_name }}</RouterLink
                    >
                    <TaskyBadge v-if="row.role" :label="__(row.role)" />
                    <TaskyBadge
                      v-if="row.is_lead"
                      :label="__('Project lead')"
                    />
                    <span class="ml-auto text-xs tabular-nums text-ink-gray-6">
                      {{ __("{0} open tasks", String(row.open_tasks)) }}
                    </span>
                    <RouterLink
                      :to="{
                        name: 'TaskyAccess',
                        params: { projectId: row.project },
                      }"
                      class="flex items-center gap-1 rounded text-xs text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                    >
                      <LucideServer class="size-3.5" aria-hidden="true" />
                      {{
                        row.access_entries
                          ? __(
                              "Access ({0} added by them)",
                              String(row.access_entries)
                            )
                          : __("Access")
                      }}
                    </RouterLink>
                  </div>
                  <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <FormControl
                      v-model="owners[row.project]"
                      type="select"
                      :label="__('Taken over by')"
                      :options="takerOptions"
                      required
                    />
                    <FormControl
                      v-model="notes[row.project]"
                      type="textarea"
                      :rows="2"
                      :label="__('Handover note')"
                      :placeholder="
                        __('Where things stand, what is pending, who to call')
                      "
                    />
                  </div>
                </li>
              </ul>
            </section>

            <section
              class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="restId"
            >
              <h2 :id="restId" class="text-base font-semibold text-ink-gray-9">
                {{ __("Everything else") }}
              </h2>
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <FormControl
                  v-model="defaultOwner"
                  type="select"
                  :label="
                    __(
                      'Takes their {0} tasks outside projects',
                      String(plan.other_tasks)
                    )
                  "
                  :options="takerOptions"
                  :disabled="!plan.other_tasks"
                />
                <TextInput
                  v-model="lastDay"
                  type="date"
                  :label="__('Last day')"
                />
              </div>
              <FormControl
                v-model="note"
                type="textarea"
                :rows="3"
                :label="__('Handover note')"
                :placeholder="
                  __(
                    'Anything the team must know: laptops, accounts to close, clients to inform…'
                  )
                "
              />
            </section>

            <div
              v-if="errorMessage"
              role="alert"
              class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
            >
              <LucideCircleAlert
                class="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <span>{{ errorMessage }}</span>
            </div>

            <div class="flex justify-end">
              <Button
                variant="solid"
                size="md"
                type="submit"
                :label="__('Complete handover')"
              />
            </div>
          </form>
        </template>
      </div>
    </div>

    <Dialog
      v-model="confirming"
      :options="{
        title: __('Complete the handover?'),
        message: __(
          'Their open tasks move to the people you chose, who also take their place on each project. {0} leaves those project teams. This can\'t be undone here.',
          plan?.full_name ?? ''
        ),
      }"
    >
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="confirming = false" />
          <Button
            variant="solid"
            :label="__('Complete handover')"
            :loading="saving"
            @click="complete()"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Dialog,
  FormControl,
  TextInput,
  call,
  createResource,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideServer from "~icons/lucide/server";

interface Person {
  name: string;
  full_name: string;
  enabled?: number;
}
interface PlanProject {
  project: string;
  project_name: string;
  role: string | null;
  is_lead: boolean;
  open_tasks: number;
  access_entries: number;
  suggested_owner: string | null;
}
interface Plan {
  employee: string;
  full_name: string;
  projects: PlanProject[];
  other_tasks: number;
}
interface Result {
  name: string;
  projects: { project: string; new_owner: string; tasks_moved: number }[];
  other_tasks_moved: number;
}

const pickId = useId();
const projectsId = useId();
const restId = useId();

const people = createResource({
  url: "helpdesk.api.employee_handover.get_people",
  auto: true,
  onError() {},
});
const holders = computed<Person[]>(() => people.data?.people ?? []);
const takers = computed<Person[]>(() => people.data?.takers ?? []);
const personOptions = computed(() => [
  { label: __("Choose a person"), value: "" },
  ...holders.value.map((p) => ({
    label: p.enabled ? p.full_name : __("{0} (disabled)", p.full_name),
    value: p.name,
  })),
]);
const takerOptions = computed(() => [
  { label: __("Choose who"), value: "" },
  ...takers.value
    .filter((p) => p.name !== employee.value)
    .map((p) => ({ label: p.full_name || p.name, value: p.name })),
]);
function takerName(user: string) {
  return takers.value.find((p) => p.name === user)?.full_name ?? user;
}

const employee = ref("");
const owners = reactive<Record<string, string>>({});
const notes = reactive<Record<string, string>>({});
const defaultOwner = ref("");
const lastDay = ref("");
const note = ref("");
const errorMessage = ref("");
const confirming = ref(false);
const saving = ref(false);
const result = ref<Result | null>(null);

const preview = createResource({
  url: "helpdesk.api.employee_handover.get_handover_preview",
  makeParams: () => ({ employee: employee.value }),
  onError() {},
  onSuccess(data: Plan) {
    for (const key of Object.keys(owners)) delete owners[key];
    for (const key of Object.keys(notes)) delete notes[key];
    for (const row of data.projects) {
      owners[row.project] = row.suggested_owner ?? "";
      notes[row.project] = "";
    }
  },
});
const plan = computed(() => preview.data as Plan | undefined);
function projectName(project: string) {
  return (
    plan.value?.projects.find((p) => p.project === project)?.project_name ??
    project
  );
}

watch(employee, (value) => {
  result.value = null;
  errorMessage.value = "";
  defaultOwner.value = "";
  lastDay.value = "";
  note.value = "";
  if (value) preview.reload();
});

async function complete() {
  const rows = plan.value?.projects ?? [];
  const missing = rows.find((row) => !owners[row.project]);
  if (missing) {
    confirming.value = false;
    errorMessage.value = __("Choose who takes over {0}.", missing.project_name);
    return;
  }
  if (plan.value?.other_tasks && !defaultOwner.value) {
    confirming.value = false;
    errorMessage.value = __("Choose who takes their tasks outside projects.");
    return;
  }
  errorMessage.value = "";
  saving.value = true;
  try {
    const done = await call(
      "helpdesk.api.employee_handover.complete_handover",
      {
        employee: employee.value,
        projects: rows.map((row) => ({
          project: row.project,
          new_owner: owners[row.project],
          note: notes[row.project],
        })),
        default_owner: defaultOwner.value || null,
        last_day: lastDay.value || null,
        note: note.value,
      }
    );
    confirming.value = false;
    toast.success(__("Handover done"));
    preview.reload();
    people.reload();
    result.value = done;
  } catch (e) {
    confirming.value = false;
    errorMessage.value = errorText(e, __("Couldn't complete it. Try again."));
  } finally {
    saving.value = false;
  }
}
</script>

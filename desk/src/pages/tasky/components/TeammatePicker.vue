<template>
  <!-- the list opens outside the dialog; dialogs using this set :dismissible="false" -->
  <div class="flex flex-col gap-1.5">
    <Autocomplete
      :label="label"
      :options="options"
      :placeholder="__('Pick a teammate')"
      :loading="projectDetail.loading || assignable.loading"
      :model-value="modelValue || null"
      @update:model-value="
        (v: { value: string } | string | null) =>
          emit('update:modelValue', (typeof v === 'string' ? v : v?.value) || '')
      "
    />
    <p v-if="loaded && !options.length" class="text-p-sm text-ink-gray-5">
      {{
        __(
          "No one else is on this project yet. Ask the project lead to add people."
        )
      }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { useAuthStore } from "@/stores/auth";
import { Autocomplete, createResource } from "frappe-ui";
import { computed, watch } from "vue";

interface Person {
  name: string;
  full_name?: string;
}

const props = defineProps<{
  modelValue: string;
  /** The task's project; only its team (members and lead) is offered. */
  project: string;
  label: string;
  /** People not to offer, e.g. the task's current assignees. */
  exclude?: string[];
}>();

const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const authStore = useAuthStore();

const projectDetail = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  onError() {},
});

// active agents with enabled accounts; disabled people never appear
const assignable = createResource({
  url: "helpdesk.tasky.api.get_users",
  auto: true,
  onError() {},
});

watch(
  () => props.project,
  (project) => {
    if (project && projectDetail.params?.project !== project)
      projectDetail.submit({ project });
  },
  { immediate: true }
);

const loaded = computed(
  () => !!projectDetail.data && !!assignable.data && !projectDetail.loading
);

const options = computed(() => {
  const detail = projectDetail.data;
  if (!detail) return [];
  const team = new Set<string>(
    (detail.users ?? []).map((m: { user: string }) => m.user)
  );
  if (detail.project_lead) team.add(detail.project_lead);
  const skip = new Set([authStore.userId, ...(props.exclude ?? [])]);
  return ((assignable.data ?? []) as Person[])
    .filter((u) => team.has(u.name) && !skip.has(u.name))
    .map((u) => ({
      label:
        u.name === detail.project_lead
          ? __("{0} (project lead)", u.full_name || u.name)
          : u.full_name || u.name,
      value: u.name,
      description: u.name,
    }));
});
</script>

<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">
          {{ __("Meeting types") }}
        </div>
      </template>
      <template #right-header>
        <Button
          v-if="canEdit"
          variant="solid"
          :label="__('New type')"
          :icon-left="LucidePlus"
          @click="edit(null)"
        />
      </template>
    </LayoutHeader>

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4 md:px-6">
      <p class="mb-3 max-w-2xl text-p-sm text-ink-gray-6">
        {{
          __(
            "Types group meetings on the Meeting calendar. Picking a type when scheduling sets the meeting's usual length."
          )
        }}
      </p>

      <div v-if="types.loading && !types.data" aria-hidden="true">
        <div
          v-for="i in 3"
          :key="i"
          class="mb-2 h-14 animate-pulse rounded-lg bg-surface-gray-2"
        />
      </div>

      <TaskyState
        v-else-if="!types.data?.length"
        :icon="LucideShapes"
        :title="__('No meeting types yet')"
        :message="
          canEdit
            ? __('Add types such as Team meeting, Client review or One-to-one.')
            : __('An Agent Manager can add them.')
        "
      />

      <ul
        v-else
        role="list"
        class="max-w-2xl overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
      >
        <li
          v-for="type in types.data"
          :key="type.name"
          class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
        >
          <div class="flex min-w-0 flex-1 flex-col">
            <span class="flex items-center gap-2 text-base text-ink-gray-9">
              <span class="truncate">{{ type.name }}</span>
              <span
                v-if="type.disabled"
                class="rounded px-1.5 text-2xs text-ink-gray-6 ring-1 ring-inset ring-outline-gray-3"
              >
                {{ __("Off") }}
              </span>
            </span>
            <span class="truncate text-p-xs text-ink-gray-6">
              <span class="font-mono tabular-nums">
                {{ __("{0} min", String(type.default_duration)) }}
              </span>
              <template v-if="type.description">
                · {{ type.description }}
              </template>
            </span>
          </div>
          <Button
            v-if="canEdit"
            variant="ghost"
            :label="__('Edit')"
            :aria-label="__('Edit {0}', type.name)"
            @click="edit(type)"
          />
        </li>
      </ul>
    </div>

    <Dialog
      v-model:open="showForm"
      :title="editing ? __('Edit meeting type') : __('New meeting type')"
      size="md"
    >
      <form
        :id="formId"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="save"
      >
        <TextInput
          v-model="form.name"
          :label="__('Name')"
          :disabled="!!editing"
          maxlength="140"
          required
        />
        <TextInput
          v-model="form.duration"
          type="number"
          min="5"
          max="480"
          step="5"
          :label="__('Usual length (minutes)')"
          required
        />
        <Textarea
          v-model="form.description"
          :label="__('Description (optional)')"
          :rows="2"
        />
        <label class="flex items-center gap-2 text-sm text-ink-gray-8">
          <input
            v-model="form.disabled"
            type="checkbox"
            class="rounded border-outline-gray-3 text-ink-gray-9 focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          />
          {{ __("Turned off: can't be picked for new meetings") }}
        </label>
        <p v-if="error" role="alert" class="text-p-sm text-danger">
          {{ error }}
        </p>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            :form="formId"
            :label="__('Save')"
            :loading="saving"
            :disabled="!form.name.trim() || !form.duration"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Dialog,
  TextInput,
  Textarea,
  createListResource,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideShapes from "~icons/lucide/shapes";

interface MeetingType {
  name: string;
  default_duration: number;
  description: string | null;
  disabled: 0 | 1;
}

const auth = useAuthStore();
// the roles that may write HD Meeting Type
const canEdit = computed(() => auth.isManager || auth.isAdmin);

const types = createListResource({
  doctype: "HD Meeting Type",
  fields: ["name", "default_duration", "description", "disabled"],
  orderBy: "disabled asc, name asc",
  pageLength: 200,
  auto: true,
});

const formId = `meeting-type-${useId()}`;
const showForm = ref(false);
const editing = ref<MeetingType | null>(null);
const form = reactive({
  name: "",
  duration: "30",
  description: "",
  disabled: false,
});
const saving = ref(false);
const error = ref("");

function edit(type: MeetingType | null) {
  editing.value = type;
  form.name = type?.name ?? "";
  form.duration = String(type?.default_duration ?? 30);
  form.description = type?.description ?? "";
  form.disabled = !!type?.disabled;
  error.value = "";
  showForm.value = true;
}

async function save() {
  const values = {
    default_duration: Number(form.duration),
    description: form.description.trim(),
    disabled: form.disabled ? 1 : 0,
  };
  saving.value = true;
  error.value = "";
  try {
    if (editing.value) {
      await types.setValue.submit({ name: editing.value.name, ...values });
    } else {
      await types.insert.submit({ meeting_type: form.name.trim(), ...values });
    }
    toast.success(__("Meeting type saved."));
    showForm.value = false;
    types.reload();
  } catch (e) {
    error.value = errorText(e, __("Couldn't save the meeting type."));
  } finally {
    saving.value = false;
  }
}
</script>

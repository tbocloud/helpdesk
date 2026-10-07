<template>
  <div class="flex h-full w-full min-w-0 flex-col">
    <div class="px-4 pb-5 pt-6 sm:px-8 sm:pt-8">
      <SettingsLayoutHeader
        :title="title"
        :description="description"
        :dirty="dirty"
        :back-label="backLabel"
        @back="emit('back')"
      >
        <template v-if="$slots.title" #title>
          <slot name="title" />
        </template>
        <template v-if="$slots.description" #description>
          <slot name="description" />
        </template>
        <template v-if="$slots.badge" #badge>
          <slot name="badge" />
        </template>
        <template v-if="$slots['header-actions'] || onSave" #actions>
          <slot name="header-actions" />
          <Button
            v-if="onSave && !blocked"
            variant="solid"
            :label="saveLabel || __('Save changes')"
            :disabled="saveDisabled ?? !dirty"
            :loading="saving"
            @click="onSave()"
          />
        </template>
        <template v-if="$slots['header-bottom'] && !blocked" #bottom>
          <slot name="header-bottom" />
        </template>
      </SettingsLayoutHeader>
    </div>
    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 pb-8 sm:px-8">
      <TaskyState
        v-if="noAccess"
        :icon="LucideLock"
        :title="__('You can\'t open these settings')"
        :message="
          __(
            'Your role doesn\'t allow it. Ask a helpdesk admin if you need access.'
          )
        "
      />
      <TaskyState
        v-else-if="error"
        error
        :icon="LucideCircleAlert"
        :title="__('Couldn\'t load these settings')"
        :message="
          errorText(error, __('Check your connection, then try again.'))
        "
      >
        <template v-if="onRetry" #default>
          <Button :label="__('Try again')" @click="onRetry()" />
        </template>
      </TaskyState>
      <div
        v-else-if="loading"
        class="flex flex-col gap-6"
        aria-busy="true"
        :aria-label="__('Loading')"
      >
        <div v-for="i in 3" :key="i" class="flex flex-col gap-2">
          <div class="h-4 w-40 animate-pulse rounded bg-surface-gray-2" />
          <div class="h-3 w-2/3 animate-pulse rounded bg-surface-gray-2" />
          <div class="h-8 w-full animate-pulse rounded bg-surface-gray-1" />
        </div>
      </div>
      <slot v-else name="content" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { disableSettingModalOutsideClick } from "@/components/Settings/settingsModal";
import SettingsLayoutHeader from "@/components/Settings/SettingsLayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button } from "frappe-ui";
import { computed, onBeforeUnmount, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideLock from "~icons/lucide/lock";

const props = withDefaults(
  defineProps<{
    title?: string;
    description?: string;
    /** Shows the Unsaved badge and keeps the modal open until saved or discarded. */
    dirty?: boolean;
    /** Shows a back button; the page handles `@back`. */
    backLabel?: string;
    /** Renders the page's one Save button in the header; disabled until dirty. */
    onSave?: () => void;
    saving?: boolean;
    saveLabel?: string;
    /** Overrides "disabled until dirty", e.g. a new record that can be saved as it is. */
    saveDisabled?: boolean;
    /** Shows a skeleton instead of the content. */
    loading?: boolean;
    /** A failed load: shows the message, with Try again when `@retry` is set. */
    error?: unknown;
    onRetry?: () => void;
  }>(),
  // undefined keeps "disabled until dirty"; Vue would default a boolean to false
  { saveDisabled: undefined }
);

const emit = defineEmits<{ (e: "back"): void }>();

const noAccess = computed(() => {
  const e = props.error as { exc_type?: string; status?: number } | undefined;
  return e?.exc_type === "PermissionError" || e?.status === 403;
});
const blocked = computed(() => props.loading || !!props.error);

// the modal asks before closing or switching pages while a form is dirty
let heldOpen = false;
watch(
  () => props.dirty,
  (dirty) => {
    heldOpen = !!dirty;
    disableSettingModalOutsideClick.value = heldOpen;
  }
);
onBeforeUnmount(() => {
  if (heldOpen) disableSettingModalOutsideClick.value = false;
});
</script>

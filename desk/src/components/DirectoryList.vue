<template>
  <!-- the Customers and Contacts lists: link rows, bulk delete, paging and every state -->
  <div
    class="overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
  >
    <!-- Selection: replaces the column header while rows are picked -->
    <div
      v-if="selected.size"
      class="flex flex-wrap items-center gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2"
    >
      <span class="text-sm tabular-nums text-ink-gray-8" aria-live="polite">
        {{ __("{0} selected", String(selected.size)) }}
      </span>
      <Button
        v-if="selected.size < rows.length"
        variant="ghost"
        :label="__('Select all {0} shown', String(rows.length))"
        @click="selectAll"
      />
      <Button variant="ghost" :label="__('Clear')" @click="clearSelection" />
      <Button
        class="ml-auto"
        theme="red"
        variant="subtle"
        :label="__('Delete {0}', String(selected.size))"
        @click="confirmOpen = true"
      >
        <template #prefix>
          <LucideTrash2 class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <div
      v-else-if="rows.length"
      class="hidden items-center gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 md:flex"
    >
      <span v-if="deletable" class="flex w-5 shrink-0 items-center">
        <input
          type="checkbox"
          class="size-4 rounded border-outline-gray-4 text-ink-gray-9 focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          :aria-label="__('Select all shown')"
          :checked="false"
          @change="selectAll"
        />
      </span>
      <div class="grid flex-1 gap-4" :class="gridClass" aria-hidden="true">
        <span
          v-for="col in columns"
          :key="col.key"
          :class="col.align === 'right' ? 'text-right' : ''"
        >
          {{ col.label }}
        </span>
      </div>
    </div>

    <!-- Loading: first page only; later pages keep the rows on screen -->
    <div v-if="loading && !rows.length" :aria-label="__('Loading')">
      <div
        v-for="i in 6"
        :key="i"
        class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
      >
        <span
          class="size-8 shrink-0 animate-pulse rounded-full bg-surface-gray-2"
        />
        <div class="flex flex-1 flex-col gap-2">
          <span class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2" />
          <span class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2" />
        </div>
      </div>
    </div>

    <TaskyState
      v-else-if="error && !rows.length"
      :icon="LucideCircleAlert"
      :title="errorTitle"
      :message="errorText(error, __('Check your connection and try again.'))"
      error
    >
      <Button :label="__('Retry')" @click="emit('retry')" />
    </TaskyState>

    <slot v-else-if="!rows.length" name="empty" />

    <ul v-else role="list">
      <li
        v-for="row in rows"
        :key="row.name"
        class="relative flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 transition-colors last:border-b-0 hover:bg-surface-gray-1"
      >
        <!-- the whole row opens the record; the checkbox sits above the link -->
        <RouterLink
          :to="rowTo(row)"
          class="absolute inset-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
          :aria-label="rowLabel(row)"
        />
        <span
          v-if="deletable"
          class="relative z-[1] hidden w-5 shrink-0 items-center md:flex"
        >
          <input
            type="checkbox"
            class="size-4 rounded border-outline-gray-4 text-ink-gray-9 focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :aria-label="__('Select {0}', rowLabel(row))"
            :checked="selected.has(row.name)"
            @change="toggle(row.name)"
          />
        </span>
        <div
          class="grid min-w-0 flex-1 items-center gap-x-4 gap-y-1"
          :class="gridClass"
        >
          <slot name="row" :row="row" />
        </div>
      </li>
    </ul>

    <!-- Paging -->
    <div
      v-if="rows.length"
      class="flex flex-wrap items-center justify-between gap-2 border-t border-outline-gray-2 px-4 py-2.5"
    >
      <span class="text-p-sm tabular-nums text-ink-gray-5">
        {{
          total === undefined
            ? __("{0} shown", String(rows.length))
            : __("{0} of {1}", String(rows.length), String(total))
        }}
      </span>
      <span v-if="error" class="text-p-sm text-ink-gray-6" role="alert">
        {{ errorText(error, __("Couldn't load more.")) }}
      </span>
      <Button
        v-if="hasMore"
        :label="__('Show more')"
        :loading="loading"
        @click="emit('more')"
      />
    </div>

    <Dialog v-model:open="confirmOpen" :title="deleteTitle" size="md">
      <template #default>
        <p class="text-p-base text-ink-gray-7">{{ deleteMessage }}</p>
        <p v-if="deleteError" class="mt-3 text-p-sm text-danger" role="alert">
          {{ deleteError }}
        </p>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="confirmOpen = false" />
          <Button
            variant="solid"
            theme="red"
            :label="deleteTitle"
            :loading="deleting"
            @click="deleteSelected"
          >
            <template #prefix>
              <LucideTrash2 class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Dialog, frappeRequest, toast } from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideTrash2 from "~icons/lucide/trash-2";

export interface DirectoryColumn {
  key: string;
  label: string;
  align?: "right";
}

type Row = { name: string } & Record<string, unknown>;

const props = defineProps<{
  columns: DirectoryColumn[];
  /** grid columns for the header and each row, e.g. "md:grid-cols-[...]" */
  gridClass: string;
  rows: Row[];
  total?: number;
  loading: boolean;
  error?: unknown;
  hasMore: boolean;
  rowTo: (row: Row) => RouteLocationRaw;
  rowLabel: (row: Row) => string;
  errorTitle: string;
  /** shows checkboxes and bulk delete; the server still checks permission */
  deletable?: boolean;
  doctype: string;
  /** e.g. "customers": used in the delete dialog */
  noun: string;
}>();

const emit = defineEmits<{
  more: [];
  retry: [];
  deleted: [];
}>();

// frappe's delete_items queues more than this many in the background
const SYNC_DELETE_LIMIT = 10;

const selected = reactive(new Set<string>());
const confirmOpen = ref(false);
const deleting = ref(false);
const deleteError = ref("");

const deleteTitle = computed(() =>
  __("Delete {0} {1}", String(selected.size), props.noun)
);
const deleteMessage = computed(() =>
  __(
    "The selected {0} are removed for everyone, and this can't be undone. Any that other records still need are kept.",
    props.noun
  )
);

// rows that leave the list (search, reload) leave the selection too
watch(
  () => props.rows,
  (rows) => {
    const shown = new Set(rows.map((r) => r.name));
    for (const name of [...selected])
      if (!shown.has(name)) selected.delete(name);
  }
);
watch(confirmOpen, () => (deleteError.value = ""));

function toggle(name: string) {
  if (selected.has(name)) selected.delete(name);
  else selected.add(name);
}

function selectAll() {
  for (const row of props.rows) selected.add(row.name);
}

function clearSelection() {
  selected.clear();
}

async function deleteSelected() {
  if (deleting.value) return;
  deleting.value = true;
  deleteError.value = "";
  const items = [...selected];
  try {
    // up to SYNC_DELETE_LIMIT are deleted now and the ones that refused come back
    const failed: string[] =
      (await frappeRequest({
        url: "frappe.desk.reportview.delete_items",
        params: { items: JSON.stringify(items), doctype: props.doctype },
      })) || [];
    if (items.length > SYNC_DELETE_LIMIT) {
      toast.success(
        __(
          "Deleting {0} {1} in the background",
          String(items.length),
          props.noun
        )
      );
    } else if (failed.length) {
      toast.error(
        __(
          "{0} couldn't be deleted, usually because other records still link to them. They stay selected.",
          failed.join(", ")
        )
      );
    } else {
      toast.success(__("Deleted {0} {1}", String(items.length), props.noun));
    }
    confirmOpen.value = false;
    selected.clear();
    for (const name of failed) selected.add(name);
    emit("deleted");
  } catch (err) {
    deleteError.value = errorText(err, __("Nothing was deleted. Try again."));
  } finally {
    deleting.value = false;
  }
}
</script>

<template>
  <Dialog
    :open="!!item"
    :title="__('Comments')"
    :message="item?.label"
    size="xl"
    @update:open="(v: boolean) => !v && emit('update:item', null)"
  >
    <div class="flex flex-col gap-4">
      <!-- Loading -->
      <div
        v-if="!comments.data && !comments.error"
        class="flex flex-col gap-4"
        aria-busy="true"
      >
        <div v-for="i in 2" :key="i" class="flex flex-col gap-2">
          <div class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2" />
          <div class="h-3.5 w-3/4 animate-pulse rounded bg-surface-gray-2" />
        </div>
      </div>

      <TaskyState
        v-else-if="comments.error && !comments.data"
        error
        :icon="LucideCircleAlert"
        :title="__('Couldn\'t load the comments')"
        :message="
          errorText(comments.error, __('Check your connection and try again.'))
        "
      >
        <Button :label="__('Retry')" @click="comments.reload()" />
      </TaskyState>

      <template v-else>
        <p
          v-if="!list.length"
          class="rounded-lg bg-surface-gray-1 px-4 py-6 text-center text-p-sm text-ink-gray-6"
        >
          {{
            canComment
              ? __(
                  "No comments yet. Ask a question, or say why this version changed."
                )
              : __("No comments yet.")
          }}
        </p>

        <ol
          v-else
          class="flex max-h-[45vh] flex-col overflow-y-auto"
          :aria-label="__('Comments')"
        >
          <li
            v-for="c in list"
            :key="c.name"
            class="flex flex-col gap-1 border-b border-outline-gray-1 py-3 first:pt-0 last:border-b-0"
          >
            <div class="flex min-w-0 flex-wrap items-center gap-x-2 text-xs">
              <span class="text-sm font-medium text-ink-gray-8">
                {{ c.author_name }}
              </span>
              <time
                class="text-ink-gray-5"
                :datetime="c.creation"
                :title="dateFormat(c.creation, dateTooltipFormat)"
              >
                {{ timeAgo(c.creation) }}
              </time>
              <span v-if="c.edited" class="text-ink-gray-5">
                · {{ __("edited") }}
              </span>
              <div
                v-if="editing !== c.name && (c.can_edit || c.can_delete)"
                class="ml-auto flex items-center gap-0.5"
              >
                <Button
                  v-if="c.can_edit"
                  variant="ghost"
                  class="min-h-11 min-w-11 md:min-h-0 md:min-w-0"
                  :tooltip="__('Edit')"
                  :aria-label="__('Edit your comment')"
                  @click="startEdit(c)"
                >
                  <template #icon>
                    <LucidePencil class="size-4" aria-hidden="true" />
                  </template>
                </Button>
                <Button
                  v-if="c.can_delete"
                  variant="ghost"
                  class="min-h-11 min-w-11 md:min-h-0 md:min-w-0"
                  :tooltip="__('Delete')"
                  :aria-label="__('Delete comment by {0}', c.author_name)"
                  @click="confirming = c.name"
                >
                  <template #icon>
                    <LucideTrash2 class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </div>
            </div>

            <form
              v-if="editing === c.name"
              class="flex flex-col gap-2"
              novalidate
              @submit.prevent="saveEdit(c)"
            >
              <MentionTextarea
                v-model="editDraft"
                :team="team"
                :label="__('Edit comment')"
                :max-length="MAX_LENGTH"
                @submit="saveEdit(c)"
              />
              <div class="flex justify-end gap-2">
                <Button :label="__('Cancel')" @click="editing = null" />
                <Button
                  variant="solid"
                  type="submit"
                  :label="__('Save changes')"
                  :loading="edit.loading"
                  :disabled="!editDraft.trim()"
                />
              </div>
            </form>
            <p
              v-else
              class="whitespace-pre-wrap break-words text-p-sm text-ink-gray-8"
            >
              <template
                v-for="(part, i) in mentionSegments(c.text, team)"
                :key="i"
              >
                <span v-if="part.mention" class="font-medium text-ink-gray-9">{{
                  part.text
                }}</span>
                <template v-else>{{ part.text }}</template>
              </template>
            </p>

            <div
              v-if="confirming === c.name"
              role="group"
              :aria-label="__('Delete this comment?')"
              class="mt-1 flex flex-wrap items-center gap-2 rounded-md bg-surface-gray-1 px-3 py-2"
            >
              <span class="text-p-sm text-ink-gray-7">
                {{ __("Delete this comment for everyone?") }}
              </span>
              <div class="ml-auto flex gap-2">
                <Button :label="__('Keep it')" @click="confirming = null" />
                <Button
                  variant="solid"
                  theme="red"
                  :label="__('Delete comment')"
                  :loading="remove.loading"
                  :disabled="remove.loading"
                  @click="
                    !remove.loading &&
                      remove.submit({ project: projectId, comment: c.name })
                  "
                />
              </div>
            </div>
          </li>
        </ol>

        <form
          v-if="canComment"
          :id="formId"
          class="flex flex-col gap-1.5 border-t border-outline-gray-1 pt-4"
          novalidate
          @submit.prevent="post"
        >
          <MentionTextarea
            v-model="draft"
            :team="team"
            :label="__('Add a comment')"
            :placeholder="__('Type @ to mention someone on the project')"
            :max-length="MAX_LENGTH"
            @submit="post"
          />
          <p class="text-p-xs text-ink-gray-5">
            {{
              __(
                "People you mention, the people it's for and whoever added it are notified."
              )
            }}
          </p>
        </form>
        <p v-else class="text-p-sm text-ink-gray-6">
          {{ __("Only people on this project can comment.") }}
        </p>
      </template>
    </div>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Close')" @click="close" />
        <Button
          v-if="canComment"
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Post comment')"
          :loading="add.loading"
          :disabled="!draft.trim()"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat, errorText, timeAgo } from "@/utils";
import { Button, Dialog, createResource, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePencil from "~icons/lucide/pencil";
import LucideTrash2 from "~icons/lucide/trash-2";
import {
  mentionSegments,
  mentionedUsers,
  type ItemComment,
  type ItemRef,
  type Person,
} from "../projectFiles";
import MentionTextarea from "./MentionTextarea.vue";

// the same limit as MAX_COMMENT_LENGTH in helpdesk/api/project_files.py
const MAX_LENGTH = 5000;

const props = defineProps<{
  /** The dialog is open while this is set. */
  item: ItemRef | null;
  projectId: string;
}>();

const emit = defineEmits<{
  "update:item": [value: null];
  /** A comment was added or deleted, so the counts on the list changed. */
  changed: [];
}>();

const formId = `item-comments-${useId()}`;
const draft = ref("");
const editing = ref<string | null>(null);
const editDraft = ref("");
const confirming = ref<string | null>(null);

const comments = createResource({
  url: "helpdesk.api.project_files.list_item_comments",
  makeParams: () => ({
    project: props.projectId,
    kind: props.item?.kind,
    item: props.item?.name,
  }),
  // shown in the dialog instead of the global error toast
  onError() {},
});

const list = computed<ItemComment[]>(() => comments.data?.comments ?? []);
const team = computed<Person[]>(() => comments.data?.team ?? []);
const canComment = computed(() => !!comments.data?.can_comment);

watch(
  () => props.item,
  (item) => {
    if (!item) return;
    draft.value = "";
    editing.value = null;
    confirming.value = null;
    comments.reset();
    comments.reload();
  },
  { immediate: true }
);

function startEdit(c: ItemComment) {
  confirming.value = null;
  editDraft.value = c.text;
  editing.value = c.name;
}

const add = createResource({
  url: "helpdesk.api.project_files.add_item_comment",
  onSuccess() {
    draft.value = "";
    comments.reload();
    emit("changed");
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't post the comment.")));
  },
});

function post() {
  if (!props.item || !draft.value.trim() || add.loading) return;
  add.submit({
    project: props.projectId,
    kind: props.item.kind,
    item: props.item.name,
    content: draft.value,
    mentions: mentionedUsers(draft.value, team.value),
  });
}

const edit = createResource({
  url: "helpdesk.api.project_files.edit_item_comment",
  onSuccess() {
    editing.value = null;
    comments.reload();
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't save the comment.")));
  },
});

function saveEdit(c: ItemComment) {
  if (!editDraft.value.trim() || edit.loading) return;
  edit.submit({
    project: props.projectId,
    comment: c.name,
    content: editDraft.value,
    mentions: mentionedUsers(editDraft.value, team.value),
  });
}

const remove = createResource({
  url: "helpdesk.api.project_files.delete_item_comment",
  onSuccess() {
    confirming.value = null;
    toast.success(__("Comment deleted"));
    comments.reload();
    emit("changed");
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't delete the comment.")));
  },
});
</script>

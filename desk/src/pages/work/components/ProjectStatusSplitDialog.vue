<template>
  <Dialog
    v-model:open="open"
    :title="__('Paste or record a full update')"
    size="3xl"
    :dismissible="false"
  >
    <!-- 1. the text -->
    <div v-if="!drafts.length" class="flex flex-col gap-3">
      <p class="text-p-sm text-ink-gray-6">
        {{
          __(
            "Talk through your projects in one go, in Malayalam, English or both. The AI splits it into one update per project for you to check. Nothing is saved until you press Save all."
          )
        }}
      </p>
      <FormControl
        v-model="text"
        type="textarea"
        :rows="9"
        :label="__('Your update')"
        :placeholder="
          __('Galom: mobile app done, waiting for the client to confirm…')
        "
      />
      <div class="flex flex-wrap items-center gap-2">
        <VoiceButton
          v-model="text"
          :disabled="split.loading"
          @listening="(on) => on && (usedVoice = true)"
        />
      </div>
      <p
        v-if="!aiAvailable"
        class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-warning"
      >
        <LucideTriangleAlert
          class="mt-0.5 size-4 shrink-0"
          aria-hidden="true"
        />
        {{
          __(
            "AI isn't set up. An administrator adds an AI key in Settings → AI providers."
          )
        }}
      </p>
      <p
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ errorMessage }}
      </p>
    </div>

    <!-- 2. the review: edit anything, drop what is wrong, then save them all -->
    <div v-else class="flex flex-col gap-3">
      <p class="text-p-sm text-ink-gray-6">
        {{
          __(
            "{0} project(s) found. Check each row, fix what is wrong, then save them all. Projects you did not mention are left as they are.",
            String(drafts.length)
          )
        }}
      </p>
      <ul
        class="flex max-h-[55vh] flex-col gap-3 overflow-y-auto pr-1"
        role="list"
      >
        <li
          v-for="item in drafts"
          :key="item.draft.project"
          class="rounded-lg border border-outline-gray-2 p-3"
        >
          <div class="mb-3 flex flex-wrap items-center gap-2">
            <span class="text-base-semibold text-ink-gray-9">{{
              item.row.project_name
            }}</span>
            <span v-if="item.row.customer" class="text-sm text-ink-gray-5">{{
              item.row.customer
            }}</span>
            <TaskyBadge
              v-if="item.needs_check"
              tone="warning"
              :icon="LucideTriangleAlert"
              :label="__('Check the numbers: they are not in your text')"
            />
            <Button
              class="ml-auto"
              variant="ghost"
              :label="__('Remove')"
              @click="remove(item.draft.project)"
            >
              <template #prefix>
                <LucideX class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
          <ProjectStatusFields
            v-model="item.draft"
            :stages="stages"
            :waiting-on="waitingOn"
          />
        </li>
      </ul>
      <p
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ errorMessage }}
      </p>
    </div>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          v-if="drafts.length"
          :label="__('Back to the text')"
          @click="drafts = []"
        />
        <Button
          v-if="!drafts.length"
          variant="solid"
          :label="__('Read the update')"
          :loading="split.loading"
          :disabled="!text.trim() || !aiAvailable || split.loading"
          @click="readUpdate"
        />
        <Button
          v-else
          variant="solid"
          :label="__('Save all')"
          :loading="save.loading"
          :disabled="!canSave"
          :title="canSave ? undefined : __('Every row needs a stage')"
          @click="saveAll"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, Dialog, FormControl, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";
import VoiceButton from "../../leads/VoiceButton.vue";
import {
  draftFromProposal,
  type StatusDraft,
  type StatusProposal,
  type StatusRow,
} from "../projectStatusMeta";
import ProjectStatusFields from "./ProjectStatusFields.vue";

interface Reviewed {
  row: StatusRow;
  draft: StatusDraft;
  needs_check: boolean;
}

const props = defineProps<{
  /** the projects the person may write */
  rows: StatusRow[];
  stages: string[];
  waitingOn: string[];
  aiAvailable: boolean;
}>();
const emit = defineEmits<{ saved: [] }>();
const open = defineModel<boolean>("open", { default: false });

const text = ref("");
const usedVoice = ref(false);
const drafts = ref<Reviewed[]>([]);

watch(open, (isOpen) => {
  if (!isOpen) return;
  text.value = "";
  usedVoice.value = false;
  drafts.value = [];
  split.reset();
  save.reset();
});

const source = computed<StatusDraft["source"]>(() =>
  usedVoice.value ? "AI from voice" : "AI from text"
);

const split = createResource({
  url: "helpdesk.api.project_status.split_status_update",
  onSuccess(data: { updates: StatusProposal[] }) {
    const byProject = new Map(props.rows.map((r) => [r.project, r]));
    drafts.value = data.updates.flatMap((proposal) => {
      const row = byProject.get(proposal.project);
      return row
        ? [
            {
              row,
              draft: draftFromProposal(row, proposal, source.value),
              needs_check: proposal.needs_check,
            },
          ]
        : [];
    });
    if (!drafts.value.length)
      toast.info(__("No project from your list was found in that update."));
  },
  // shown inline instead of the global error toast
  onError() {},
});

const save = createResource({
  url: "helpdesk.api.project_status.save_status_updates",
  onSuccess(data: { saved: string[] }) {
    toast.success(__("{0} status update(s) saved", String(data.saved.length)));
    open.value = false;
    emit("saved");
  },
  onError() {},
});

const errorMessage = computed(() =>
  errorText(split.error || save.error, __("Something went wrong. Try again."))
);

const canSave = computed(
  () => drafts.value.every((d) => d.draft.stage) && !save.loading
);

function readUpdate() {
  split.submit({ text: text.value });
}

function remove(project: string) {
  drafts.value = drafts.value.filter((d) => d.draft.project !== project);
}

function saveAll() {
  save.submit({ updates: drafts.value.map((d) => d.draft) });
}
</script>

<template>
  <!-- a BRD's questions for the client (TBO Smart's docs/client-documents.md §5): the client
       answers on their own page; new answers go into the BRD with "Update from answers" -->
  <section
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="titleId"
  >
    <div
      class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-3"
    >
      <h2 :id="titleId" class="text-base-medium text-ink-gray-9">
        {{ __("Client questionnaire") }}
      </h2>
      <span class="text-sm tabular-nums text-ink-gray-6">
        {{ __("{0} of {1} answered", String(answered), String(rows.length)) }}
      </span>
      <div v-if="canWrite" class="ml-auto flex flex-wrap gap-2">
        <Button
          v-if="questionnaire.new_answers"
          variant="solid"
          :label="
            __('Update from {0} new answers', String(questionnaire.new_answers))
          "
          :disabled="dirty || questionsDirty"
          :tooltip="
            dirty || questionsDirty ? __('Save your changes first') : ''
          "
          :loading="apply.loading"
          @click="apply.submit({ name: proposal })"
        >
          <template #prefix>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Dropdown v-if="questionnaire.open" :options="shareOptions">
          <Button :label="__('Share with the client')">
            <template #prefix>
              <LucideShare2 class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
      </div>
    </div>

    <p
      v-if="!questionnaire.open"
      class="px-4 pt-3 text-p-sm text-ink-gray-6"
      role="status"
    >
      {{
        __(
          "Closed: the BRD was approved, declined or revised. The answers stay as the client gave them."
        )
      }}
    </p>
    <p
      v-else-if="questionnaire.sent_on"
      class="px-4 pt-3 text-p-sm text-ink-gray-6"
    >
      {{
        __(
          "The client has the link since {0}.",
          dayjs(questionnaire.sent_on).format("D MMM, h:mm a")
        )
      }}
      <template v-if="questionnaire.answered_on">
        {{
          __(
            "Last answer {0}.",
            dayjs(questionnaire.answered_on).format("D MMM, h:mm a")
          )
        }}
      </template>
    </p>

    <ul role="list" class="flex flex-col">
      <li
        v-for="(row, i) in rows"
        :key="row.name || `new-${i}`"
        class="flex flex-col gap-1.5 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
      >
        <div class="flex items-start gap-2">
          <div class="flex min-w-0 flex-1 flex-col gap-1">
            <span class="text-xs text-ink-gray-5">
              {{
                row.section_type
                  ? SECTION_LABELS[row.section_type] || row.section_type
                  : __("Other")
              }}
              <template v-if="row.asked_by === 'AI'">
                · {{ __("asked by the AI") }}</template
              >
            </span>
            <FormControl
              v-if="editable && !row.answer"
              v-model="row.question"
              type="textarea"
              :rows="2"
              :aria-label="__('Question')"
              maxlength="500"
            />
            <p v-else class="text-p-sm text-ink-gray-8">{{ row.question }}</p>
          </div>
          <Button
            v-if="editable && !row.answer"
            variant="ghost"
            :aria-label="__('Remove the question')"
            :tooltip="__('Remove the question')"
            @click="remove(i)"
          >
            <template #icon>
              <LucideTrash2 class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <div
          v-if="row.answer"
          class="flex items-start gap-2 rounded-lg bg-surface-gray-1 px-3 py-2"
        >
          <p class="min-w-0 flex-1 text-p-sm text-ink-gray-8">
            {{ row.answer }}
          </p>
          <TaskyBadge
            :label="row.applied ? __('In the BRD') : __('New')"
            :tone="row.applied ? 'success' : 'info'"
          />
        </div>
      </li>
    </ul>

    <div
      v-if="editable"
      class="flex flex-wrap items-end gap-2 border-t border-outline-gray-1 px-4 py-3"
    >
      <FormControl
        v-model="newSection"
        class="w-full sm:w-56"
        type="select"
        :label="__('Section')"
        :options="sectionOptions"
      />
      <Button :label="__('Add a question')" @click="add">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
      <Button
        class="ml-auto"
        :label="questionsDirty ? __('Save questions') : __('Questions saved')"
        :disabled="!questionsDirty"
        :loading="save.loading"
        @click="saveQuestions"
      />
    </div>

    <Dialog
      v-model:open="showSend"
      :title="__('Send the questionnaire')"
      size="lg"
    >
      <form
        :id="sendFormId"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="sendIt"
      >
        <FormControl
          v-model="sendForm.recipients"
          type="email"
          :label="__('To')"
          :description="
            __(
              'The client gets an email with the link, from the ERP site. It shows only the questions.'
            )
          "
          required
        />
        <FormControl
          v-model="sendForm.message"
          type="textarea"
          :rows="4"
          :label="__('Message')"
          :placeholder="
            __('A short note above the link. Blank: a standard greeting.')
          "
        />
        <p v-if="sendError" role="alert" class="text-p-sm text-danger">
          {{ sendError }}
        </p>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            :form="sendFormId"
            :label="__('Send questionnaire')"
            :loading="send.loading"
            :disabled="!sendForm.recipients.trim()"
          />
        </div>
      </template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  Dialog,
  Dropdown,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideShare2 from "~icons/lucide/share-2";
import LucideTrash2 from "~icons/lucide/trash-2";
import {
  SECTION_LABELS,
  type DocumentQuestion,
  type Proposal,
  type Questionnaire,
  type SectionType,
} from "./proposals";

const props = defineProps<{
  proposal: string;
  questionnaire: Questionnaire;
  /** the BRD's section types the questions may feed */
  sectionTypes: SectionType[];
  canWrite: boolean;
  /** a draft the person may change */
  editable: boolean;
  /** the builder has unsaved changes */
  dirty: boolean;
  leadEmail?: string | null;
}>();
const emit = defineEmits<{ (e: "changed", proposal: Proposal): void }>();
const titleId = `questionnaire-${useId()}`;
const sendFormId = `questionnaire-send-${useId()}`;

const rows = ref<DocumentQuestion[]>([]);
const saved = ref("");
const questionsDirty = computed(
  () => JSON.stringify(rows.value) !== saved.value
);
// the builder hands a new copy after any save: unsaved question edits are kept until
// this panel's own save replaces them
let takeNext = false;
// the rows as sent with the pending save: edits made while it runs are not replaced
let submitted = "";
watch(
  () => props.questionnaire,
  (q) => {
    if (questionsDirty.value && !takeNext) {
      // keep the local edits, but compare them with what the server now has
      saved.value = JSON.stringify(q.questions.map((row) => ({ ...row })));
      return;
    }
    takeNext = false;
    rows.value = q.questions.map((row) => ({ ...row }));
    saved.value = JSON.stringify(rows.value);
  },
  { immediate: true }
);
const answered = computed(
  () => rows.value.filter((row) => (row.answer || "").trim()).length
);

const sectionOptions = computed(() =>
  props.sectionTypes
    .filter(
      (t) =>
        !["Cover", "Acceptance", "Open Questions", "Image", "Custom"].includes(
          t
        )
    )
    .map((t) => ({ label: SECTION_LABELS[t] || t, value: t }))
);
const newSection = ref<SectionType>("Business Objectives");

function add() {
  rows.value.push({ section_type: newSection.value, question: "" });
}

function remove(index: number) {
  rows.value.splice(index, 1);
}

function done(d: Proposal | { proposal: Proposal }) {
  emit("changed", "proposal" in d ? d.proposal : d);
}

const save = createResource({
  url: "helpdesk.api.proposals.save_questions",
  method: "POST",
  onSuccess(p: Proposal) {
    takeNext = JSON.stringify(rows.value) === submitted;
    done(p);
    toast.success(__("Questions saved"));
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't save the questions.")));
  },
});

function saveQuestions() {
  if (save.loading) return;
  submitted = JSON.stringify(rows.value);
  save.submit({
    name: props.proposal,
    questions: rows.value
      .filter((row) => row.question.trim() && !row.answer)
      .map((row) => ({
        section_type: row.section_type,
        question: row.question.trim(),
        asked_by: row.asked_by,
      })),
  });
}

const apply = createResource({
  url: "helpdesk.api.proposals.apply_answers",
  method: "POST",
  onSuccess(d: { proposal: Proposal; sections: string[]; warnings: string[] }) {
    done(d);
    for (const warning of d.warnings ?? []) toast.warning(warning);
    toast.success(
      d.sections.length
        ? __("Updated: {0}", d.sections.join(", "))
        : __("The answers are in the open questions")
    );
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't update the BRD from the answers.")));
  },
});

async function copy(url: string) {
  try {
    await navigator.clipboard.writeText(url);
    toast.success(__("Link copied"));
  } catch {
    toast.info(url);
  }
}

const share = createResource({
  url: "helpdesk.api.proposals.share_questionnaire",
  method: "POST",
  onSuccess(d: { proposal: Proposal; url: string }) {
    done(d);
    copy(d.url);
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't share it.")));
  },
});

const showSend = ref(false);
const sendError = ref("");
const sendForm = reactive({ recipients: "", message: "" });

const shareOptions = computed(() => [
  {
    label: __("Copy link"),
    icon: "link",
    onClick: () =>
      questionsDirty.value
        ? toast.warning(__("Save the questions first"))
        : share.submit({ name: props.proposal }),
  },
  {
    label: __("Send by email"),
    icon: "mail",
    onClick: () => {
      if (questionsDirty.value) {
        toast.warning(__("Save the questions first"));
        return;
      }
      sendForm.recipients = props.leadEmail || "";
      sendForm.message = "";
      sendError.value = "";
      showSend.value = true;
    },
  },
]);

const send = createResource({
  url: "helpdesk.api.proposals.send_questionnaire",
  method: "POST",
  onSuccess(d: { proposal: Proposal; url: string }) {
    done(d);
    showSend.value = false;
    toast.success(__("Sent to {0}", sendForm.recipients));
  },
  onError(e: unknown) {
    sendError.value = errorText(
      e,
      __("Couldn't send it. Check your connection and try again.")
    );
  },
});

function sendIt() {
  if (send.loading) return;
  sendError.value = "";
  send.submit({
    name: props.proposal,
    recipients: sendForm.recipients,
    message: sendForm.message,
  });
}
</script>

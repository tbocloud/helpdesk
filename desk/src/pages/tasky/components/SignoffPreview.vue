<template>
  <section
    class="flex min-h-0 flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-label="__('Preview')"
  >
    <div class="border-b border-outline-gray-1 px-3 py-2">
      <TabButtons
        v-model="tab"
        :aria-label="__('What to preview')"
        :options="[
          { label: __('Mail preview'), value: 'mail' },
          { label: __('Document preview'), value: 'document' },
        ]"
      />
    </div>

    <template v-if="tab === 'mail'">
      <dl
        class="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-outline-gray-1 px-4 py-3 text-sm"
      >
        <dt class="text-ink-gray-5">{{ __("Subject") }}</dt>
        <dd class="text-base-medium text-ink-gray-9">
          {{ mail.subject || "—" }}
        </dd>
        <dt class="text-ink-gray-5">{{ __("To") }}</dt>
        <dd class="min-w-0 truncate text-ink-gray-8">
          <template v-if="mail.toEmail">
            {{ mail.toName }}
            <span class="font-mono text-xs text-ink-gray-6"
              >&lt;{{ mail.toEmail }}&gt;</span
            >
          </template>
          <template v-else>{{ __("Pick who signs off") }}</template>
        </dd>
        <template v-if="mail.cc.length">
          <dt class="text-ink-gray-5">{{ __("CC") }}</dt>
          <dd class="min-w-0 break-words font-mono text-xs text-ink-gray-7">
            {{ mail.cc.join(", ") }}
          </dd>
        </template>
      </dl>
      <!-- the body as the customer sees it; a sandbox runs nothing and keeps the app's styles out -->
      <iframe
        :title="__('Mail body')"
        sandbox=""
        :srcdoc="mailDoc"
        class="min-h-[420px] w-full flex-1 bg-white"
      />
    </template>

    <template v-else>
      <TaskyState
        v-if="documentError"
        error
        :icon="LucideCircleAlert"
        :title="__('Couldn\'t show the document')"
        :message="documentError"
      >
        <Button :label="__('Try again')" @click="loadDocument" />
      </TaskyState>
      <div
        v-else-if="!documentHtml"
        class="m-4 h-96 animate-pulse rounded bg-surface-gray-1"
        aria-busy="true"
        :aria-label="__('Loading')"
      />
      <iframe
        v-else
        :title="__('Sign-off document')"
        sandbox=""
        :srcdoc="documentHtml"
        class="min-h-[640px] w-full flex-1 bg-white"
      />
    </template>
  </section>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDebounceFn } from "@vueuse/core";
import { Button, TabButtons, call } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";

const props = defineProps<{
  mail: {
    subject: string;
    toName: string;
    toEmail: string;
    cc: string[];
    body: string;
  };
  /** a saved sign-off: its document as it goes out */
  signoff?: string | null;
  /** a sign-off not saved yet: what the form has, to show its document */
  unsaved?: {
    project: string;
    lead?: string | null;
    values: Record<string, unknown>;
  } | null;
}>();

const tab = ref<"mail" | "document">("mail");

const mailDoc = computed(
  () =>
    `<!doctype html><html><head><meta charset="utf-8"><style>
      body{font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;font-size:14px;
      line-height:1.55;color:#1f2430;margin:16px;overflow-wrap:anywhere}
      a{color:#3A748D}</style></head><body>${
        props.mail.body || ""
      }</body></html>`
);

const documentHtml = ref("");
const documentError = ref("");
// an answer for older values must not land over the newest one
let asked = 0;
async function loadDocument() {
  if (tab.value !== "document") return;
  const ask = ++asked;
  documentError.value = "";
  try {
    const html: string = props.signoff
      ? await call("helpdesk.api.project_signoff.preview_signoff_document", {
          signoff: props.signoff,
        })
      : await call(
          "helpdesk.api.project_signoff.preview_new_signoff_document",
          {
            project: props.unsaved?.project,
            lead: props.unsaved?.lead || null,
            values: props.unsaved?.values ?? {},
          }
        );
    if (ask === asked) documentHtml.value = html;
  } catch (e) {
    if (ask === asked)
      documentError.value = errorText(e, __("Check your connection."));
  }
}
const loadSoon = useDebounceFn(loadDocument, 600);
watch(tab, loadDocument);
watch(
  () => [props.signoff, JSON.stringify(props.unsaved?.values ?? null)],
  () => loadSoon()
);
</script>

<template>
  <section
    class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    :aria-labelledby="titleId"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 :id="titleId" class="text-base-medium text-ink-gray-9">
        {{ __("WhatsApp") }}
      </h2>
      <a
        v-if="box.chat_url"
        :href="box.chat_url"
        target="_blank"
        rel="noopener"
        class="inline-flex items-center gap-1 rounded text-p-sm text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      >
        {{ __("Open in TBO Chat") }}
        <LucideExternalLink class="size-3.5" aria-hidden="true" />
      </a>
    </div>

    <p v-if="whatsapp.blocked" role="status" class="text-p-sm text-ink-gray-7">
      {{ whatsapp.blocked }}
    </p>

    <p v-else-if="!box.chat_ready" class="text-p-sm text-ink-gray-7">
      {{
        __(
          "WhatsApp isn't connected to TBO Chat yet, so messages are sent from your own phone."
        )
      }}
    </p>

    <form
      v-else-if="canWrite && whatsapp.window_open"
      class="flex flex-col gap-2"
      @submit.prevent="send"
    >
      <p class="text-p-sm text-ink-gray-7">
        {{
          __("They wrote recently, so you can reply freely until {0}.", until)
        }}
      </p>
      <FormControl
        v-model="text"
        type="textarea"
        :rows="3"
        :label="__('Reply on WhatsApp')"
      />
      <div class="flex justify-end">
        <Button
          type="submit"
          variant="solid"
          :label="__('Send on WhatsApp')"
          :loading="reply.loading"
          :disabled="!text.trim()"
        />
      </div>
    </form>

    <form
      v-else-if="canWrite && box.templates.length"
      class="flex flex-col gap-2"
      @submit.prevent="send"
    >
      <p class="text-p-sm text-ink-gray-7">
        {{ box.hint }}
        {{
          whatsapp.last_in
            ? __("They last wrote more than 24 hours ago.")
            : __("They haven't written to us yet.")
        }}
      </p>
      <FormControl
        v-if="box.templates.length > 1"
        v-model="template"
        type="select"
        :label="__('Message to send')"
        :options="templateOptions"
      />
      <p
        class="whitespace-pre-wrap rounded bg-surface-gray-1 px-3 py-2 text-p-sm text-ink-gray-9"
      >
        {{ chosen?.preview }}
      </p>
      <div class="flex justify-end">
        <Button
          type="submit"
          variant="solid"
          :label="__('Send this template')"
          :loading="reply.loading"
        />
      </div>
    </form>

    <p v-else-if="canWrite" class="text-p-sm text-ink-gray-7">
      {{ box.hint }}
      {{
        __(
          "Ask an admin to add an approved template in Settings → TBO Chat to message from here."
        )
      }}
    </p>

    <p v-if="error" role="alert" class="text-p-sm text-danger">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, FormControl, toast } from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucideExternalLink from "~icons/lucide/external-link";
import type { LeadWhatsApp, LeadWhatsAppBox } from "./leads";

const props = defineProps<{
  leadId: string;
  whatsapp: LeadWhatsApp;
  box: LeadWhatsAppBox;
  canWrite: boolean;
}>();
const emit = defineEmits<{ sent: [] }>();

const titleId = `lead-whatsapp-${useId()}`;
const text = ref("");
const error = ref("");
const template = ref(
  (props.box.templates.find((t) => t.is_default) || props.box.templates[0])
    ?.name || ""
);

const templateOptions = computed(() =>
  props.box.templates.map((t) => ({ label: t.name, value: t.name }))
);
const chosen = computed(() =>
  props.box.templates.find((t) => t.name === template.value)
);
const until = computed(() =>
  props.whatsapp.window_ends
    ? dayjs(props.whatsapp.window_ends).format("D MMM, h:mm a")
    : ""
);

const reply = createResource({
  url: "helpdesk.api.whatsapp.reply",
  method: "POST",
  makeParams() {
    return props.whatsapp.window_open
      ? { lead: props.leadId, text: text.value.trim() }
      : { lead: props.leadId, template: template.value };
  },
  onSuccess() {
    text.value = "";
    toast.success(__("Sent on WhatsApp"));
    emit("sent");
  },
  onError(e: unknown) {
    error.value = errorText(e, __("It wasn't sent. Try again."));
  },
});

function send() {
  error.value = "";
  reply.submit();
}
</script>

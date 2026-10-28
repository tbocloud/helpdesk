<template>
  <SettingsSection
    :title="__('Website lead form')"
    :description="
      __(
        'Leads from a form on the company website go straight to the ERP site, which files them and gives each to its department\'s next member. Nothing to set up here: paste the snippet into the website.'
      )
    "
  >
    <p
      v-if="!base"
      class="flex items-center gap-2 rounded-md bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-7"
    >
      <LucideInfo class="size-4 shrink-0" aria-hidden="true" />
      {{ __("Save the CRM site URL above to get the endpoint.") }}
    </p>
    <template v-else>
      <div class="flex flex-col gap-1.5">
        <FormLabel :label="__('Endpoint')" size="md" />
        <code
          class="break-all rounded-md bg-surface-gray-2 px-3 py-2 font-mono text-p-sm text-ink-gray-8"
          >{{ endpoint }}</code
        >
      </div>
      <div class="flex flex-col gap-1.5">
        <div class="flex items-center justify-between gap-2">
          <FormLabel :label="__('HTML snippet')" size="md" />
          <Button :label="__('Copy snippet')" @click="copy">
            <template #prefix>
              <LucideCopy class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <pre
          class="max-h-64 overflow-auto rounded-md bg-surface-gray-2 px-3 py-2 font-mono text-p-xs text-ink-gray-8"
          tabindex="0"
          :aria-label="__('HTML snippet')"
          >{{ snippet }}</pre
        >
      </div>
    </template>
    <p class="flex items-start gap-2 text-p-sm text-ink-gray-6">
      <LucideMail class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      {{
        __(
          "Emails BCC'd to the logging address are filed on the matching lead's timeline. The address is set on the ERP site, in TBO Smart Settings."
        )
      }}
    </p>
  </SettingsSection>
</template>

<script setup lang="ts">
import { copyText } from "@/pages/leads/leads";
import { __ } from "@/translation";
import { Button, FormLabel, toast } from "frappe-ui";
import { computed } from "vue";
import LucideCopy from "~icons/lucide/copy";
import LucideInfo from "~icons/lucide/info";
import LucideMail from "~icons/lucide/mail";
import SettingsSection from "../SettingsSection.vue";

const props = defineProps<{
  /** the CRM site URL as saved in the connection */
  siteUrl: string;
}>();

const base = computed(() => props.siteUrl.trim().replace(/\/+$/, ""));
const endpoint = computed(
  () => `${base.value}/api/method/tbo_smart.api.hub_leads.submit_website_lead`
);

const snippet = computed(
  () => `<form method="POST" action="${endpoint.value}">
  <input name="lead_name" placeholder="Your name" required />
  <input name="company_name" placeholder="Company" />
  <input name="email_id" type="email" placeholder="Email" />
  <input name="mobile_no" type="tel" placeholder="Mobile" />
  <textarea name="message" placeholder="How can we help?"></textarea>
  <button type="submit">Send</button>
</form>`
);

async function copy() {
  if (await copyText(snippet.value)) toast.success(__("Snippet copied"));
  else toast.error(__("Couldn't copy. Select the snippet and copy it."));
}
</script>

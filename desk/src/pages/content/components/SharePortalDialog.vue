<template>
  <Dialog v-model:open="open" :options="{ size: 'lg' }">
    <template #body-title>
      <h3 class="text-xl-semibold text-ink-gray-9">
        {{ __("Send client portal email") }}
      </h3>
    </template>
    <template #body-content>
      <form
        id="share-portal-form"
        class="flex flex-col gap-4"
        @submit.prevent="submit"
      >
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "The client gets the portal link and a 6-digit code by email. They sign in to review, approve and comment on posts that are in Client Review."
            )
          }}
        </p>

        <Link
          v-model="customer"
          doctype="HD Customer"
          :label="__('Customer') + ' *'"
          :placeholder="__('Select customer')"
        />

        <div
          v-if="customer && access.loading && !access.data"
          class="h-20 animate-pulse rounded bg-surface-gray-2"
        />
        <div
          v-else-if="access.error"
          class="text-p-sm text-danger"
          role="alert"
        >
          {{ access.error.messages?.[0] || __("Couldn't load portal access") }}
        </div>

        <template v-else-if="customer && access.data">
          <div
            v-if="!access.data.enabled"
            class="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2.5 text-p-sm text-warning"
            role="status"
          >
            <LucideCircleAlert
              class="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            {{
              __(
                "The client portal is turned off. Turn it on in Settings → Content."
              )
            }}
          </div>

          <template v-else>
            <FormControl
              v-if="access.data.emails.length"
              v-model="choice"
              type="select"
              :label="__('Send to')"
              :options="[
                ...access.data.emails,
                { label: __('Another email…'), value: OTHER },
              ]"
            />
            <FormControl
              v-if="choice === OTHER || !access.data.emails.length"
              v-model="typedEmail"
              type="email"
              :label="access.data.emails.length ? __('Email') : __('Send to')"
              :placeholder="__('client@company.com')"
              :description="
                __('Saved as a contact of {0} so they can sign in.', customer)
              "
              required
            />

            <p class="text-p-sm text-ink-gray-5">
              <span class="font-mono tabular-nums">{{
                access.data.posts_in_review
              }}</span>
              {{
                access.data.posts_in_review === 1
                  ? __("post is waiting for their review.")
                  : __("posts are waiting for their review.")
              }}
              <template v-if="!access.data.posts_in_review">
                {{
                  __(
                    "Move posts to Client Review so they show up for approval."
                  )
                }}
              </template>
            </p>
          </template>
        </template>

        <div
          v-if="access.data?.portal_url"
          class="flex flex-col gap-1.5 border-t border-outline-gray-2 pt-4"
        >
          <span class="text-xs text-ink-gray-5">{{ __("Portal link") }}</span>
          <div class="flex flex-wrap items-center gap-2">
            <code
              class="min-w-0 flex-1 truncate rounded bg-surface-gray-2 px-2.5 py-1.5 font-mono text-sm text-ink-gray-8"
              >{{ access.data.portal_url }}</code
            >
            <Button :label="__('Copy')" @click="copyLink">
              <template #prefix
                ><LucideCopy class="size-4" aria-hidden="true"
              /></template>
            </Button>
            <Button :label="__('Open portal')" :link="access.data.portal_url">
              <template #prefix
                ><LucideExternalLink class="size-4" aria-hidden="true"
              /></template>
            </Button>
          </div>
        </div>

        <ErrorMessage :message="error" />
      </form>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Close')" @click="open = false" />
        <Button
          variant="solid"
          type="submit"
          form="share-portal-form"
          :label="__('Send email')"
          :loading="send.loading"
          :disabled="!canSend"
        >
          <template #prefix
            ><LucideMail class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import { __ } from "@/translation";
import {
  Button,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCopy from "~icons/lucide/copy";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideMail from "~icons/lucide/mail";

interface PortalAccess {
  enabled: boolean;
  emails: string[];
  posts_in_review: number;
  portal_url: string;
}

const OTHER = "__other__";

const props = defineProps<{ customer?: string }>();
const open = defineModel<boolean>("open", { default: false });

const customer = ref("");
const choice = ref("");
const typedEmail = ref("");
const error = ref("");

const access = createResource({
  url: "helpdesk.api.content_portal.get_portal_access",
  makeParams: () => ({ customer: customer.value }),
  onSuccess(data: PortalAccess) {
    choice.value = data.emails[0] || OTHER;
  },
});

const email = computed(() =>
  choice.value === OTHER || !access.data?.emails.length
    ? typedEmail.value.trim()
    : choice.value
);
const canSend = computed(
  () => !!customer.value && !!access.data?.enabled && !!email.value
);

let loadedFor: string | null = null;
function load(value: string) {
  if (value === loadedFor) return;
  loadedFor = value;
  error.value = "";
  access.reset();
  if (value) access.reload();
}

watch(open, (isOpen) => {
  if (!isOpen) return;
  typedEmail.value = "";
  loadedFor = null;
  customer.value = props.customer || "";
  load(customer.value);
});

watch(customer, (value) => open.value && load(value));

const send = createResource({
  url: "helpdesk.api.content_portal.send_portal_access",
  onSuccess(data: { success: boolean; message: string }) {
    if (!data.success) {
      error.value = data.message;
      return;
    }
    toast.success(__("Portal email sent to {0}", email.value));
    open.value = false;
  },
  onError(e: { messages?: string[] }) {
    error.value = e.messages?.[0] || __("Couldn't send the email");
  },
});

function submit() {
  error.value = "";
  if (!canSend.value) return;
  send.submit({ customer: customer.value, email: email.value });
}

async function copyLink() {
  try {
    await navigator.clipboard.writeText(access.data.portal_url);
    toast.success(__("Link copied"));
  } catch {
    toast.error(__("Couldn't copy. Select the link and copy it yourself."));
  }
}
</script>

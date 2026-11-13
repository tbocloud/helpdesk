<template>
  <Dialog
    :open="open"
    :title="title"
    size="3xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <TaskyState
      v-if="options.error"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the form')"
      :message="
        errorText(options.error, __('Check your connection, then try again.'))
      "
    >
      <Button :label="__('Try again')" @click="options.reload()" />
    </TaskyState>

    <div
      v-else-if="!options.data"
      class="flex flex-col gap-4"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div v-for="i in 4" :key="i" class="flex flex-col gap-1.5">
        <div class="h-3 w-24 animate-pulse rounded bg-surface-gray-2" />
        <div class="h-8 w-full animate-pulse rounded bg-surface-gray-1" />
      </div>
    </div>

    <div
      v-else-if="!options.data.customer"
      role="alert"
      class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-warning"
    >
      <LucideTriangleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{{
        __(
          "This project has no customer. Set the customer on the project first; the person who signs off must be one of its contacts."
        )
      }}</span>
    </div>

    <form
      v-else
      :id="formId"
      class="flex flex-col gap-6"
      novalidate
      @submit.prevent="editing ? submit(false) : askToSend()"
    >
      <p v-if="isUat && !editing" class="text-p-sm text-ink-gray-6">
        {{
          __(
            "A test case for each requirement of the approved SRS on the ERP site: its steps and the expected result. The client marks each Pass or Fail; a Fail becomes an issue for the team."
          )
        }}
      </p>

      <!-- what is signed off -->
      <section class="flex flex-col gap-3" :aria-labelledby="`${formId}-setup`">
        <h3 :id="`${formId}-setup`" class="text-base-medium text-ink-gray-9">
          {{ __("Sign-off setup") }}
        </h3>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div class="flex flex-col gap-1.5">
            <span class="text-xs text-ink-gray-5">{{
              __("Project type")
            }}</span>
            <span
              class="flex h-7 items-center rounded border border-dashed border-outline-gray-2 px-2 text-base text-ink-gray-8"
              >{{
                options.data.project_type
                  ? __(options.data.project_type)
                  : __("Not set")
              }}</span
            >
          </div>
          <FormControl
            v-if="!editing"
            v-model="form.template"
            type="select"
            :label="__('Sign-off template')"
            :options="templateOptions"
            :description="
              __(
                'Mail content and questions are copied in; you can change them before sending.'
              )
            "
            @update:model-value="onTemplate"
          />
          <TextInput
            v-if="!isUat"
            v-model="form.module_title"
            :label="__('Module')"
            :placeholder="__('e.g. Accounts')"
            maxlength="140"
            required
          />
          <TextInput
            v-if="!isUat"
            v-model="form.training_date"
            type="date"
            :label="__('Training date')"
          />
          <!-- Combobox layers inside the dialog, so Escape and clicking outside still close it -->
          <Combobox
            :label="isUat ? __('Tests with the client') : __('Trainer')"
            :options="trainerOptions"
            :placeholder="__('Pick from the project team')"
            :model-value="form.trainer || null"
            @update:model-value="(v: string | null) => (form.trainer = v || '')"
          />
        </div>
      </section>

      <!-- who it goes to -->
      <section
        class="flex flex-col gap-3"
        :aria-labelledby="`${formId}-customer`"
      >
        <h3 :id="`${formId}-customer`" class="text-base-medium text-ink-gray-9">
          {{ __("Customer") }}
          <span class="ml-1 text-base text-ink-gray-6">{{
            options.data.customer
          }}</span>
        </h3>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div class="flex flex-col gap-1.5">
            <Combobox
              :label="__('Signs off for the customer (To)')"
              :options="contactOptions"
              :placeholder="__('Pick a contact with an email')"
              :empty-text="__('No contacts with an email')"
              :model-value="form.signatory_contact || null"
              @update:model-value="
                (v: string | null) => (form.signatory_contact = v || '')
              "
            />
            <p class="text-p-xs text-ink-gray-5">
              <template v-if="options.data.contacts.length">
                {{
                  __(
                    "Only this person gets the link and the one-time code, and only they can sign."
                  )
                }}
              </template>
              <template v-else>
                {{
                  __(
                    "{0} has no contacts with an email yet.",
                    options.data.customer
                  )
                }}
                <router-link
                  :to="{
                    name: 'Customer',
                    params: { id: options.data.customer },
                  }"
                  class="rounded text-ink-gray-8 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  >{{ __("Add contacts to the customer") }}</router-link
                >
              </template>
            </p>
          </div>
          <FormControl
            v-model="form.cc"
            type="text"
            :label="__('CC')"
            :placeholder="__('name@company.com, name2@company.com')"
            :description="
              __('Comma separated. The project lead and you, to start with.')
            "
          />
        </div>
      </section>

      <!-- the mail the customer gets -->
      <section class="flex flex-col gap-3" :aria-labelledby="`${formId}-mail`">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 :id="`${formId}-mail`" class="text-base-medium text-ink-gray-9">
            {{ __("Mail content") }}
          </h3>
          <span
            v-if="previewing"
            class="text-xs text-ink-gray-5"
            aria-live="polite"
            >{{ __("Filling in…") }}</span
          >
          <Button
            v-else-if="mailEdited && !confirmReapply"
            variant="ghost"
            size="sm"
            :label="__('Reapply template')"
            @click="confirmReapply = true"
          />
        </div>
        <div
          v-if="confirmReapply"
          class="flex flex-wrap items-center gap-2 rounded-md bg-surface-gray-1 px-3 py-2 text-p-sm text-ink-gray-8"
          role="alert"
        >
          <span class="flex-1">{{
            __("Reapply the template? Your changes to the mail are lost.")
          }}</span>
          <Button
            size="sm"
            :label="__('Keep my text')"
            @click="confirmReapply = false"
          />
          <Button
            size="sm"
            variant="solid"
            :label="__('Reapply')"
            @click="reapply"
          />
        </div>
        <TextInput
          v-model="form.subject"
          :label="__('Subject')"
          maxlength="240"
          required
        />
        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-ink-gray-5">{{ __("Mail body") }}</span>
          <CompactEditor
            v-model="form.body"
            type="Email"
            min-height="min-h-[180px]"
            max-height="max-h-72"
          />
          <p class="text-p-xs text-ink-gray-5">{{ linkHint }}</p>
        </div>
        <div
          v-if="mailError"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span class="flex-1">{{ mailError }}</span>
          <Button size="sm" :label="__('Try again')" @click="reapply" />
        </div>
        <p
          v-else-if="unfilled.length && detailsPicked"
          class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-ink-gray-9"
        >
          <LucideTriangleAlert
            class="mt-0.5 size-4 shrink-0 text-warning"
            aria-hidden="true"
          />
          <span>{{
            __("Fill {0}: it is used in the mail.", unfilled.join(", "))
          }}</span>
        </p>
      </section>

      <section v-if="editing" class="flex flex-col gap-2">
        <h3 class="text-base-medium text-ink-gray-9">{{ __("Questions") }}</h3>
        <SignoffQuestionsEditor v-model="form.items" />
      </section>

      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button :label="__('Cancel')" @click="close" />
        <template v-if="options.data?.customer">
          <Button
            v-if="editing"
            variant="solid"
            :label="__('Save changes')"
            :loading="saving === 'draft'"
            @click="submit(false)"
          />
          <template v-else>
            <Button
              :label="__('Save as draft')"
              :loading="saving === 'draft'"
              :disabled="!!saving"
              @click="submit(false)"
            />
            <!-- the reason it can't go yet is its tooltip and, on a phone, under it -->
            <Button
              variant="solid"
              :label="__('Send to customer')"
              :disabled="!!sendBlocked || !!saving"
              :title="sendBlocked || undefined"
              @click="askToSend"
            >
              <template #prefix>
                <LucideSend class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </template>
        </template>
      </div>
      <p
        v-if="!editing && options.data?.customer && sendBlocked"
        class="mt-2 text-right text-p-xs text-ink-gray-6"
      >
        {{ sendBlocked }}
      </p>
    </template>
  </Dialog>

  <!-- the mail goes to a customer: who gets it, said once more -->
  <Dialog
    v-model:open="confirmSend"
    :title="__('Send the sign-off?')"
    size="sm"
  >
    <div class="flex flex-col gap-2 text-p-base text-ink-gray-8">
      <p>
        {{
          __(
            "The mail goes to {0} ({1}) with their link to sign.",
            signatory?.full_name || "",
            signatory?.email || ""
          )
        }}
      </p>
      <p v-if="ccList.length" class="text-p-sm text-ink-gray-6">
        {{ __("CC: {0}", ccList.join(", ")) }}
      </p>
    </div>
    <div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      <Button :label="__('Back')" @click="confirmSend = false" />
      <Button
        variant="solid"
        :label="__('Send')"
        :loading="saving === 'send'"
        @click="submit(true)"
      />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import CompactEditor from "@/components/CompactEditor.vue";
import SignoffQuestionsEditor from "@/components/SignoffQuestionsEditor.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDebounceFn } from "@vueuse/core";
import {
  Button,
  Combobox,
  Dialog,
  FormControl,
  TextInput,
  call,
  createResource,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideSend from "~icons/lucide/send";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import { unfilledPlaceholders, type SignoffQuestion } from "../signoffMeta";

/** The sign-off being edited (Draft or Reopened); without it the dialog creates one. */
export interface SignoffDraft {
  name: string;
  module_title: string;
  signoff_type?: "Training" | "UAT";
  template?: string | null;
  training_date?: string | null;
  trainer?: string | null;
  signatory_contact?: string | null;
  email_subject?: string | null;
  email_body?: string | null;
  cc_emails?: string | null;
  items: SignoffQuestion[];
}

interface Template {
  name: string;
  template_name: string;
  module?: string;
  signoff_type?: "Training" | "UAT";
  project_type?: string | null;
}

interface Contact {
  contact: string;
  full_name: string;
  email: string;
  designation?: string | null;
}

interface Mail {
  subject: string;
  body: string;
  cc: string[];
}

const props = defineProps<{
  open: boolean;
  projectId: string;
  signoff?: SignoffDraft | null;
  /** a UAT: its tests come from the SRS of the plan the project was made from */
  uat?: boolean;
  /** opened from this lead's page: its owner may send it without opening the project */
  lead?: string | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  /** saved (`sent`: and sent to the customer) */
  saved: [name: string, sent: boolean];
}>();

const formId = `signoff-form-${useId()}`;
const editing = computed(() => !!props.signoff);
// a new UAT, or editing one
const isUat = computed(
  () => props.uat || props.signoff?.signoff_type === "UAT"
);
const title = computed(() =>
  editing.value
    ? __("Edit sign-off")
    : isUat.value
    ? __("New UAT sign-off")
    : __("New sign-off")
);
// written here: a "}}" inside the template's {{ }} would end it
const linkHint = __(
  "The customer's link to sign goes where {0} is, or at the end, with how the one-time code works.",
  "{{ sign_off_link }}"
);
const errorMessage = ref("");

const form = reactive({
  template: "",
  module_title: "",
  training_date: "",
  trainer: "",
  signatory_contact: "",
  cc: "",
  subject: "",
  body: "",
  items: [] as SignoffQuestion[],
});

// the mail's state; the watcher below sets it when the dialog opens
const baseline = ref({ subject: "", body: "" });
// the mail follows the choices above until it is written by hand (or kept from a draft)
const autoFill = ref(true);
const previewing = ref(false);
const mailError = ref("");
const confirmReapply = ref(false);

const options = createResource({
  url: "helpdesk.api.project_signoff.get_signoff_form",
  makeParams: () => ({ project: props.projectId, lead: props.lead || null }),
  onSuccess(data: { default_cc: string[]; templates: Template[] }) {
    if (editing.value) {
      // a draft made before mails were kept starts from its template's
      if (!form.subject) refreshMail(true);
      return;
    }
    form.cc = data.default_cc.join(", ");
    // a UAT starts on the first UAT template that fits the project, if any
    if (isUat.value) form.template = fitting.value[0]?.name ?? "";
    refreshMail(true);
  },
});

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    errorMessage.value = "";
    mailError.value = "";
    confirmReapply.value = false;
    const s = props.signoff;
    Object.assign(form, {
      template: s?.template ?? "",
      module_title: s?.module_title ?? "",
      training_date: s?.training_date ?? "",
      trainer: s?.trainer ?? "",
      signatory_contact: s?.signatory_contact ?? "",
      cc: s?.cc_emails ?? "",
      subject: s?.email_subject ?? "",
      body: s?.email_body ?? "",
      items: s ? s.items.map((i) => ({ ...i })) : [],
    });
    baseline.value = { subject: form.subject, body: form.body };
    // a draft's own mail is kept; only a new one follows the template
    autoFill.value = !s?.email_subject;
    options.reload();
  },
  { immediate: true }
);

// the templates for this kind of sign-off and this project's type (or any type)
const fitting = computed<Template[]>(() => {
  const kind = isUat.value ? "UAT" : "Training";
  const type = options.data?.project_type;
  return (options.data?.templates ?? []).filter(
    (t: Template) =>
      (t.signoff_type || "Training") === kind &&
      (!t.project_type || !type || t.project_type === type)
  );
});

const templateOptions = computed(() => [
  ...fitting.value.map((t) => ({ label: t.template_name, value: t.name })),
  {
    label: isUat.value
      ? __("No template: the standard UAT mail")
      : __("No template: start empty"),
    value: "",
  },
]);

const trainerOptions = computed(() =>
  (options.data?.team ?? []).map((m: { user: string; full_name: string }) => ({
    label: m.full_name || m.user,
    value: m.user,
    description: m.user,
  }))
);

const contacts = computed<Contact[]>(() => options.data?.contacts ?? []);
const contactOptions = computed(() =>
  contacts.value.map((c) => ({
    label: c.full_name,
    value: c.contact,
    description: [c.designation, c.email].filter(Boolean).join(" · "),
  }))
);
const signatory = computed(() =>
  contacts.value.find((c) => c.contact === form.signatory_contact)
);
const ccList = computed(() =>
  form.cc
    .split(/[,;\s]+/)
    .map((e) => e.trim())
    .filter(Boolean)
);

function onTemplate(name: string) {
  const t = fitting.value.find((x) => x.name === name);
  // suggest the template's module, without overwriting what was typed
  if (t?.module && !form.module_title.trim()) form.module_title = t.module;
}

// ---------- the mail: filled in from the template, until it is changed by hand ----------

/** The words of an HTML body, so the editor tidying its markup isn't "changed by hand". */
function words(html: string) {
  const text =
    new DOMParser().parseFromString(html || "", "text/html").body.textContent ||
    "";
  return text.replace(/\s+/g, " ").trim();
}
const mailEdited = computed(
  () =>
    form.subject.trim() !== baseline.value.subject.trim() ||
    words(form.body) !== words(baseline.value.body)
);

// an answer for older choices must not land over the newest one
let asked = 0;
async function refreshMail(force = false) {
  if (!options.data?.customer) return;
  if (!force && (!autoFill.value || mailEdited.value)) return;
  const ask = ++asked;
  previewing.value = true;
  mailError.value = "";
  try {
    const mail: Mail = await call(
      "helpdesk.api.project_signoff.preview_signoff_mail",
      {
        project: props.projectId,
        signoff_type: isUat.value ? "UAT" : "Training",
        template: form.template || null,
        signatory_contact: form.signatory_contact || null,
        module_title: form.module_title,
        training_date: form.training_date || null,
        trainer: form.trainer || null,
        lead: props.lead || null,
      }
    );
    if (ask !== asked) return;
    form.subject = mail.subject;
    form.body = mail.body;
    baseline.value = { subject: mail.subject, body: mail.body };
    autoFill.value = true;
    // the template's own CC join who is already copied
    const cc = new Set(ccList.value.map((e) => e.toLowerCase()));
    form.cc = [...ccList.value, ...mail.cc.filter((e) => !cc.has(e))].join(
      ", "
    );
  } catch (e) {
    if (ask === asked)
      mailError.value = errorText(e, __("Couldn't fill in the mail."));
  } finally {
    if (ask === asked) previewing.value = false;
  }
}
const refreshSoon = useDebounceFn(() => refreshMail(), 300);
watch(
  () => [
    form.template,
    form.signatory_contact,
    form.module_title,
    form.training_date,
    form.trainer,
  ],
  () => props.open && options.data && refreshSoon()
);

function reapply() {
  confirmReapply.value = false;
  refreshMail(true);
}

const labels = computed<Record<string, string>>(
  () => options.data?.placeholder_labels ?? {}
);
/** What the mail still needs, in the words of the fields that fill it. */
const unfilled = computed(() =>
  unfilledPlaceholders(`${form.subject} ${form.body}`).map(
    (name) => labels.value[name] || `{{ ${name} }}`
  )
);

// ---------- saving and sending ----------

// who signs, the trainer and the module: until they are picked, the mail's gaps are theirs
const detailsPicked = computed(
  () =>
    !!form.signatory_contact &&
    !!form.trainer &&
    (isUat.value || !!form.module_title.trim())
);

/** Why it can't be sent yet, in words; "" when it can. */
const sendBlocked = computed(() => {
  if (!form.signatory_contact)
    return __("Pick who signs off for the customer.");
  if (!isUat.value && !form.module_title.trim())
    return __("Name the module, e.g. Accounts.");
  if (!form.trainer)
    return isUat.value
      ? __("Pick who tests with the client.")
      : __("Pick the trainer.");
  if (previewing.value) return __("Filling in the mail…");
  if (!form.subject.trim() || !words(form.body))
    return __("Write the mail's subject and message.");
  if (unfilled.value.length)
    return __("Fill {0}: it is used in the mail.", unfilled.value.join(", "));
  return "";
});

const confirmSend = ref(false);
function askToSend() {
  if (sendBlocked.value) {
    errorMessage.value = sendBlocked.value;
    return;
  }
  errorMessage.value = "";
  confirmSend.value = true;
}

const saving = ref<"" | "draft" | "send">("");

async function submit(send: boolean) {
  const draftReady =
    (isUat.value || !!form.module_title.trim()) &&
    !!form.trainer &&
    !!form.signatory_contact &&
    (!editing.value || form.items.every((i) => i.question.trim()));
  if (!draftReady) {
    confirmSend.value = false;
    errorMessage.value = editing.value
      ? __(
          "Fill in the module, trainer and signatory, and give every question some text."
        )
      : isUat.value
      ? __("Pick who tests with the client and who signs.")
      : __("Fill in the module, trainer and signatory.");
    return;
  }
  errorMessage.value = "";
  const mail = {
    email_subject: form.subject.trim(),
    email_body: words(form.body) ? form.body : "",
    cc_emails: ccList.value.join(", "),
  };
  const common = {
    module_title: form.module_title.trim(),
    training_date: form.training_date || null,
    trainer: form.trainer,
    signatory_contact: form.signatory_contact,
  };
  const how = { send: send ? 1 : 0, lead: props.lead || null };
  saving.value = send ? "send" : "draft";
  try {
    const data: { name: string } = editing.value
      ? await call("helpdesk.api.project_signoff.update_signoff", {
          signoff: props.signoff!.name,
          items: form.items,
          ...common,
          ...mail,
        })
      : isUat.value
      ? await call("helpdesk.api.project_signoff.create_uat_signoff", {
          project: props.projectId,
          trainer: form.trainer,
          signatory_contact: form.signatory_contact,
          template: form.template || null,
          ...mail,
          ...how,
        })
      : await call("helpdesk.api.project_signoff.create_signoff", {
          project: props.projectId,
          template: form.template || null,
          ...common,
          ...mail,
          ...how,
        });
    toast.success(
      send
        ? __("Sent to {0}", signatory.value?.full_name || "")
        : editing.value
        ? __("Sign-off saved")
        : __("Saved as a draft")
    );
    confirmSend.value = false;
    emit("update:open", false);
    emit("saved", data.name, send);
  } catch (e) {
    // nothing was saved: what was typed stays, to fix and send again
    confirmSend.value = false;
    errorMessage.value = errorText(
      e,
      send
        ? __("Couldn't send the sign-off.")
        : __("Couldn't save the sign-off.")
    );
  } finally {
    saving.value = "";
  }
}
</script>

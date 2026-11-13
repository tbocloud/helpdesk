<template>
  <div class="flex flex-col gap-6">
    <p v-if="f.fromPlan && !f.editing" class="text-p-sm text-ink-gray-6">
      {{
        __(
          "A test case for each requirement of the approved SRS on the ERP site: its steps and the expected result. The client marks each Pass or Fail; a Fail becomes an issue for the team."
        )
      }}
    </p>

    <!-- what is signed off -->
    <section class="flex flex-col gap-3" :aria-labelledby="`${id}-setup`">
      <h3 :id="`${id}-setup`" class="text-base-medium text-ink-gray-9">
        {{ __("Sign-off setup") }}
      </h3>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div v-if="f.data?.project_type" class="flex flex-col gap-1.5">
          <span class="text-xs text-ink-gray-5">{{ __("Project type") }}</span>
          <span
            class="flex h-7 items-center rounded border border-dashed border-outline-gray-2 px-2 text-base text-ink-gray-8"
            >{{ __(f.data.project_type) }}</span
          >
        </div>
        <!-- a project without a type: picked here only to narrow the templates -->
        <FormControl
          v-else
          v-model="f.pickedType"
          type="select"
          :label="__('Project type')"
          :options="projectTypeOptions(__('Any type'))"
          :description="
            __('The project has no type; this only narrows the templates.')
          "
        />
        <FormControl
          v-model="f.form.template"
          type="select"
          :label="__('Sign-off template')"
          :options="f.templateOptions"
          :disabled="f.editing"
          :description="
            __(
              'Mail content and questions are copied in; you can change them before sending.'
            )
          "
          @update:model-value="f.onTemplate"
        />
        <!-- a training made without a stage names its module; a stage picks modules -->
        <TextInput
          v-if="f.namesModule"
          v-model="f.form.module_title"
          :label="__('Module')"
          :placeholder="__('e.g. Accounts')"
          maxlength="140"
          required
        />
        <!-- a UAT from the plan: who tests with the client -->
        <SignoffDetailField v-if="uatTester" :f="f" field="trainer" compact />
        <!-- the stage's details the dialog asks for (the full page has them all, below) -->
        <template v-if="!tall">
          <SignoffDetailField
            v-for="field in f.dialogFields"
            :key="field"
            :f="f"
            :field="field"
            compact
          />
        </template>
      </div>
    </section>

    <!-- who it goes to -->
    <section class="flex flex-col gap-3" :aria-labelledby="`${id}-customer`">
      <h3 :id="`${id}-customer`" class="text-base-medium text-ink-gray-9">
        {{ __("Customer") }}
      </h3>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-ink-gray-5">{{ __("Customer") }}</span>
          <span
            class="flex min-h-7 items-center rounded border border-dashed border-outline-gray-2 px-2 py-1 text-base text-ink-gray-8"
            >{{ f.data?.customer_name || f.data?.customer }}</span
          >
        </div>
        <div class="flex flex-col gap-1.5">
          <span :id="`${id}-address`" class="text-xs text-ink-gray-5">{{
            __("Address")
          }}</span>
          <div
            v-if="f.addresses.length"
            class="flex items-start gap-2 rounded border border-dashed border-outline-gray-2 px-2 py-1"
          >
            <span
              class="min-w-0 flex-1 whitespace-pre-line text-p-sm text-ink-gray-8"
              :aria-labelledby="`${id}-address`"
              >{{ addressText }}</span
            >
            <Dropdown
              v-if="f.addresses.length > 1"
              :options="addressMenu"
              align="end"
            >
              <Button
                variant="ghost"
                size="sm"
                :label="__('Change')"
                :aria-label="__('Change the address')"
              />
            </Dropdown>
          </div>
          <p
            v-else
            class="flex items-start gap-1.5 rounded border border-dashed border-outline-gray-2 px-2 py-1 text-p-sm text-ink-gray-6"
          >
            <span class="flex-1"
              >{{ __("No address on file.") }}
              <a
                href="/app/address/new"
                target="_blank"
                rel="noopener"
                class="rounded text-ink-gray-8 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                >{{ __("Add address") }}</a
              >
              {{ __("and link it to {0}. You can still send.", customerLabel) }}
            </span>
          </p>
        </div>
        <div class="flex flex-col gap-1.5">
          <Combobox
            :label="__('Signs off for the customer (To)')"
            :options="f.contactOptions"
            :placeholder="__('Pick a contact with an email')"
            :empty-text="__('No contacts with an email')"
            :model-value="f.form.signatory_contact || null"
            @update:model-value="
              (v: string | null) => (f.form.signatory_contact = v || '')
            "
          />
          <p class="text-p-xs text-ink-gray-5">
            <template v-if="f.contacts.length">
              {{
                __(
                  "The mail goes to this person's email. To send it to someone else, add them as a contact of the customer first."
                )
              }}
            </template>
            <template v-else>
              {{ __("{0} has no contacts with an email yet.", customerLabel) }}
              <router-link
                v-if="f.data?.customer"
                :to="{ name: 'Customer', params: { id: f.data.customer } }"
                class="rounded text-ink-gray-8 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                >{{ __("Add contacts to the customer") }}</router-link
              >
            </template>
          </p>
        </div>
        <div class="flex flex-col gap-1.5">
          <FormControl
            v-model="f.form.cc"
            type="text"
            :label="__('CC')"
            :placeholder="__('name@company.com, name2@company.com')"
            :description="
              __('Comma separated. The project lead and you, to start with.')
            "
            :list="`${id}-cc`"
          />
          <!-- the customer's other contacts, offered as CC while typing -->
          <datalist :id="`${id}-cc`">
            <option
              v-for="c in f.contacts"
              :key="c.contact"
              :value="ccWith(c.email)"
            >
              {{ c.full_name }}
            </option>
          </datalist>
        </div>
      </div>
    </section>

    <!-- the mail the customer gets -->
    <section class="flex flex-col gap-3" :aria-labelledby="`${id}-mail`">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 :id="`${id}-mail`" class="text-base-medium text-ink-gray-9">
          {{ __("Mail content") }}
        </h3>
        <span
          v-if="f.previewing"
          class="text-xs text-ink-gray-5"
          aria-live="polite"
          >{{ __("Filling in…") }}</span
        >
        <Button
          v-else-if="f.mailEdited && !f.confirmReapply"
          variant="ghost"
          size="sm"
          :label="__('Reapply template')"
          @click="f.confirmReapply = true"
        />
      </div>
      <div
        v-if="f.confirmReapply"
        class="flex flex-wrap items-center gap-2 rounded-md bg-surface-gray-1 px-3 py-2 text-p-sm text-ink-gray-8"
        role="alert"
      >
        <span class="flex-1">{{
          __("Reapply the template? Your changes to the mail are lost.")
        }}</span>
        <Button
          size="sm"
          :label="__('Keep my text')"
          @click="f.confirmReapply = false"
        />
        <Button
          size="sm"
          variant="solid"
          :label="__('Reapply')"
          @click="f.reapply()"
        />
      </div>
      <TextInput
        v-model="f.form.subject"
        :label="__('Subject')"
        maxlength="240"
        required
      />
      <div class="flex flex-col gap-1.5">
        <span class="text-xs text-ink-gray-5">{{ __("Mail body") }}</span>
        <CompactEditor
          v-model="f.form.body"
          type="Email"
          :min-height="tall ? 'min-h-[360px]' : 'min-h-[180px]'"
          :max-height="tall ? 'max-h-[60vh]' : 'max-h-72'"
        />
        <p class="text-p-xs text-ink-gray-5">{{ linkHint }}</p>
      </div>
      <div
        v-if="f.mailError"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span class="flex-1">{{ f.mailError }}</span>
        <Button size="sm" :label="__('Try again')" @click="f.reapply()" />
      </div>
      <p
        v-else-if="f.unfilled.length && f.detailsPicked"
        class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-ink-gray-9"
      >
        <LucideTriangleAlert
          class="mt-0.5 size-4 shrink-0 text-warning"
          aria-hidden="true"
        />
        <span>{{
          __("Fill {0}: it is used in the mail.", f.unfilled.join(", "))
        }}</span>
      </p>
      <Checkbox
        v-model="f.form.attach_pdf"
        :label="__('Attach sign-off document (PDF)')"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import CompactEditor from "@/components/CompactEditor.vue";
import { __ } from "@/translation";
import {
  Button,
  Checkbox,
  Combobox,
  Dropdown,
  FormControl,
  TextInput,
} from "frappe-ui";
import { computed, useId } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import { projectTypeOptions } from "../taskMeta";
import SignoffDetailField from "./SignoffDetailField.vue";
import type { SignoffForm } from "../useSignoffForm";

const props = defineProps<{
  f: SignoffForm;
  /** the full page: a taller mail editor */
  tall?: boolean;
}>();

const id = `signoff-${useId()}`;
// a UAT names who tests with the client (no UAT stage asks for it among its details)
const uatTester = computed(
  () => props.f.isUat && !props.f.shownFields.includes("trainer")
);
// written here: a "}}" inside the template's {{ }} would end it
const linkHint = __(
  "With questions, the link to the customer's questions page goes where {0} is, or at the end.",
  "{{ sign_off_link }}"
);
const customerLabel = computed(
  () => props.f.data?.customer_name || props.f.data?.customer || ""
);
const addressText = computed(
  () =>
    props.f.address?.display.replace(/<br\s*\/?>/gi, "\n").trim() ||
    __("Pick an address")
);
const addressMenu = computed(() =>
  props.f.addresses.map((a) => ({
    label: a.is_primary ? __("{0} (primary)", a.title) : a.title,
    onClick: () => (props.f.form.customer_address = a.name),
  }))
);

/** The CC typed so far with `email` added, so picking a contact keeps the others. */
function ccWith(email: string) {
  const typed = props.f.ccList.filter(
    (e) => e.toLowerCase() !== email.toLowerCase()
  );
  return [...typed, email].join(", ");
}
</script>

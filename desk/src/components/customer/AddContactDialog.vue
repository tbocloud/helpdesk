<template>
  <Dialog
    v-model:open="show"
    :title="__('Add contact')"
    :message="
      __(
        'They are added to the customer without portal access, so they can be mailed and sign off. Invite them to the portal when they need to raise tickets.'
      )
    "
    :dismissible="!customer.createContact.loading"
  >
    <form :id="formId" novalidate @submit.prevent="add">
      <NewContactFields v-model="contact" />
      <p
        v-if="errorMessage"
        role="alert"
        class="mt-3 flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </p>
    </form>
    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Add contact')"
          :loading="customer.createContact.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { CustomerResourceSymbol } from "@/types";
import { errorText } from "@/utils";
import { Button, Dialog, toast } from "frappe-ui";
import { inject, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import NewContactFields, { blankContact } from "./NewContactFields.vue";

const show = defineModel<boolean>({ default: false });

const customer = inject(CustomerResourceSymbol)!;

const formId = `add-contact-${useId()}`;
const contact = ref(blankContact());
const errorMessage = ref("");

function add() {
  errorMessage.value = "";
  if (!contact.value.full_name.trim() || !contact.value.email.trim()) {
    errorMessage.value = __("Enter their name and email.");
    return;
  }
  customer.createContact.submit(contact.value, {
    onSuccess() {
      toast.success(__("{0} added", contact.value.full_name.trim()));
      customer.getContacts.reload();
      show.value = false;
    },
    onError(e: unknown) {
      errorMessage.value = errorText(e, __("Couldn't add the contact."));
    },
  });
}

watch(show, (open) => {
  if (!open) return;
  contact.value = blankContact();
  errorMessage.value = "";
});
</script>

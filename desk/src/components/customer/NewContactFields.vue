<template>
  <div class="flex flex-col gap-3">
    <TextInput
      v-model="contact.full_name"
      :label="__('Name')"
      :placeholder="__('e.g. Priya Nair')"
      autocomplete="off"
      maxlength="140"
      required
      autofocus
    />
    <TextInput
      v-model="contact.email"
      type="email"
      :label="__('Email')"
      :placeholder="__('name@company.com')"
      autocomplete="off"
      required
    />
    <TextInput
      v-model="contact.designation"
      :label="__('Designation (optional)')"
      :placeholder="__('e.g. Finance Manager')"
      maxlength="140"
    />
  </div>
</template>

<script lang="ts">
/** Someone added as a customer's contact by name and email (HD Customer.add_contact_by_email). */
export interface NewContact {
  full_name: string;
  email: string;
  designation: string;
}

export function blankContact(): NewContact {
  return { full_name: "", email: "", designation: "" };
}
</script>

<script setup lang="ts">
import { __ } from "@/translation";
import { TextInput } from "frappe-ui";

const contact = defineModel<NewContact>({ required: true });
</script>

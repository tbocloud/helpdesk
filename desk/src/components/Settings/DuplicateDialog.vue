<template>
  <Dialog v-model:open="open" :title="title">
    <template #default>
      <form :id="formId" @submit.prevent="submit">
        <FormControl
          v-model="name"
          type="text"
          :label="label"
          :maxlength="maxlength"
          required
        />
      </form>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="open = false" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Make a copy')"
          :loading="loading"
          :disabled="!name.trim()"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dialog, FormControl } from "frappe-ui";
import { useId } from "vue";

defineProps<{
  title: string;
  /** Label of the new name field, e.g. "Name of the copy". */
  label: string;
  maxlength?: number;
  loading?: boolean;
}>();

const emit = defineEmits<{ (e: "duplicate"): void }>();

const open = defineModel<boolean>("open", { required: true });
const name = defineModel<string>("name", { required: true });

const formId = `duplicate-${useId()}`;

function submit() {
  if (name.value.trim()) emit("duplicate");
}
</script>

<template>
  <button
    v-if="!editing"
    type="button"
    class="inline-flex h-7 items-center gap-1 rounded-full border border-dashed border-outline-gray-3 px-3 text-sm text-ink-gray-6 transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
    @click="start"
  >
    <LucidePlus class="size-3.5" aria-hidden="true" />{{ label }}
  </button>
  <!-- not a <form>: the chip sits inside the dialog's own form -->
  <div
    v-else
    class="inline-flex min-h-7 items-center gap-1 rounded-full border border-brand bg-surface-base pl-3 pr-1"
  >
    <input
      ref="input"
      v-model="name"
      type="text"
      maxlength="140"
      class="h-6 w-36 border-0 bg-transparent p-0 text-sm text-ink-gray-8 placeholder-ink-gray-4 focus:ring-0"
      :placeholder="placeholder"
      :aria-label="label"
      :disabled="saving"
      @keydown.enter.prevent="save"
      @keydown.esc.stop.prevent="editing = false"
    />
    <button
      type="button"
      class="grid size-5 place-items-center rounded-full text-brand-ink hover:bg-brand-soft disabled:opacity-50"
      :disabled="saving || !name.trim()"
      :aria-label="__('Save')"
      @click="save"
    >
      <LucideCheck class="size-3.5" aria-hidden="true" />
    </button>
    <button
      type="button"
      class="grid size-5 place-items-center rounded-full text-ink-gray-5 hover:bg-surface-gray-2"
      :aria-label="__('Cancel')"
      @click="editing = false"
    >
      <LucideX class="size-3.5" aria-hidden="true" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { toast } from "frappe-ui";
import { nextTick, ref } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucidePlus from "~icons/lucide/plus";
import LucideX from "~icons/lucide/x";
import { type ContentOptionKind, useContentOptions } from "../contentOptions";

const props = defineProps<{
  kind: ContentOptionKind;
  label: string;
  placeholder?: string;
}>();
const emit = defineEmits<{ (e: "added", name: string): void }>();

const { platforms, postTypes, addOption } = useContentOptions();
const editing = ref(false);
const name = ref("");
const saving = ref(false);
const input = ref<HTMLInputElement | null>(null);

async function start() {
  name.value = "";
  editing.value = true;
  await nextTick();
  input.value?.focus();
}

async function save() {
  const value = name.value.trim();
  if (!value) return;
  // picking one that already exists (in any case) is just selecting it
  const existing = (
    props.kind === "platform" ? platforms : postTypes
  ).value.find((o) => o.toLowerCase() === value.toLowerCase());
  if (existing) {
    emit("added", existing);
    editing.value = false;
    return;
  }
  saving.value = true;
  try {
    emit("added", await addOption(props.kind, value));
    editing.value = false;
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't add {0}", value));
  } finally {
    saving.value = false;
  }
}
</script>

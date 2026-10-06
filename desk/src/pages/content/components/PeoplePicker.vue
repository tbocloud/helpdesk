<template>
  <div class="flex flex-col gap-1.5">
    <label v-if="label" :for="inputId" class="text-xs text-ink-gray-5">{{
      label
    }}</label>
    <ul
      v-if="modelValue.length"
      class="flex flex-wrap gap-1.5"
      :aria-label="label"
    >
      <li
        v-for="(user, i) in modelValue"
        :key="user"
        class="inline-flex h-7 max-w-full items-center gap-1.5 rounded-full bg-surface-gray-2 pl-1 pr-1.5 text-sm text-ink-gray-8"
      >
        <Avatar size="xs" :label="nameOf(user)" />
        <span class="max-w-[11rem] truncate">{{ nameOf(user) }}</span>
        <span
          v-if="i === 0 && modelValue.length > 1"
          class="rounded bg-brand-soft px-1 text-2xs font-medium text-brand-ink"
          :title="__('Main person for this role')"
          >{{ __("main") }}</span
        >
        <button
          type="button"
          class="rounded-full p-0.5 text-ink-gray-5 hover:bg-surface-gray-3 hover:text-ink-gray-8"
          :aria-label="__('Remove {0}', nameOf(user))"
          @click="remove(user)"
        >
          <LucideX class="size-3.5" aria-hidden="true" />
        </button>
      </li>
    </ul>
    <!-- keyed so the box clears after each pick -->
    <Link
      :key="adds"
      doctype="User"
      :filters="{ enabled: 1, user_type: 'System User' }"
      @update:model-value="add"
    >
      <!-- our own trigger, so the role's label can name it -->
      <template #target="{ togglePopover }">
        <button
          :id="inputId"
          type="button"
          class="flex h-7 w-full items-center justify-between gap-2 rounded border border-outline-gray-1 bg-surface-gray-2 px-2 text-base text-ink-gray-4 transition-colors hover:bg-surface-gray-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
          @click="togglePopover()"
        >
          <span class="truncate">{{
            modelValue.length ? __("Add another person") : placeholder
          }}</span>
          <LucideChevronDown
            class="size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
        </button>
      </template>
    </Link>
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import { __ } from "@/translation";
import { Avatar, call } from "frappe-ui";
import { reactive, ref, useId, watch } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideX from "~icons/lucide/x";

const props = withDefaults(
  defineProps<{ modelValue: string[]; label?: string; placeholder?: string }>(),
  { label: "", placeholder: "" }
);
const emit = defineEmits<{ (e: "update:modelValue", value: string[]): void }>();

const adds = ref(0);
const inputId = useId();

function add(user: string) {
  if (!user) return;
  if (!props.modelValue.includes(user))
    emit("update:modelValue", [...props.modelValue, user]);
  adds.value++;
}

function remove(user: string) {
  emit(
    "update:modelValue",
    props.modelValue.filter((u) => u !== user)
  );
}

// full names, looked up once per person and shared by every picker
const names = reactive<Record<string, string>>(fullNames);
function nameOf(user: string) {
  return names[user] || user;
}
watch(
  () => props.modelValue,
  (users) => {
    const unknown = users.filter((u) => !(u in names));
    if (!unknown.length) return;
    for (const u of unknown) names[u] = u;
    call("frappe.client.get_list", {
      doctype: "User",
      filters: { name: ["in", unknown] },
      fields: ["name", "full_name"],
      limit_page_length: unknown.length,
    })
      .then((rows: { name: string; full_name: string }[]) => {
        for (const r of rows) names[r.name] = r.full_name || r.name;
      })
      .catch(() => {});
  },
  { immediate: true }
);
</script>

<script lang="ts">
const fullNames: Record<string, string> = {};
</script>

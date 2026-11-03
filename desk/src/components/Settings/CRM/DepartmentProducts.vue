<template>
  <fieldset
    class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 p-4"
  >
    <legend class="px-1 text-sm-medium text-ink-gray-8">
      {{ __("Products / brands") }}
    </legend>
    <p class="text-p-xs text-ink-gray-6">
      {{
        __(
          "The names your callers can call under, like PhoebiX or BillaX under GrowthX. Each product's leads are kept apart. Leave it empty if the department sells one thing."
        )
      }}
    </p>
    <ul v-if="products.length" role="list" class="flex flex-col gap-3">
      <li
        v-for="(product, index) in products"
        :key="index"
        class="grid grid-cols-1 items-end gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_auto_auto]"
      >
        <FormControl
          v-model="product.product_name"
          :label="__('Name')"
          maxlength="140"
          autocomplete="off"
        />
        <FormControl
          v-model="product.intro_line"
          :label="__('Say on the call')"
          :placeholder="__('PhoebiX – solar ERP for installers')"
          maxlength="140"
          autocomplete="off"
        />
        <Switch
          class="pb-1.5"
          :model-value="!!product.is_active"
          :label="product.is_active ? __('On') : __('Off')"
          :aria-label="__('{0} is on', product.product_name || __('Product'))"
          @update:model-value="product.is_active = $event ? 1 : 0"
        />
        <!-- a saved product is switched off, never removed: its leads keep the name -->
        <Button
          v-if="!product.previous_name"
          variant="ghost"
          :label="__('Remove {0}', product.product_name || __('product'))"
          @click="products.splice(index, 1)"
        >
          <template #icon>
            <LucideTrash2 class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <span v-else class="hidden size-7 sm:block" aria-hidden="true" />
      </li>
    </ul>
    <Button class="self-start" :label="__('Add product')" @click="add">
      <template #prefix>
        <LucidePlus class="size-4" aria-hidden="true" />
      </template>
    </Button>
  </fieldset>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import type { LeadProduct } from "@/pages/leads/leads";
import { Button, FormControl, Switch } from "frappe-ui";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";

const products = defineModel<LeadProduct[]>({ required: true });

function add() {
  products.value.push({ product_name: "", is_active: 1, intro_line: "" });
}
</script>

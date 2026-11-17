<template>
  <SourceEditor
    v-if="site"
    :name="site.name"
    :back-label="
      site.from === 'list'
        ? __('Back to divisions')
        : __('Back to {0}', divisionLabel)
    "
    @back="site = null"
    @saved="onSourceSaved"
  />
  <!-- kept while its site is open, so what was typed there survives -->
  <DivisionEditor
    v-if="editing !== undefined"
    v-show="!site"
    ref="divisionEditor"
    :name="editing"
    @back="editing = undefined"
    @created="editing = $event"
    @open-source="site = { name: $event, from: 'division' }"
  />
  <DivisionsList
    v-else-if="!site"
    @open="editing = $event"
    @open-source="site = { name: $event, from: 'list' }"
  />
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed, ref } from "vue";
import DivisionEditor from "./DivisionEditor.vue";
import DivisionsList from "./DivisionsList.vue";
import SourceEditor from "./SourceEditor.vue";

// undefined: the list; null: a new division; a name: that division
const editing = ref<string | null | undefined>(undefined);
// an ERP site open on top: null for a new one; `from` is where Back goes
const site = ref<{ name: string | null; from: "list" | "division" } | null>(
  null
);
const divisionEditor = ref<InstanceType<typeof DivisionEditor> | null>(null);
const divisionLabel = computed(() => editing.value || __("the division"));

function onSourceSaved(name: string) {
  // a site added from a division is that division's
  if (site.value?.from === "division" && site.value.name === null)
    divisionEditor.value?.useSource(name);
  site.value = { name, from: site.value?.from || "list" };
}
</script>

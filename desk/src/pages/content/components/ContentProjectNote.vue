<template>
  <!-- which project the post's tasks join: one of the customer's open projects. The live
       region stays mounted so screen readers announce the text when it arrives. -->
  <div aria-live="polite">
    <p v-if="customer && shown" class="flex items-start gap-1.5 text-p-xs">
      <template v-if="shown.name">
        <LucideFolderKanban
          class="mt-0.5 size-3.5 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        <span class="min-w-0 text-ink-gray-6">
          {{ __("Tasks go to") }}
          <a
            :href="projectHref"
            target="_blank"
            rel="noopener"
            class="font-medium text-ink-gray-8 underline-offset-2 hover:underline focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >{{ shown.project_name || shown.name }}</a
          >
        </span>
      </template>
      <template v-else-if="shown.hidden">
        <LucideFolderKanban
          class="mt-0.5 size-3.5 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        <span class="min-w-0 text-ink-gray-6">{{
          __("Tasks go to this customer's project")
        }}</span>
      </template>
      <template v-else>
        <LucideTriangleAlert
          class="mt-0.5 size-3.5 shrink-0 text-warning"
          aria-hidden="true"
        />
        <span class="text-ink-gray-7">{{ shown.missing }}</span>
      </template>
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { useEventListener } from "@vueuse/core";
import { call } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";

type ContentProject = {
  name: string | null;
  project_name?: string;
  // the project exists but the viewer can't open it
  hidden?: boolean;
  missing?: string;
};

const props = defineProps<{ customer?: string | null }>();
const router = useRouter();

// the answer for the customer now picked; nothing while it loads or if it failed, so the
// note never shows another customer's project
const result = ref<{ customer: string; project: ContentProject } | null>(null);
const shown = computed(() =>
  result.value?.customer === props.customer ? result.value.project : null
);

// only the latest request's answer counts: an older one (another customer, or the
// same one before a focus reload) is dropped when it arrives late
let latest = 0;

async function load() {
  const customer = props.customer;
  if (!customer) return;
  const request = ++latest;
  try {
    const project = await call(
      "helpdesk.api.content_board.get_content_project",
      {
        customer,
      }
    );
    if (request === latest) result.value = { customer, project };
  } catch {
    if (request === latest) result.value = null;
  }
}

watch(() => props.customer, load, { immediate: true });
// the project is often fixed in another tab (the link opens one): check again on return
useEventListener(window, "focus", load);

const projectHref = computed(
  () =>
    shown.value?.name &&
    router.resolve({
      name: "TaskyProject",
      params: { projectId: shown.value.name },
    }).href
);
</script>

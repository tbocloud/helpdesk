<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId" />
    <div class="flex-1 overflow-auto">
      <div
        class="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 pb-8 pt-4 md:px-8"
      >
        <router-link
          :to="{ name: 'TaskySignoffs', params: { projectId } }"
          class="inline-flex w-fit items-center gap-1 rounded text-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        >
          <LucideArrowLeft class="size-4" aria-hidden="true" />
          {{ __("All sign-offs") }}
        </router-link>
        <h2 class="text-xl font-semibold text-ink-gray-9">
          {{ uat ? __("New UAT sign-off") : __("New sign-off") }}
        </h2>
        <SignoffEditorForm
          :project-id="projectId"
          :uat="uat"
          :carried="carried"
          @saved="opened"
          @back="back"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useSignoffDraftStore } from "@/stores/signoffDraft";
import { __ } from "@/translation";
import { useRouter } from "vue-router";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import ProjectNav from "./components/ProjectNav.vue";
import SignoffEditorForm from "./components/SignoffEditorForm.vue";

/** A new sign-off prepared on its own page, with what the dialog had (Edit in full page). */
const props = defineProps<{ projectId: string; uat?: boolean }>();
const router = useRouter();
// taken once: a reload starts a fresh form
const carried = useSignoffDraftStore().take(props.projectId, !!props.uat);

function opened(name: string) {
  router.replace({
    name: "TaskySignoff",
    params: { projectId: props.projectId, signoffId: name },
  });
}

function back() {
  router.push({
    name: "TaskySignoffs",
    params: { projectId: props.projectId },
  });
}
</script>

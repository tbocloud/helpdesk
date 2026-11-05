<template>
  <!-- stored rich text (a note's HTML), drawn read-only by the editor, so it renders as the
       editor's own nodes and never as raw HTML -->
  <Editor :model-value="html" :extensions="extensions" :editable="false">
    <template #default>
      <EditorContent
        class="prose-f max-w-none text-p-sm text-ink-gray-8 focus:outline-none"
      />
    </template>
  </Editor>
</template>

<script setup lang="ts">
import { buildEditorExtensions } from "@/components/editor/config";
import { Editor, EditorContent } from "frappe-ui/editor";

defineProps<{ html: string }>();
const extensions = buildEditorExtensions();
</script>

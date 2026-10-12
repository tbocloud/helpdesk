<template>
  <component :is="icon" aria-hidden="true" />
</template>

<script setup lang="ts">
import { computed } from "vue";
import LucideClapperboard from "~icons/lucide/clapperboard";
import LucideFileText from "~icons/lucide/file-text";
import LucideGalleryHorizontalEnd from "~icons/lucide/gallery-horizontal-end";
import LucideImage from "~icons/lucide/image";
import LucideNewspaper from "~icons/lucide/newspaper";
import LucideShapes from "~icons/lucide/shapes";
import LucideSmartphone from "~icons/lucide/smartphone";
import LucideVideo from "~icons/lucide/video";

const props = defineProps<{ postType: string }>();

const ICONS = {
  Post: LucideImage,
  Carousel: LucideGalleryHorizontalEnd,
  Reel: LucideClapperboard,
  Story: LucideSmartphone,
  Video: LucideVideo,
  Article: LucideFileText,
  Newsletter: LucideNewspaper,
};

// post types the team added get a generic mark
const icon = computed(
  () => ICONS[props.postType as keyof typeof ICONS] ?? LucideShapes
);
</script>

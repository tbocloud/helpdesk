<template>
  <!-- the panel folded to icons: the same pages one click away, names in tooltips -->
  <aside
    id="nav-panel"
    :aria-label="__('Menu')"
    class="flex h-full w-14 shrink-0 flex-col items-center gap-1 border-e border-outline-gray-2 bg-surface-sidebar py-3"
  >
    <Tooltip
      v-if="showSearch"
      :text="__('Search')"
      placement="right"
      :hover-delay="0"
    >
      <button
        type="button"
        :class="[buttonClass, idleClass]"
        :aria-label="__('Search')"
        @click="emit('search')"
      >
        <LucideSearch class="size-4" aria-hidden="true" />
      </button>
    </Tooltip>

    <nav
      v-if="area"
      :aria-label="area.label"
      class="mt-1 flex min-h-0 flex-1 flex-col items-center overflow-y-auto overscroll-contain px-2 pb-2"
    >
      <ul class="flex flex-col items-center gap-1">
        <template v-for="(group, index) in area.groups" :key="index">
          <li
            v-if="index"
            class="my-1 h-px w-6 shrink-0 bg-outline-gray-3"
            role="presentation"
          />
          <li v-for="item in group.items" :key="item.id">
            <Tooltip :text="itemLabel(item)" placement="right" :hover-delay="0">
              <a
                :href="hrefOf({ name: item.to, query: item.query })"
                :class="[
                  buttonClass,
                  isActive(item.id) ? activeClass : idleClass,
                ]"
                :aria-label="itemLabel(item)"
                :aria-current="isActive(item.id) ? 'page' : undefined"
                @click="go($event, { name: item.to, query: item.query })"
              >
                <component :is="item.icon" class="size-4" aria-hidden="true" />
                <span
                  v-if="badge(item.countKey)"
                  class="absolute -end-0.5 -top-0.5 min-w-4 rounded-full bg-brand px-1 text-center font-mono text-2xs leading-4 tabular-nums text-brand-on"
                  aria-hidden="true"
                >
                  {{ badge(item.countKey) > 99 ? "99+" : badge(item.countKey) }}
                </span>
              </a>
            </Tooltip>
          </li>

          <!-- a tree (saved views) opens as a small menu beside its icon -->
          <li v-for="tree in group.trees" :key="tree.id">
            <Tooltip :text="tree.label" placement="right" :hover-delay="0">
              <Dropdown side="right" align="start" :options="treeOptions(tree)">
                <template #default="{ open, close, disabled, ...trigger }">
                  <button
                    type="button"
                    v-bind="trigger"
                    :class="[
                      buttonClass,
                      treeHasActive(tree) ? activeClass : idleClass,
                    ]"
                    :aria-label="tree.label"
                    aria-haspopup="menu"
                    :aria-expanded="open"
                  >
                    <component
                      :is="tree.icon"
                      class="size-4"
                      aria-hidden="true"
                    />
                  </button>
                </template>
              </Dropdown>
            </Tooltip>
          </li>
        </template>
      </ul>
    </nav>
    <div v-else class="flex-1" />

    <div class="flex shrink-0 flex-col items-center gap-1">
      <FollowUpStrip v-if="showFollowUps" :summary="followUps" compact rail />
      <slot name="footer-items" />
    </div>
  </aside>
</template>

<script setup lang="ts">
import FollowUpStrip from "@/components/FollowUpStrip.vue";
import { __ } from "@/translation";
import { Dropdown, Tooltip } from "frappe-ui";
import { useRouter } from "vue-router";
import LucideSearch from "~icons/lucide/search";
import type { NavArea, NavItem, NavTree } from "./navigation";

const props = defineProps<{
  area?: NavArea;
  /** id of the highlighted item or sub-item */
  activeId?: string | null;
  counts?: Record<string, any> | null;
  showSearch?: boolean;
  showFollowUps?: boolean;
  followUps?: any;
}>();

const emit = defineEmits<{ (e: "search"): void }>();

const router = useRouter();

// size-10 keeps the target as large as the rail's
const buttonClass =
  "relative grid size-10 shrink-0 place-items-center rounded-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight";
const activeClass = "bg-brand-soft text-brand-ink";
const idleClass = "text-ink-gray-7 hover:bg-surface-gray-2";

const isActive = (id: string) => props.activeId === id;
const badge = (key?: string): number =>
  key ? Number(props.counts?.[key] || 0) : 0;

// the count rides on the icon, so the name carries it for screen readers and the tooltip
const itemLabel = (item: NavItem) =>
  badge(item.countKey)
    ? __("{0} ({1} waiting)", item.label, String(badge(item.countKey)))
    : item.label;

const treeHasActive = (tree: NavTree) =>
  tree.children.some((child) => isActive(child.id));

const hrefOf = (to: { name: string; query?: Record<string, string> }) =>
  router.resolve(to).href;

// a plain click navigates in the app; a modified one (new tab) stays the browser's
function go(
  event: MouseEvent,
  to: { name: string; query?: Record<string, string> }
) {
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
  event.preventDefault();
  router.push(to);
}

const treeOptions = (tree: NavTree) => [
  {
    group: tree.label,
    items: tree.children.map((child) => ({
      label: child.label,
      onClick: () => {
        child.onSelect?.();
        router.push(child.to);
      },
    })),
  },
];
</script>

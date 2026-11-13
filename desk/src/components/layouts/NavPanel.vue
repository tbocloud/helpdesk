<template>
  <aside
    id="nav-panel"
    :aria-label="__('Menu')"
    class="flex h-full shrink-0 flex-col border-e border-outline-gray-2 bg-surface-sidebar"
    :class="mobile ? 'min-w-0 flex-1' : 'w-60'"
  >
    <div class="flex shrink-0 flex-col gap-2 px-3 pt-3">
      <!-- who this workspace is; the account menu lives on the rail's avatar -->
      <div
        class="flex items-center gap-2 rounded-xl border border-outline-gray-2 bg-surface-base px-2 py-1.5"
      >
        <BrandLogo class="!size-8 !rounded-[8px] !font-bold" />
        <div class="flex min-w-0 flex-1 flex-col gap-0.5">
          <div
            class="truncate text-base font-semibold leading-tight text-ink-gray-9"
          >
            {{ config.brandName }}
          </div>
          <div class="truncate text-xs leading-tight text-ink-gray-6">
            {{ subLine }}
          </div>
        </div>
      </div>

      <button
        v-if="showSearch"
        type="button"
        class="flex h-9 w-full items-center gap-2.5 rounded-xl border border-outline-gray-2 bg-surface-base px-3 text-start transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        @click="emit('search')"
      >
        <LucideSearch
          class="size-3.5 shrink-0 text-ink-gray-6"
          aria-hidden="true"
        />
        <span class="flex-1 truncate text-base text-ink-gray-6">
          {{ __("Search") }}
        </span>
        <kbd
          class="flex items-center gap-0.5 rounded-[4px] bg-surface-gray-2 px-1.5 py-0.5 text-2xs text-ink-gray-6"
        >
          <component
            :is="device.modifierIcon"
            class="size-3"
            aria-hidden="true"
          />
          K
        </kbd>
      </button>
    </div>

    <!-- the area's name stays put while its items scroll -->
    <h2
      v-if="area"
      :id="`nav-area-${area.id}`"
      class="shrink-0 px-5 pb-1 pt-3 text-sm font-semibold text-ink-gray-9"
    >
      {{ area.label }}
    </h2>

    <nav
      v-if="area"
      :aria-labelledby="`nav-area-${area.id}`"
      class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pb-2"
    >
      <section
        v-for="(group, index) in area.groups"
        :key="index"
        class="mt-3 first:mt-0"
      >
        <h3
          v-if="group.label"
          class="mb-1 px-2 text-2xs font-semibold uppercase tracking-wider text-ink-gray-5"
        >
          {{ group.label }}
        </h3>
        <ul class="flex flex-col gap-0.5">
          <li v-for="item in group.items" :key="item.id">
            <RouterLink
              custom
              :to="{ name: item.to, query: item.query }"
              v-slot="{ href, navigate }"
            >
              <a
                :href="href"
                :class="[rowClass, isActive(item.id) ? activeClass : idleClass]"
                :aria-current="isActive(item.id) ? 'page' : undefined"
                @click="navigate"
              >
                <component
                  :is="item.icon"
                  class="size-4 shrink-0"
                  :class="
                    isActive(item.id) ? 'text-brand-ink' : 'text-ink-gray-6'
                  "
                  aria-hidden="true"
                />
                <span class="flex-1 truncate">{{ item.label }}</span>
                <span
                  v-if="badge(item.countKey)"
                  class="font-mono text-xs tabular-nums text-ink-gray-6"
                  :aria-label="__('{0} waiting', String(badge(item.countKey)))"
                >
                  {{ badge(item.countKey) > 99 ? "99+" : badge(item.countKey) }}
                </span>
              </a>
            </RouterLink>
          </li>

          <li v-for="tree in group.trees" :key="tree.id">
            <button
              type="button"
              :class="[rowClass, idleClass, 'w-full text-start']"
              :aria-expanded="sidebarStore.isTreeOpen(tree.id)"
              :aria-controls="`nav-tree-${tree.id}`"
              @click="
                sidebarStore.setTreeOpen(
                  tree.id,
                  !sidebarStore.isTreeOpen(tree.id)
                )
              "
            >
              <component
                :is="tree.icon"
                class="size-4 shrink-0 text-ink-gray-6"
                aria-hidden="true"
              />
              <span class="flex-1 truncate">{{ tree.label }}</span>
              <LucideChevronRight
                class="size-4 shrink-0 text-ink-gray-5 transition-transform motion-reduce:transition-none"
                :class="sidebarStore.isTreeOpen(tree.id) && 'rotate-90'"
                aria-hidden="true"
              />
            </button>
            <!-- the guide line runs down the left; each sub-item hangs off it with a dot -->
            <ul
              v-show="sidebarStore.isTreeOpen(tree.id)"
              :id="`nav-tree-${tree.id}`"
              class="ms-[1.15rem] mt-0.5 flex flex-col gap-0.5 border-s border-outline-gray-3 ps-2"
            >
              <li v-for="child in tree.children" :key="child.id">
                <div class="group/child relative">
                  <RouterLink custom :to="child.to" v-slot="{ href, navigate }">
                    <a
                      :href="href"
                      :class="[
                        rowClass,
                        'pe-9',
                        isActive(child.id) ? activeClass : idleClass,
                      ]"
                      :aria-current="isActive(child.id) ? 'page' : undefined"
                      @click="onChildClick(child, navigate, $event)"
                    >
                      <span
                        class="size-1.5 shrink-0 rounded-full"
                        :class="
                          isActive(child.id) ? 'bg-brand' : 'bg-surface-gray-5'
                        "
                        aria-hidden="true"
                      />
                      <span class="flex-1 truncate">{{ child.label }}</span>
                    </a>
                  </RouterLink>
                  <Dropdown
                    v-if="child.view"
                    side="right"
                    align="start"
                    :options="viewActions(child.view)"
                  >
                    <template #default="{ open }">
                      <Button
                        variant="ghost"
                        icon="lucide-more-horizontal"
                        class="absolute end-1 top-1/2 -translate-y-1/2 !size-6 rounded !text-ink-gray-7"
                        :class="
                          open
                            ? 'opacity-100'
                            : 'opacity-0 focus-visible:opacity-100 group-hover/child:opacity-100 [@media(pointer:coarse)]:opacity-100'
                        "
                        :aria-label="__('View options')"
                      />
                    </template>
                  </Dropdown>
                </div>
              </li>
            </ul>
          </li>
        </ul>
      </section>
    </nav>

    <div class="flex shrink-0 flex-col gap-1.5 px-3 pb-3 pt-2">
      <FollowUpStrip v-if="showFollowUps" :summary="followUps" compact />
      <slot name="footer" />
      <slot name="footer-items" />
    </div>
  </aside>
</template>

<script setup lang="ts">
import BrandLogo from "@/components/BrandLogo.vue";
import FollowUpStrip from "@/components/FollowUpStrip.vue";
import { useDevice } from "@/composables";
import { useAuthStore } from "@/stores/auth";
import { useConfigStore } from "@/stores/config";
import { useSidebarStore } from "@/stores/sidebar";
import { __ } from "@/translation";
import { isCustomerPortal } from "@/utils";
import { Button, Dropdown } from "frappe-ui";
import { computed } from "vue";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideSearch from "~icons/lucide/search";
import type { NavArea, NavChild } from "./navigation";

const props = defineProps<{
  area?: NavArea;
  /** id of the highlighted item or sub-item */
  activeId?: string | null;
  counts?: Record<string, any> | null;
  showSearch?: boolean;
  showFollowUps?: boolean;
  followUps?: any;
  viewActions: (view: any) => any[];
  mobile?: boolean;
}>();

const emit = defineEmits<{ (e: "search"): void }>();

const device = useDevice();
const authStore = useAuthStore();
const config = useConfigStore();
const sidebarStore = useSidebarStore();

const rowClass = [
  "flex items-center gap-2.5 rounded-lg px-2 text-base transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight",
  props.mobile ? "min-h-11" : "min-h-9",
].join(" ");
const activeClass = "bg-brand-soft font-semibold text-brand-ink";
const idleClass = "text-ink-gray-8 hover:bg-surface-gray-2";

const isActive = (id: string) => props.activeId === id;
const badge = (key?: string): number =>
  key ? Number(props.counts?.[key] || 0) : 0;

function onChildClick(
  child: NavChild,
  navigate: (e: MouseEvent) => void,
  event: MouseEvent
) {
  child.onSelect?.();
  navigate(event);
}

// The department tells people apart faster than a repeated name.
const subLine = computed(() => {
  if (isCustomerPortal.value) return __("Customer portal");
  if (authStore.isSalesEmployee) return __("Sales");
  if (authStore.isContentTeam) return __("Content team");
  if (authStore.isDmEmployee) return __("Digital marketing");
  if (authStore.isErpOnly) return __("ERP");
  return authStore.userName;
});
</script>

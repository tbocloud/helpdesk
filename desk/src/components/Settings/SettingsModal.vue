<template>
  <Dialog
    v-model:open="show"
    size="5xl"
    bare
    :dismissible="!disableSettingModalOutsideClick"
  >
    <template #default>
      <div
        class="flex flex-col overflow-hidden sm:flex-row"
        :style="{ height: 'calc(100vh - 8rem)' }"
      >
        <!-- small screens: one select instead of the sidebar -->
        <div
          class="shrink-0 border-b border-outline-gray-2 bg-surface-sidebar px-4 py-3 sm:hidden"
        >
          <label
            for="settings-page-select"
            class="mb-1.5 block text-xs-medium text-ink-gray-6"
          >
            {{ __("Settings page") }}
          </label>
          <select
            id="settings-page-select"
            class="h-11 w-full rounded border border-outline-gray-2 bg-surface-base py-0 ps-2 text-base text-ink-gray-8"
            :value="activeTab?.label"
            @change="onSelect($event.target as HTMLSelectElement)"
          >
            <optgroup
              v-for="group in tabs"
              :key="group.label"
              :label="group.label"
            >
              <option
                v-for="item in group.items"
                :key="item.label"
                :value="item.label"
              >
                {{ item.label }}
              </option>
            </optgroup>
          </select>
        </div>

        <nav
          class="hidden w-56 shrink-0 flex-col gap-4 overflow-y-auto bg-surface-sidebar px-2 py-3 hide-scrollbar sm:flex"
          :aria-label="__('Settings')"
          @keydown="onNavKeydown"
        >
          <div
            v-for="group in tabs"
            :key="group.label"
            role="group"
            :aria-labelledby="groupId(group.label)"
          >
            <h2
              :id="groupId(group.label)"
              class="px-2 pb-1 text-xs-medium text-ink-gray-5"
            >
              {{ group.label }}
            </h2>
            <ul class="flex flex-col gap-0.5">
              <li v-for="item in group.items" :key="item.label">
                <button
                  type="button"
                  data-slot="sidebar-item"
                  :data-state="isActive(item) ? 'active' : undefined"
                  :aria-current="isActive(item) ? 'page' : undefined"
                  class="flex w-full items-center gap-2 px-2 text-left text-sm"
                  :class="
                    isActive(item)
                      ? 'font-medium'
                      : 'text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9'
                  "
                  @click="onTabChange(item)"
                >
                  <component
                    :is="item.icon"
                    class="tbo-nav-icon size-4 shrink-0"
                    :class="isActive(item) ? '' : 'text-ink-gray-6'"
                    aria-hidden="true"
                  />
                  <span class="truncate">{{ item.label }}</span>
                </button>
              </li>
            </ul>
          </div>
        </nav>

        <div
          class="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-surface-base sm:max-w-[816px]"
        >
          <component
            :is="activeTab.component"
            v-if="activeTab"
            class="flex h-full w-full flex-col"
          />
        </div>
      </div>
    </template>
  </Dialog>
  <ConfirmDialog
    v-model="showConfirmDialog"
    :title="__('Leave without saving?')"
    :message="
      __('Your changes on this page haven\'t been saved and will be lost.')
    "
    :onConfirm="
      () => {
        if (nextActiveTab !== null) {
          activeTab = nextActiveTab;
        }
        nextActiveTab = null;
        showConfirmDialog = false;
        disableSettingModalOutsideClick = false;
      }
    "
    :onCancel="
      () => {
        nextActiveTab = null;
      }
    "
  />
</template>
<script setup lang="ts">
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { __ } from "@/translation";
import { Dialog } from "frappe-ui";
import { ModelRef, ref } from "vue";
import {
  activeTab,
  disableSettingModalOutsideClick,
  nextActiveTab,
  tabs,
  type SettingsTab,
} from "./settingsModal";

const show: ModelRef<boolean> = defineModel();

const showConfirmDialog = ref(false);

function isActive(item: SettingsTab) {
  return activeTab.value?.label === item.label;
}

function groupId(label: string) {
  return `settings-group-${label.replace(/\W+/g, "-").toLowerCase()}`;
}

function onTabChange(tab: SettingsTab) {
  if (isActive(tab)) return;
  if (!disableSettingModalOutsideClick.value) {
    activeTab.value = tab;
    return;
  }
  nextActiveTab.value = tab;
  showConfirmDialog.value = true;
}

function onSelect(select: HTMLSelectElement) {
  const tab = tabs.value
    .flatMap((group) => group.items)
    .find((item) => item.label === select.value);
  if (tab) onTabChange(tab);
  // until a pending "leave without saving?" is confirmed, show the current page
  select.value = activeTab.value?.label;
}

// Up/Down (and Home/End) move between pages, like a menu
function onNavKeydown(event: KeyboardEvent) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const items = Array.from(
    (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>(
      "button[data-slot='sidebar-item']"
    )
  );
  const current = items.indexOf(document.activeElement as HTMLButtonElement);
  if (current === -1) return;
  event.preventDefault();
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
      ? items.length - 1
      : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) %
        items.length;
  items[next]?.focus();
}
</script>

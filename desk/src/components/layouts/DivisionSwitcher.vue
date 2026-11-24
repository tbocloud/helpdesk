<template>
  <!-- Super Admins and managers of several divisions see which division they're in and
       switch it; everyone else works in their own division without the card -->
  <Dropdown v-if="auth.canSwitchDivision" :options="options">
    <button
      type="button"
      class="flex h-11 w-full items-center gap-2.5 rounded-[10px] border border-outline-gray-2 bg-surface-base px-3 text-start transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      :aria-label="__('Division: {0}. Switch division', current.label)"
    >
      <component
        :is="current.all ? LucideLayers : LucideMapPin"
        class="size-4 shrink-0 text-brand-ink"
        aria-hidden="true"
      />
      <span class="flex min-w-0 flex-1 flex-col leading-tight">
        <span class="truncate text-[13px] font-semibold text-ink-gray-9">
          {{ current.label }}
        </span>
        <span class="truncate text-[11.5px] text-ink-gray-6">
          {{ current.sub }}
        </span>
      </span>
      <LucideChevronsUpDown
        class="size-4 shrink-0 text-ink-gray-6"
        aria-hidden="true"
      />
    </button>
  </Dropdown>
</template>

<script setup lang="ts">
import { switchDivision } from "@/pages/divisions/divisions";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Dropdown, toast } from "frappe-ui";
import { computed, h } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideChevronsUpDown from "~icons/lucide/chevrons-up-down";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideLayers from "~icons/lucide/layers";
import LucideMapPin from "~icons/lucide/map-pin";

const auth = useAuthStore();

const active = computed(() =>
  auth.divisions.find((d) => d.name === auth.activeDivision)
);

const current = computed(() =>
  active.value
    ? {
        all: false,
        label: active.value.division_name,
        sub: [active.value.country, active.value.role]
          .filter(Boolean)
          .join(" · "),
      }
    : {
        all: true,
        label: __("All divisions"),
        sub: __("Consolidated"),
      }
);

// a mark beside the current one, an empty space beside the rest so the names line up
const mark = (on: boolean) => () =>
  h(LucideCheck, { class: ["size-4", on ? "" : "invisible"] });

async function pick(division: string | null) {
  if (division === (auth.activeDivision || null)) return;
  try {
    await switchDivision(division);
  } catch (error: any) {
    toast.error(error?.messages?.[0] || __("Couldn't switch division"));
  }
}

const options = computed(() => {
  const groups: any[] = [
    {
      group: __("Switch division"),
      items: [
        // only a Super Admin sees every division at once
        ...(auth.isSuperAdmin
          ? [
              {
                label: __("All divisions"),
                icon: mark(!active.value),
                onClick: () => pick(null),
              },
            ]
          : []),
        ...auth.divisions
          .filter((d) => d.can_switch)
          .map((d) => ({
            label: d.division_name,
            icon: mark(d.name === auth.activeDivision),
            onClick: () => pick(d.name),
          })),
      ],
    },
  ];
  if (active.value?.workspace_url) {
    const url = active.value.workspace_url;
    groups.push({
      group: __("Workspace"),
      items: [
        {
          label: __("Open {0} workspace", active.value.division_name),
          icon: LucideExternalLink,
          onClick: () => window.open(url, "_blank", "noopener"),
        },
      ],
    });
  }
  return groups;
});
</script>

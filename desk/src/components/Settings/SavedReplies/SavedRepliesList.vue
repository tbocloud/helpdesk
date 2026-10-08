<template>
  <SettingsLayoutBase
    :title="__('Saved Replies')"
    :description="
      __(
        'Ready-made answers agents can drop into a reply: your own, your team\'s or everyone\'s.'
      )
    "
  >
    <template #header-actions>
      <Button variant="solid" :label="__('New saved reply')" @click="goToNew()">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template #header-bottom>
      <div class="flex items-center gap-2">
        <SettingsSearch
          v-model="savedRepliesSearchQuery"
          :placeholder="__('Search saved replies')"
        />
        <Dropdown :options="filterOptions" placement="right">
          <Button
            :aria-label="__('Show saved replies: {0}', activeFilterLabel)"
          >
            {{ activeFilterLabel }}
            <template #suffix>
              <LucideChevronDown class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
      </div>
    </template>
    <template #content>
      <SettingsList
        :items="savedRepliesListResource?.data"
        :label="__('Saved replies')"
        :loading="savedRepliesListResource?.list?.loading"
        :error="savedRepliesListResource?.list?.error"
        :filtered="Boolean(savedRepliesSearchQuery) || activeFilter !== 'All'"
        :empty-icon="SavedReplyIcon"
        :empty-title="__('No saved replies yet')"
        :empty-message="
          __('Save an answer you give often, then insert it in any reply.')
        "
        @retry="savedRepliesListResource?.reload()"
        @clear-filters="clearFilters"
      >
        <template #default="{ item: savedReply }">
          <SettingsListItem
            :title="savedReply.title"
            @open="
              savedRepliesActiveScreen = {
                screen: 'view',
                data: savedReply,
              }
            "
          >
            <template #meta>
              <span
                class="hidden w-36 shrink-0 items-center gap-1.5 text-sm text-ink-gray-7 md:flex"
              >
                <Avatar
                  :label="
                    getUser(savedReply.owner)?.full_name || savedReply.owner
                  "
                  :image="getUser(savedReply.owner)?.user_image"
                  size="xs"
                  class="shrink-0"
                />
                <span class="truncate">{{
                  getUser(savedReply.owner)?.full_name || savedReply.owner
                }}</span>
              </span>
              <span
                class="flex w-24 shrink-0 items-center gap-1 text-sm text-ink-gray-7"
              >
                <component
                  :is="getScopeIcon(savedReply.scope)"
                  class="size-4 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                />
                {{ __(savedReply.scope) }}
              </span>
            </template>
            <template #actions>
              <Dropdown
                placement="right"
                :options="dropdownOptions(savedReply)"
              >
                <Button
                  variant="ghost"
                  :label="__('More actions for {0}', savedReply.title)"
                  @click="isConfirmingDelete = false"
                >
                  <template #icon>
                    <LucideEllipsis class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </Dropdown>
            </template>
          </SettingsListItem>
        </template>
      </SettingsList>
    </template>
  </SettingsLayoutBase>
  <DuplicateDialog
    v-model:open="duplicateDialog.show"
    v-model:name="duplicateDialog.newTitle"
    :title="__('Duplicate saved reply')"
    :label="__('Title of the copy')"
    :loading="savedRepliesListResource?.insert.loading"
    @duplicate="duplicate()"
  />
</template>

<script setup lang="ts">
import { useConfigStore } from "@/stores/config";
import { __ } from "@/translation";
import { ConfirmDelete } from "@/utils";
import { Avatar, Button, call, Dropdown, toast } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, inject, ref, Ref, watch } from "vue";
import GlobeIcon from "~icons/lucide/globe";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucidePlus from "~icons/lucide/plus";
import UserIcon from "~icons/lucide/user";
import UsersIcon from "~icons/lucide/users";
import { useUserStore } from "../../../stores/user";
import { SavedReply, SavedReplyListResourceSymbol } from "../../../types";
import SavedReplyIcon from "../../icons/SavedReplyIcon.vue";
import SettingsLayoutBase from "../../layouts/SettingsLayoutBase.vue";
import DuplicateDialog from "../DuplicateDialog.vue";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSearch from "../SettingsSearch.vue";
import { activeFilter } from "./savedReplies";

const { getUser } = useUserStore();
const { disableGlobalScopeForSavedReplies, teamRestrictionApplied } =
  storeToRefs(useConfigStore());

const savedRepliesSearchQuery = inject<Ref<string>>("savedRepliesSearchQuery");
const savedRepliesActiveScreen = inject<any>("savedRepliesActiveScreen");
const duplicateDialog = ref({
  show: false,
  name: "",
  title: "",
  newTitle: "",
});

const goToNew = () => {
  savedRepliesActiveScreen.value = {
    screen: "view",
    data: {
      scope: activeFilter.value
        ? activeFilter.value === "All"
          ? "Personal"
          : activeFilter.value
        : "Personal",
    },
  };
};

const isConfirmingDelete = ref(false);

const savedRepliesListResource = inject(SavedReplyListResourceSymbol);

const dropdownOptions = (savedReply: SavedReply) => [
  {
    label: __("Duplicate"),
    onClick: () => {
      duplicateDialog.value = {
        show: true,
        name: savedReply.name,
        title: savedReply.title,
        newTitle: `${savedReply.title} (Copy)`,
      };
    },
    icon: "lucide-copy",
  },
  ...ConfirmDelete({
    onConfirmDelete: () => deleteSavedReply(savedReply),
    isConfirmingDelete,
  }),
];

const deleteSavedReply = (savedReply: SavedReply) => {
  if (!isConfirmingDelete.value) {
    isConfirmingDelete.value = true;
    return;
  }

  savedRepliesListResource?.delete.submit(savedReply.name, {
    onSuccess: () => {
      toast.success(__("Saved reply deleted successfully."));
    },
  });
};

const duplicate = async () => {
  await call("frappe.client.get", {
    doctype: "HD Saved Reply",
    name: duplicateDialog.value.name,
  }).then((data: SavedReply) => {
    savedRepliesListResource?.insert.submit(
      {
        ...data,
        title: duplicateDialog.value.newTitle,
      },
      {
        onSuccess: (data) => {
          toast.success(__("Saved reply duplicated successfully."));
          duplicateDialog.value = {
            show: false,
            name: "",
            title: "",
            newTitle: "",
          };
          savedRepliesActiveScreen.value = {
            screen: "view",
            data: { name: data.name },
          };
        },
      }
    );
  });
};

const filterOptions = computed(() => {
  const scopes = [
    { label: __("All"), value: "All" },
    { label: __("Personal"), value: "Personal" },
    { label: __("My Team(s)"), value: "Team" },
    { label: __("Global"), value: "Global" },
  ];
  if (teamRestrictionApplied.value && disableGlobalScopeForSavedReplies.value) {
    scopes.pop();
  }
  return scopes.map((scope) => ({
    ...scope,
    selected: activeFilter.value === scope.value,
    onClick: () => applyFilter(scope.value),
  }));
});

const activeFilterLabel = computed(() => {
  return (
    filterOptions.value.find((option) => option.value === activeFilter.value)
      ?.label ?? activeFilter.value
  );
});

const applyFilter = (scope: string) => {
  if (!savedRepliesListResource) return;
  activeFilter.value = scope;
  savedRepliesListResource.filters = {
    ...savedRepliesListResource?.filters,
    scope: scope == "All" ? undefined : ["=", scope],
  };
  savedRepliesListResource.list.reload();
};

function clearFilters() {
  savedRepliesSearchQuery.value = "";
  applyFilter("All");
}

const getScopeIcon = (scope: string) => {
  const icons = [
    {
      label: __("Personal"),
      icon: UserIcon,
    },
    {
      label: __("Team"),
      icon: UsersIcon,
    },
    {
      label: __("Global"),
      icon: GlobeIcon,
    },
  ];
  return icons.find((x) => x.label === scope)?.icon;
};

watch(
  () => savedRepliesSearchQuery?.value,
  (newValue) => {
    if (!savedRepliesListResource) return;

    savedRepliesListResource.filters = {
      ...savedRepliesListResource.filters,
      title: ["like", `%${newValue}%`],
    };
    savedRepliesListResource.list.reload();
  }
);
</script>

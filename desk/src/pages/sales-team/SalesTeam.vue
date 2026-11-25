<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Sales team')"
      :subtitle="__('Your sales and presales people, and the roles they hold.')"
    >
      <template #right-header>
        <Button
          size="md"
          variant="solid"
          :label="__('Add to team')"
          :disabled="!team.data"
          @click="openRoles(null)"
        >
          <template #prefix>
            <LucideUserPlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto overflow-x-hidden">
      <div
        class="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 pb-8 pt-4 md:px-8"
      >
        <TaskyState
          v-if="team.error && !team.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base"
          :error="!isRefusal"
          :icon="isRefusal ? LucideLock : LucideCircleAlert"
          :title="
            isRefusal
              ? __('The sales team isn\'t open to you')
              : __('Couldn\'t load the sales team')
          "
          :message="
            errorText(team.error, __('Check your connection and try again.'))
          "
        >
          <Button
            v-if="!isRefusal"
            :label="__('Try again')"
            @click="team.reload()"
          />
        </TaskyState>

        <div
          v-else-if="!team.data"
          class="h-80 animate-pulse rounded-xl bg-surface-gray-3"
          aria-busy="true"
          :aria-label="__('Loading')"
        />

        <TaskyState
          v-else-if="!members.length"
          class="rounded-xl border border-outline-gray-2 bg-surface-base"
          :icon="LucideUsers"
          :title="__('No one is on the sales team yet')"
          :message="
            __(
              'Add agents as Sales Users, Presales Executives or Sales Employees.'
            )
          "
        >
          <Button
            variant="solid"
            :label="__('Add to team')"
            @click="openRoles(null)"
          />
        </TaskyState>

        <template v-else>
          <div class="flex flex-wrap items-center gap-2">
            <FormControl
              v-model="search"
              class="w-full sm:w-64"
              type="text"
              :placeholder="__('Search people')"
              :aria-label="__('Search people')"
            >
              <template #prefix>
                <LucideSearch
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
              </template>
            </FormControl>
            <TabButtons
              v-model="roleFilter"
              :aria-label="__('Role')"
              :options="roleOptions"
            />
          </div>

          <section
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-label="__('Sales team')"
          >
            <p
              v-if="!shown.length"
              class="px-4 py-10 text-center text-sm text-ink-gray-6"
            >
              {{ __("No one matches.") }}
            </p>
            <ul v-else class="divide-y divide-outline-gray-1">
              <li
                v-for="member in shown"
                :key="member.user"
                class="flex flex-wrap items-center gap-3 px-4 py-3"
              >
                <PersonAvatar :name="member.full_name" size="lg" />
                <div class="min-w-0 flex-1">
                  <div class="truncate text-base-medium text-ink-gray-9">
                    {{ member.full_name }}
                  </div>
                  <div class="truncate font-mono text-xs text-ink-gray-6">
                    {{ member.user }}
                  </div>
                </div>
                <div class="flex flex-wrap gap-1.5">
                  <TaskyBadge
                    v-for="role in member.roles"
                    :key="role"
                    :label="__(role)"
                  />
                </div>
                <div class="flex items-center gap-1">
                  <Button :label="__('Roles')" @click="openRoles(member)">
                    <template #prefix>
                      <LucideUserCog class="size-4" aria-hidden="true" />
                    </template>
                  </Button>
                  <Button
                    variant="ghost"
                    :aria-label="
                      __('Remove {0} from the team', member.full_name)
                    "
                    :tooltip="__('Remove from team')"
                    @click="removing = member"
                  >
                    <template #icon>
                      <LucideUserMinus class="size-4" aria-hidden="true" />
                    </template>
                  </Button>
                </div>
              </li>
            </ul>
          </section>
        </template>
      </div>
    </div>

    <MemberRolesDialog
      :open="rolesOpen"
      :member="editing"
      :roles="team.data?.roles ?? []"
      :candidates="team.data?.candidates ?? []"
      @close="rolesOpen = false"
      @saved="onSaved"
    />

    <Dialog
      :open="!!removing"
      :title="__('Remove from the sales team?')"
      size="sm"
      @update:open="(value: boolean) => !value && (removing = null)"
    >
      <p class="text-p-base text-ink-gray-8">
        {{
          __(
            "{0} loses their sales roles ({1}). Their account stays, and you can add them back any time.",
            removing?.full_name ?? "",
            (removing?.roles ?? []).map((r) => __(r)).join(", ")
          )
        }}
      </p>
      <ErrorMessage
        class="mt-3"
        :message="remove.error ? errorText(remove.error) : ''"
      />
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="removing = null" />
          <Button
            variant="solid"
            theme="red"
            :label="__('Remove')"
            :loading="remove.loading"
            @click="remove.submit({ user: removing?.user, roles: [] })"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideLock from "~icons/lucide/lock";
import LucideSearch from "~icons/lucide/search";
import LucideUserCog from "~icons/lucide/user-cog";
import LucideUserMinus from "~icons/lucide/user-minus";
import LucideUserPlus from "~icons/lucide/user-plus";
import LucideUsers from "~icons/lucide/users";
import MemberRolesDialog from "./MemberRolesDialog.vue";
import type { TeamCandidate, TeamMember } from "./salesTeam";

const team = createResource({
  url: "helpdesk.api.sales_team.get_team",
  auto: true,
}) as {
  data: { roles: string[]; members: TeamMember[]; candidates: TeamCandidate[] };
  error: any;
  loading: boolean;
  reload: () => void;
};
const isRefusal = computed(
  () => team.error?.exc_type === "SalesTeamForbiddenError"
);
const members = computed(() => team.data?.members ?? []);

const search = ref("");
const roleFilter = ref("");
const roleOptions = computed(() => [
  { label: __("All"), value: "" },
  ...(team.data?.roles ?? []).map((role) => ({
    label: __(role),
    value: role,
  })),
]);
const shown = computed(() => {
  const q = search.value.trim().toLowerCase();
  return members.value.filter(
    (m) =>
      (!roleFilter.value || m.roles.includes(roleFilter.value)) &&
      (!q ||
        m.full_name.toLowerCase().includes(q) ||
        m.user.toLowerCase().includes(q))
  );
});

const rolesOpen = ref(false);
const editing = ref<TeamMember | null>(null);
function openRoles(member: TeamMember | null) {
  editing.value = member;
  rolesOpen.value = true;
}
function onSaved() {
  rolesOpen.value = false;
  team.reload();
}

const removing = ref<TeamMember | null>(null);
const remove = createResource({
  url: "helpdesk.api.sales_team.set_member_roles",
  onSuccess() {
    toast.success(__("{0} is off the sales team", removing.value?.full_name));
    removing.value = null;
    team.reload();
  },
});
watch(removing, () => remove.reset());
</script>

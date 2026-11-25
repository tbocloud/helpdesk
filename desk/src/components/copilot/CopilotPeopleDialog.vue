<template>
  <Dialog
    v-model:open="show"
    :title="__('Copilot People for {0}', customer)"
    size="5xl"
  >
    <template #default>
      <div class="flex flex-col gap-4">
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "Who Copilot goes to for this customer. Main first, then Fallback 1, 2 and 3 when the one before is away; Until (optional) ends a temporary cover. An empty role uses the default:"
            )
          }}
        </p>
        <ul class="-mt-2 list-disc pl-5 text-p-sm text-ink-gray-6">
          <li>
            {{
              __(
                "Developer: the Ticket Owner, then the Backup Ticket Owner, then the common Developers"
              )
            }}
          </li>
          <li>{{ __("Fix Approver: the developers") }}</li>
          <li>
            {{
              __(
                "Project Coordinator: the common ones in HDS Copilot Settings → People"
              )
            }}
          </li>
        </ul>

        <div
          v-if="rows.length"
          class="flex flex-col divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
        >
          <fieldset
            v-for="(row, i) in rows"
            :key="row.key"
            class="grid grid-cols-1 items-end gap-3 p-3 sm:grid-cols-2 lg:grid-cols-[11rem_minmax(13rem,1.4fr)_7rem_9.5rem_minmax(8rem,1fr)_auto]"
          >
            <legend class="sr-only">{{ __("Person {0}", i + 1) }}</legend>
            <FormControl
              v-model="row.role"
              type="select"
              :label="__('Role')"
              :options="roleOptions"
            />
            <RecordCombobox
              v-model="row.person"
              doctype="HD Agent"
              :filters="{ is_active: 1 }"
              :label="__('Person')"
              :placeholder="__('Choose an agent')"
            />
            <FormControl
              v-model="row.level"
              type="select"
              :label="__('Level')"
              :options="levelOptions"
            />
            <FormControl v-model="row.until" type="date" :label="__('Until')" />
            <FormControl
              v-model="row.note"
              type="text"
              :label="__('Note')"
              :maxlength="140"
            />
            <div class="flex items-center gap-2 pb-1">
              <FormControl
                v-model="row.active"
                type="checkbox"
                :label="__('Active')"
              />
              <Button
                variant="ghost"
                :label="__('Remove person {0}', i + 1)"
                @click="rows.splice(i, 1)"
              >
                <template #icon>
                  <LucideTrash2 class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </fieldset>
        </div>
        <p
          v-else
          class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-5 text-center text-p-sm text-ink-gray-6"
        >
          {{ __("No people of its own: every role uses its default.") }}
        </p>

        <Button class="self-start" :label="__('Add person')" @click="add">
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>

        <ErrorMessage v-if="problem" :message="problem" />
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="show = false" />
        <Button
          variant="solid"
          :label="__('Save people')"
          :loading="savingFor === opening"
          @click="submit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import RecordCombobox from "./RecordCombobox.vue";
import { SETUP_API, type CopilotSetup, type PeopleRow } from "./setupMeta";

const props = defineProps<{
  customer: string;
  people: CopilotSetup["people"];
}>();
const emit = defineEmits<{ saved: [setup: CopilotSetup] }>();
const show = defineModel<boolean>({ default: false });

type EditRow = Omit<PeopleRow, "full_name"> & { key: number };

let next = 0;
const rows = ref<EditRow[]>([]);
const problem = ref("");

const roleOptions = computed(() =>
  props.people.roles.map((r) => ({ label: __(r), value: r }))
);
const levelOptions = computed(() =>
  props.people.levels.map((l) => ({ label: __(l), value: l }))
);

// a fresh copy each time it opens, so Cancel leaves the saved people as they were
// each opening (and each close) is a new opening: a save from an earlier one does not close this one
const opening = ref(0);
watch(
  show,
  (open) => {
    opening.value += 1;
    if (!open) return;
    problem.value = "";
    rows.value = props.people.rows.map((r) => ({
      key: next++,
      role: r.role,
      person: r.person,
      level: r.level,
      active: r.active,
      until: r.until,
      note: r.note,
    }));
  },
  { immediate: true }
);

function add() {
  rows.value.push({
    key: next++,
    role: props.people.roles[0],
    person: "",
    level: props.people.levels[0],
    active: true,
    until: "",
    note: "",
  });
}

const savingFor = ref<number | null>(null);

async function submit() {
  const mine = opening.value;
  problem.value = "";
  savingFor.value = mine;
  try {
    const data = (await call(`${SETUP_API}.save_people`, {
      name: props.customer,
      rows: JSON.stringify(
        rows.value.map((r) => ({
          role: r.role,
          person: r.person,
          level: r.level,
          active: r.active ? 1 : 0,
          until: r.until || null,
          note: r.note,
        }))
      ),
    })) as CopilotSetup;
    toast.success(__("Copilot People saved"));
    emit("saved", data);
    if (mine === opening.value) show.value = false;
  } catch (err) {
    if (mine === opening.value) {
      problem.value = errorText(err, __("Copilot People were not saved"));
    }
  } finally {
    if (savingFor.value === mine) savingFor.value = null;
  }
}
</script>

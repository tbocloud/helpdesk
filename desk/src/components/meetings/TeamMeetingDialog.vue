<template>
  <!-- kept open on outside clicks so a half-filled meeting isn't lost -->
  <Dialog
    v-model:open="open"
    :title="__('Schedule a meeting')"
    size="xl"
    :dismissible="false"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <TextInput
          v-model="form.subject"
          class="sm:col-span-2"
          :label="__('Purpose')"
          :placeholder="__('e.g. Weekly sales review')"
          maxlength="255"
          required
        />
        <FormControl
          v-model="form.meetingType"
          type="select"
          :label="__('Meeting type')"
          :options="typeOptions"
        />
      </div>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <TextInput
          v-model="form.date"
          type="date"
          :label="__('Date')"
          :min="today"
          required
        />
        <TextInput
          v-model="form.start"
          type="time"
          :label="__('Start time')"
          step="300"
          required
        />
        <TextInput
          v-model="form.end"
          type="time"
          :label="__('End time')"
          step="300"
          required
        />
      </div>
      <p v-if="timeError" role="alert" class="-mt-2 text-xs text-danger">
        {{ timeError }}
      </p>

      <fieldset class="flex flex-col gap-2">
        <legend
          class="mb-1.5 flex w-full items-center justify-between text-xs text-ink-gray-5"
        >
          <span>{{ __("People") }}</span>
          <span class="font-mono tabular-nums">
            {{ __("{0} added", String(form.people.length)) }}
          </span>
        </legend>
        <TextInput
          v-model="search"
          type="search"
          :placeholder="__('Search active employees')"
          :aria-label="__('Search people')"
        />
        <p
          v-if="busySelected.length"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-xs text-ink-gray-8"
        >
          <LucideCircleAlert
            class="mt-0.5 size-3.5 shrink-0 text-warning"
            aria-hidden="true"
          />
          {{
            __(
              "{0} has another meeting at this time or within 10 minutes of it. Pick another time or remove them.",
              busySelected.map((p) => p.full_name).join(", ")
            )
          }}
        </p>
        <div
          class="max-h-64 overflow-y-auto rounded-md border border-outline-gray-2"
          :aria-busy="people.loading"
        >
          <p
            v-if="!timeIsValid"
            class="px-3 py-4 text-center text-p-xs text-ink-gray-5"
          >
            {{ __("Pick the date and time to see who is free.") }}
          </p>
          <p
            v-else-if="people.loading && !people.data"
            role="status"
            class="px-3 py-4 text-center text-p-xs text-ink-gray-5"
          >
            {{ __("Checking who is free…") }}
          </p>
          <p
            v-else-if="!visiblePeople.length"
            class="px-3 py-4 text-center text-p-xs text-ink-gray-5"
          >
            {{ __("No active employee matches.") }}
          </p>
          <ul v-else role="list">
            <li
              v-for="person in visiblePeople"
              :key="person.user"
              class="border-b border-outline-gray-1 last:border-b-0"
            >
              <label
                class="flex items-center gap-3 px-3 py-2"
                :class="
                  person.busy && !isPicked(person)
                    ? 'cursor-not-allowed opacity-60'
                    : 'cursor-pointer hover:bg-surface-gray-1'
                "
              >
                <input
                  type="checkbox"
                  class="rounded border-outline-gray-3 text-ink-gray-9 focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                  :checked="isPicked(person)"
                  :disabled="!!person.busy && !isPicked(person)"
                  @change="toggle(person)"
                />
                <Avatar
                  size="sm"
                  :label="person.full_name"
                  :image="person.image"
                />
                <span class="flex min-w-0 flex-1 flex-col">
                  <span class="truncate text-sm text-ink-gray-8">
                    {{ person.full_name }}
                  </span>
                  <span
                    v-if="person.busy"
                    class="truncate text-p-xs text-ink-gray-5"
                  >
                    {{
                      __(
                        "In a meeting {0}: {1}",
                        busyTime(person.busy),
                        person.busy.subject
                      )
                    }}
                  </span>
                  <span v-else class="truncate text-p-xs text-ink-gray-5">
                    {{ person.email }}
                  </span>
                </span>
                <span
                  v-if="person.busy"
                  class="shrink-0 rounded px-1.5 text-2xs text-ink-gray-6 ring-1 ring-inset ring-outline-gray-3"
                >
                  {{ __("Busy") }}
                </span>
              </label>
            </li>
          </ul>
        </div>
      </fieldset>

      <Textarea
        v-model="form.agenda"
        :label="__('Notes (optional)')"
        :placeholder="__('What will you go through?')"
        :rows="3"
      />

      <label
        v-if="meetingsEnabled.data"
        class="flex items-center gap-2 text-sm text-ink-gray-8"
      >
        <input
          v-model="form.teamsLink"
          type="checkbox"
          class="rounded border-outline-gray-3 text-ink-gray-9 focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        />
        {{ __("Add a Teams link and send Outlook invitations") }}
      </label>

      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Schedule meeting')"
          :loading="schedule.loading"
          :disabled="!canSubmit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import { __ } from "@/translation";
import { watchDebounced } from "@vueuse/core";
import {
  Avatar,
  Button,
  Dialog,
  FormControl,
  TextInput,
  Textarea,
  createListResource,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import { meetingsEnabled } from "./meetingsBus";

interface BusyWith {
  name: string;
  subject: string;
  starts_on: string;
  ends_on: string;
}

interface Person {
  user: string;
  full_name: string;
  email: string;
  image: string | null;
  busy: BusyWith | null;
}

const props = defineProps<{
  /** the day clicked on the calendar (YYYY-MM-DD) */
  date?: string;
  /** the hour clicked in the week or day view (HH:mm) */
  time?: string;
}>();

const emit = defineEmits<{ scheduled: [name: string] }>();

const open = defineModel<boolean>("open", { default: false });

const formId = `team-meeting-${useId()}`;
const today = dayjs().format("YYYY-MM-DD");
const DEFAULT_MINUTES = 30;

const form = reactive({
  subject: "",
  meetingType: "",
  date: today,
  start: "",
  end: "",
  agenda: "",
  teamsLink: false,
  people: [] as string[],
});
const search = ref("");

const meetingTypes = createListResource({
  doctype: "HD Meeting Type",
  fields: ["name", "default_duration"],
  filters: { disabled: 0 },
  orderBy: "name asc",
  pageLength: 100,
  auto: true,
});

const typeOptions = computed(() => [
  { label: __("None"), value: "" },
  ...(meetingTypes.data ?? []).map((t: { name: string }) => ({
    label: t.name,
    value: t.name,
  })),
]);

function lengthOf(type: string) {
  const found = (meetingTypes.data ?? []).find(
    (t: { name: string }) => t.name === type
  );
  return found?.default_duration || DEFAULT_MINUTES;
}

function addMinutes(time: string, minutes: number) {
  return dayjs(`${today} ${time}`).add(minutes, "minute").format("HH:mm");
}

// the meeting's length: a type sets it to its usual one, moving the end changes
// it, and moving the start keeps it (the end moves along)
const length = ref(DEFAULT_MINUTES);
watch(
  () => form.meetingType,
  (type) => {
    length.value = lengthOf(type);
    if (form.start) form.end = addMinutes(form.start, length.value);
  }
);
watch(
  () => form.start,
  (start) => {
    if (start) form.end = addMinutes(start, length.value);
  }
);
watch(
  () => form.end,
  (end) => {
    const minutes = dayjs(`${today} ${end}`).diff(
      dayjs(`${today} ${form.start}`),
      "minute"
    );
    if (minutes > 0) length.value = minutes;
  }
);

const startsOn = computed(() => `${form.date} ${form.start}:00`);
const endsOn = computed(() => `${form.date} ${form.end}:00`);

const timeError = computed(() => {
  if (!form.date || !form.start || !form.end) return "";
  if (form.end <= form.start)
    return __("The meeting must end after it starts.");
  if (dayjs(startsOn.value).isBefore(dayjs().subtract(5, "minute")))
    return __("Pick a time in the future.");
  return "";
});
const timeIsValid = computed(
  () => !!form.date && !!form.start && !!form.end && !timeError.value
);

const people = createResource({
  url: "helpdesk.api.meetings.get_meeting_people",
  makeParams: () => ({ starts_on: startsOn.value, ends_on: endsOn.value }),
  onError() {},
});

// who is free changes with the time; ask once the typing settles
watchDebounced(
  () => [startsOn.value, endsOn.value, open.value],
  () => open.value && timeIsValid.value && people.fetch(),
  { debounce: 300 }
);

const allPeople = computed<Person[]>(() => people.data ?? []);

const visiblePeople = computed(() => {
  const term = search.value.trim().toLowerCase();
  const list = term
    ? allPeople.value.filter(
        (p) =>
          p.full_name.toLowerCase().includes(term) ||
          (p.email || "").toLowerCase().includes(term)
      )
    : allPeople.value;
  // the people added first, then who is free, then who is busy
  const rank = (p: Person) => (isPicked(p) ? 0 : p.busy ? 2 : 1);
  return [...list].sort((a, b) => rank(a) - rank(b));
});

const busySelected = computed(() =>
  allPeople.value.filter((p) => p.busy && isPicked(p))
);

function isPicked(person: Person) {
  return form.people.includes(person.user);
}

function toggle(person: Person) {
  form.people = isPicked(person)
    ? form.people.filter((u) => u !== person.user)
    : [...form.people, person.user];
}

function busyTime(busy: BusyWith) {
  return `${dayjs(busy.starts_on).format("HH:mm")}–${dayjs(busy.ends_on).format(
    "HH:mm"
  )}`;
}

const schedule = createResource({
  url: "helpdesk.api.meetings.schedule_team_meeting",
  onSuccess(data: { name: string }) {
    toast.success(__("Meeting scheduled. Everyone invited has been told."));
    emit("scheduled", data.name);
    open.value = false;
  },
  onError() {},
});

const errorMessage = computed(() =>
  errorText(schedule.error, __("Couldn't schedule the meeting."))
);

const canSubmit = computed(
  () =>
    !!form.subject.trim() &&
    timeIsValid.value &&
    form.people.length > 0 &&
    !busySelected.value.length &&
    !schedule.loading
);

function firstSlot() {
  // the hour clicked, else the next full hour (10:00 when that is outside 8:00–19:00)
  if (props.time) return props.time;
  const next = dayjs().add(1, "hour").startOf("hour");
  const isToday = !props.date || props.date === today;
  return isToday && next.hour() >= 8 && next.hour() < 19
    ? next.format("HH:mm")
    : "10:00";
}

function reset() {
  form.subject = "";
  form.meetingType = "";
  form.date = props.date && props.date >= today ? props.date : today;
  length.value = DEFAULT_MINUTES;
  form.start = firstSlot();
  form.end = addMinutes(form.start, DEFAULT_MINUTES);
  form.agenda = "";
  form.teamsLink = false;
  form.people = [];
  search.value = "";
  schedule.reset();
}

// after the resources exist: reset() clears their last error
watch(open, (isOpen) => isOpen && reset(), { immediate: true });

function submit() {
  if (!canSubmit.value) return;
  schedule.submit({
    subject: form.subject.trim(),
    meeting_type: form.meetingType || null,
    starts_on: startsOn.value,
    ends_on: endsOn.value,
    attendees: JSON.stringify(form.people),
    agenda: form.agenda.trim(),
    teams_link: form.teamsLink ? 1 : 0,
  });
}
</script>

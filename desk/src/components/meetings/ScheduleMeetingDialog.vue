<template>
  <!-- kept open on outside clicks so a half-filled invitation isn't lost -->
  <Dialog
    v-model:open="open"
    :title="__('Schedule Teams meeting')"
    size="lg"
    :dismissible="false"
  >
    <div
      v-if="defaults.loading && !defaults.data"
      class="flex flex-col gap-3 py-2"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div
        v-for="i in 4"
        :key="i"
        class="h-8 animate-pulse rounded bg-surface-gray-2"
      />
    </div>

    <form
      v-else
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <TextInput
        v-model="form.subject"
        :label="__('Subject')"
        maxlength="255"
        required
      />

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <TextInput
          v-model="form.date"
          type="date"
          :label="__('Date')"
          :min="today"
          required
        />
        <TextInput
          v-model="form.time"
          type="time"
          :label="__('Time')"
          step="300"
          required
        />
        <FormControl
          v-model="form.duration"
          type="select"
          :label="__('Length')"
          :options="durationOptions"
        />
      </div>

      <fieldset class="flex flex-col gap-2">
        <legend class="mb-1.5 text-xs text-ink-gray-5">
          {{ __("Attendees") }}
        </legend>
        <ul
          v-if="form.attendees.length"
          role="list"
          class="flex flex-wrap gap-1.5"
        >
          <li
            v-for="person in form.attendees"
            :key="person.email"
            class="flex max-w-full items-center gap-1 rounded-full border border-outline-gray-2 bg-surface-gray-1 py-0.5 pl-2.5 pr-1 text-sm text-ink-gray-8"
          >
            <span class="truncate" :title="person.email">
              {{ person.full_name || person.email }}
            </span>
            <button
              type="button"
              class="rounded-full p-0.5 text-ink-gray-5 hover:bg-surface-gray-3 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :aria-label="__('Remove {0}', person.full_name || person.email)"
              @click="removeAttendee(person.email)"
            >
              <LucideX class="size-3.5" aria-hidden="true" />
            </button>
          </li>
        </ul>
        <div class="flex items-end gap-2">
          <TextInput
            v-model="newEmail"
            class="flex-1"
            type="email"
            :placeholder="__('Add an email, e.g. accounts@customer.com')"
            :aria-label="__('Add attendee email')"
            @keydown.enter.prevent="addAttendee"
          />
          <Button :label="__('Add')" @click="addAttendee" />
        </div>
        <p v-if="emailError" role="alert" class="text-xs text-danger">
          {{ emailError }}
        </p>
      </fieldset>

      <Textarea
        v-model="form.agenda"
        :label="__('Agenda (optional)')"
        :placeholder="__('What will you go through? Attendees see this.')"
        :rows="3"
      />

      <p class="text-p-xs text-ink-gray-5">
        {{
          __(
            "Created in the Outlook calendar of {0}. Outlook emails the invitations with the Teams link, to customers too.",
            defaults.data?.organizer || __("the organizer")
          )
        }}
      </p>

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
          :label="__('Schedule and send invites')"
          :loading="schedule.loading"
          :disabled="!canSubmit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  FormControl,
  TextInput,
  Textarea,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideX from "~icons/lucide/x";

interface Attendee {
  email: string;
  full_name?: string;
}

interface MeetingDefaults {
  subject: string;
  attendees: Attendee[];
  duration: number;
  organizer: string;
}

const props = defineProps<{
  referenceDoctype: "HD Ticket" | "Task";
  referenceName: string;
}>();

const emit = defineEmits<{
  scheduled: [result: { name: string; join_url: string }];
}>();

const open = defineModel<boolean>("open", { default: false });

const formId = `schedule-meeting-${useId()}`;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const today = dayjs().format("YYYY-MM-DD");

const durationOptions = [15, 30, 45, 60, 90, 120].map((m) => ({
  label: m < 60 ? __("{0} min", String(m)) : __("{0} h", String(m / 60)),
  value: String(m),
}));

const form = reactive({
  subject: "",
  date: today,
  time: "",
  duration: "30",
  agenda: "",
  attendees: [] as Attendee[],
});
const newEmail = ref("");
const emailError = ref("");

function errorText(err: any, fallback: string) {
  if (!err) return "";
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || fallback;
}

const defaults = createResource({
  url: "helpdesk.api.meetings.get_meeting_defaults",
  makeParams: () => ({
    reference_doctype: props.referenceDoctype,
    reference_name: props.referenceName,
  }),
  onSuccess(data: MeetingDefaults) {
    form.subject = data.subject;
    form.attendees = [...data.attendees];
    form.duration = String(data.duration);
  },
  onError() {},
});

function nextSlot() {
  // the next full hour, or 10:00 tomorrow when that is after working hours
  const next = dayjs().add(1, "hour").startOf("hour");
  return next.hour() >= 19 || next.hour() < 8
    ? next.add(next.hour() >= 19 ? 1 : 0, "day").hour(10)
    : next;
}

function reset() {
  const slot = nextSlot();
  form.date = slot.format("YYYY-MM-DD");
  form.time = slot.format("HH:mm");
  form.agenda = "";
  newEmail.value = "";
  emailError.value = "";
  schedule.reset();
  defaults.fetch();
}

function addAttendee() {
  const email = newEmail.value.trim().toLowerCase();
  emailError.value = "";
  if (!email) return;
  if (!EMAIL.test(email)) {
    emailError.value = __("{0} doesn't look like an email address.", email);
    return;
  }
  if (!form.attendees.some((a) => a.email === email)) {
    form.attendees.push({ email });
  }
  newEmail.value = "";
}

function removeAttendee(email: string) {
  form.attendees = form.attendees.filter((a) => a.email !== email);
}

const schedule = createResource({
  url: "helpdesk.api.meetings.schedule_meeting",
  onSuccess(data: { name: string; join_url: string }) {
    toast.success(__("Meeting scheduled. Invitations are on their way."));
    emit("scheduled", data);
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
    !!form.date &&
    !!form.time &&
    form.attendees.length > 0 &&
    !schedule.loading
);

// after `schedule` exists: reset() clears its last error
watch(open, (isOpen) => isOpen && reset(), { immediate: true });

function submit() {
  // an email typed but not added yet still counts
  if (newEmail.value.trim()) addAttendee();
  if (!canSubmit.value) return;
  schedule.submit({
    reference_doctype: props.referenceDoctype,
    reference_name: props.referenceName,
    subject: form.subject.trim(),
    starts_on: `${form.date} ${form.time}:00`,
    duration: Number(form.duration),
    attendees: JSON.stringify(form.attendees),
    agenda: form.agenda.trim(),
  });
}
</script>

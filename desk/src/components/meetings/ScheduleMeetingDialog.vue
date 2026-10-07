<template>
  <!-- kept open on outside clicks so a half-filled invitation isn't lost -->
  <Dialog
    v-model:open="open"
    :title="started ? __('Teams meeting started') : __('Teams meeting')"
    size="lg"
    :dismissible="false"
  >
    <!-- Meet now: the link is ready -->
    <div v-if="started" class="flex flex-col gap-4">
      <p class="text-p-sm text-ink-gray-7">
        {{
          __(
            "Everyone you added has an Outlook invitation with this link. Share it with anyone else who should join."
          )
        }}
      </p>
      <div
        class="flex items-center gap-2 rounded-md border border-outline-gray-2 bg-surface-gray-1 px-3 py-2"
      >
        <LucideVideo
          class="size-4 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        <span class="min-w-0 flex-1 truncate font-mono text-xs text-ink-gray-7">
          {{ started.join_url }}
        </span>
      </div>
      <div class="flex flex-wrap gap-2">
        <Button
          variant="solid"
          :label="__('Join now')"
          :icon-left="LucideVideo"
          :link="started.join_url"
        />
        <Button
          :label="copied ? __('Copied') : __('Copy link')"
          :icon-left="copied ? LucideCheck : LucideCopy"
          @click="copyLink"
        />
        <Button
          v-if="referenceDoctype === 'HD Ticket'"
          :label="__('Add link to reply')"
          :icon-left="LucideReply"
          @click="addToReply"
        />
      </div>
    </div>

    <div
      v-else-if="defaults.loading && !defaults.data"
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
      <TabButtons
        v-model="mode"
        :buttons="[
          { label: __('Meet now'), value: 'now' },
          { label: __('Schedule for later'), value: 'later' },
        ]"
      />

      <TextInput
        v-model="form.subject"
        :label="__('Subject')"
        maxlength="255"
        required
      />

      <div
        class="grid grid-cols-1 gap-4"
        :class="mode === 'later' ? 'sm:grid-cols-3' : 'sm:grid-cols-2'"
      >
        <template v-if="mode === 'later'">
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
        </template>
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
        <div
          v-if="suggestions.length"
          class="flex flex-wrap items-center gap-1.5"
        >
          <span class="text-xs text-ink-gray-5">{{ __("Add:") }}</span>
          <button
            v-for="person in suggestions"
            :key="person.email"
            type="button"
            class="flex max-w-full items-center gap-1 rounded-full border border-dashed border-outline-gray-3 py-0.5 pl-1.5 pr-2.5 text-sm text-ink-gray-7 hover:border-outline-gray-4 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :title="person.email"
            @click="addPerson(person)"
          >
            <LucidePlus class="size-3.5 shrink-0" aria-hidden="true" />
            <span class="truncate">{{ person.full_name || person.email }}</span>
          </button>
        </div>
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
        v-if="mode === 'later'"
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
        <template v-if="started">
          <Button :label="__('Done')" @click="close" />
        </template>
        <template v-else>
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            :form="formId"
            :label="
              mode === 'now'
                ? __('Start meeting now')
                : __('Schedule and send invites')
            "
            :icon-left="mode === 'now' ? LucideVideo : undefined"
            :loading="busy"
            :disabled="!canSubmit"
          />
        </template>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import { insertIntoReply } from "@/pages/ticket/modalStates";
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  FormControl,
  TabButtons,
  TextInput,
  Textarea,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCopy from "~icons/lucide/copy";
import LucidePlus from "~icons/lucide/plus";
import LucideReply from "~icons/lucide/reply";
import LucideVideo from "~icons/lucide/video";
import LucideX from "~icons/lucide/x";

interface Attendee {
  email: string;
  full_name?: string;
}

interface MeetingDefaults {
  subject: string;
  attendees: Attendee[];
  suggestions: Attendee[];
  duration: number;
  organizer: string;
}

interface CreatedMeeting {
  name: string;
  join_url: string;
}

const props = withDefaults(
  defineProps<{
    referenceDoctype: "HD Ticket" | "Task";
    referenceName: string;
    // the tab the dialog opens on
    initialMode?: "now" | "later";
  }>(),
  { initialMode: "later" }
);

const emit = defineEmits<{
  scheduled: [result: CreatedMeeting];
}>();

const open = defineModel<boolean>("open", { default: false });

const formId = `schedule-meeting-${useId()}`;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const today = dayjs().format("YYYY-MM-DD");

const durationOptions = [15, 30, 45, 60, 90, 120].map((m) => ({
  label: m < 60 ? __("{0} min", String(m)) : __("{0} h", String(m / 60)),
  value: String(m),
}));

const mode = ref<"now" | "later">(props.initialMode);
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
const started = ref<CreatedMeeting | null>(null);
const copied = ref(false);

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

// suggestions not added yet (customer contacts, or the task's project team)
const suggestions = computed<Attendee[]>(() =>
  ((defaults.data as MeetingDefaults | undefined)?.suggestions ?? []).filter(
    (s) => !form.attendees.some((a) => a.email === s.email)
  )
);

function nextSlot() {
  // the next full hour, or 10:00 the next working morning outside 8:00–19:00
  const next = dayjs().add(1, "hour").startOf("hour");
  return next.hour() >= 19 || next.hour() < 8
    ? next.add(next.hour() >= 19 ? 1 : 0, "day").hour(10)
    : next;
}

function addPerson(person: Attendee) {
  if (!form.attendees.some((a) => a.email === person.email)) {
    form.attendees.push({ ...person });
  }
}

function addAttendee() {
  const email = newEmail.value.trim().toLowerCase();
  emailError.value = "";
  if (!email) return;
  if (!EMAIL.test(email)) {
    emailError.value = __("{0} doesn't look like an email address.", email);
    return;
  }
  addPerson({ email });
  newEmail.value = "";
}

function removeAttendee(email: string) {
  form.attendees = form.attendees.filter((a) => a.email !== email);
}

function onCreated(data: CreatedMeeting) {
  emit("scheduled", data);
  if (mode.value === "now") {
    // stay open with the link; opening Teams here would be blocked as a pop-up
    started.value = data;
  } else {
    toast.success(__("Meeting scheduled. Invitations are on their way."));
    open.value = false;
  }
}

const schedule = createResource({
  url: "helpdesk.api.meetings.schedule_meeting",
  onSuccess: onCreated,
  onError() {},
});

const startNow = createResource({
  url: "helpdesk.api.meetings.start_meeting_now",
  onSuccess: onCreated,
  onError() {},
});

const busy = computed(() => schedule.loading || startNow.loading);

const errorMessage = computed(() =>
  mode.value === "now"
    ? errorText(startNow.error, __("Couldn't start the meeting."))
    : errorText(schedule.error, __("Couldn't schedule the meeting."))
);

const canSubmit = computed(
  () =>
    !!form.subject.trim() &&
    form.attendees.length > 0 &&
    (mode.value === "now" || (!!form.date && !!form.time)) &&
    !busy.value
);

function reset() {
  const slot = nextSlot();
  mode.value = props.initialMode;
  form.date = slot.format("YYYY-MM-DD");
  form.time = slot.format("HH:mm");
  form.agenda = "";
  newEmail.value = "";
  emailError.value = "";
  started.value = null;
  copied.value = false;
  schedule.reset();
  startNow.reset();
  defaults.fetch();
}

// after the resources exist: reset() clears their last error
watch(open, (isOpen) => isOpen && reset(), { immediate: true });

function submit() {
  // an email typed but not added yet still counts
  if (newEmail.value.trim()) addAttendee();
  if (!canSubmit.value) return;
  const common = {
    reference_doctype: props.referenceDoctype,
    reference_name: props.referenceName,
    subject: form.subject.trim(),
    duration: Number(form.duration),
    attendees: JSON.stringify(form.attendees),
  };
  if (mode.value === "now") {
    startNow.submit(common);
    return;
  }
  schedule.submit({
    ...common,
    starts_on: `${form.date} ${form.time}:00`,
    agenda: form.agenda.trim(),
  });
}

async function copyLink() {
  if (!started.value) return;
  try {
    await navigator.clipboard.writeText(started.value.join_url);
    copied.value = true;
  } catch {
    toast.error(__("Couldn't copy. Select the link and copy it."));
  }
}

function escapeHtml(text: string) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function addToReply() {
  if (!started.value) return;
  const url = escapeHtml(started.value.join_url);
  insertIntoReply(
    props.referenceName,
    `<p>${escapeHtml(
      __("Please join our Teams meeting:")
    )} <a href="${url}">${url}</a></p>`
  );
  open.value = false;
}
</script>

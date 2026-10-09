<template>
  <Dialog v-model:open="open" :options="{ size: 'md' }">
    <template #body-title>
      <div class="flex flex-col gap-0.5">
        <h3 class="text-xl-semibold text-ink-gray-9">{{ copy.title }}</h3>
        <p v-if="post" class="truncate text-p-sm text-ink-gray-5">
          {{ post.title }} · {{ platformsOf(post).join(", ") }}
        </p>
      </div>
    </template>
    <template #body-content>
      <form
        v-if="post && action"
        id="entry-action-form"
        class="flex flex-col gap-4"
        @submit.prevent="submit"
      >
        <p v-if="copy.help" class="text-p-sm text-ink-gray-6">
          {{ copy.help }}
        </p>

        <FormControl
          v-if="action === 'publish'"
          v-model="url"
          type="url"
          :label="__('Published URL')"
          :placeholder="__('https://instagram.com/p/…')"
          required
        />

        <template v-if="action === 'postpone'">
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormControl
              v-model="date"
              type="date"
              :label="__('New posting date')"
              required
            />
            <FormControl
              v-model="time"
              type="time"
              format="h:mm A"
              :interval="5"
              :label="__('Time')"
              required
            />
          </div>
          <FormControl
            v-model="reason"
            type="textarea"
            :rows="3"
            :label="__('Reason')"
            :placeholder="__('e.g. Client approval delayed, creative pending')"
            required
          />
        </template>

        <FormControl
          v-if="action === 'cancel'"
          v-model="reason"
          type="textarea"
          :rows="3"
          :label="__('Reason (optional)')"
          :placeholder="__('Why is this post dropped?')"
        />

        <template v-if="action === 'assign'">
          <!-- picks made before everyone on the role loads would be overwritten -->
          <PeoplePicker
            v-if="teamLoaded"
            v-model="people"
            :label="__(roleLabel)"
            :placeholder="__('Pick one or more people')"
          />
          <p v-else-if="!error" class="text-p-sm text-ink-gray-5">
            {{ __("Loading who is on this role…") }}
          </p>
          <p class="text-p-sm text-ink-gray-5">
            {{
              __(
                "Everyone on this gets the post's task for it. Remove everyone to unassign."
              )
            }}
          </p>
        </template>

        <ErrorMessage :message="error" />
      </form>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Close')" @click="open = false" />
        <Button
          :variant="action === 'cancel' ? 'subtle' : 'solid'"
          :theme="action === 'cancel' ? 'red' : undefined"
          type="submit"
          form="entry-action-form"
          :loading="saving"
          :disabled="!teamLoaded"
          :label="copy.submit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  call,
  dayjs,
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import PeoplePicker from "./PeoplePicker.vue";
import {
  type ContentPost,
  type EntryAction,
  platformsOf,
  TEAM_ROLES,
  type TeamRole,
} from "../constants";

const props = defineProps<{
  post: ContentPost | null;
  action: EntryAction | null;
  role?: TeamRole;
}>();
const open = defineModel<boolean>("open", { default: false });
const emit = defineEmits<{ (e: "done"): void }>();

const url = ref("");
const date = ref("");
const time = ref("10:00");
const reason = ref("");
const people = ref<string[]>([]);
const error = ref("");
const saving = ref(false);
// saving before everyone on the role has loaded would take the others off it
const teamLoaded = ref(true);
let teamRequest = 0;

const roleLabel = computed(
  () => TEAM_ROLES.find((r) => r.field === props.role)?.label || "Assign"
);

const copy = computed(() => {
  switch (props.action) {
    case "publish":
      return {
        title: __("Mark as published"),
        help: __("Paste the link to the live post."),
        submit: __("Mark published"),
      };
    case "postpone":
      return {
        title: __("Postpone"),
        help: __(
          "Pick the new date and say why. The reason is kept on the post's history."
        ),
        submit: __("Postpone"),
      };
    case "cancel":
      return {
        title: __("Cancel this post"),
        help: __(
          "It leaves the calendar and never triggers a missed-post alert. You can find it again with the Cancelled filter."
        ),
        submit: __("Cancel post"),
      };
    default:
      return {
        title: __("Assign {0}", __(roleLabel.value).toLowerCase()),
        help: "",
        submit: __("Save"),
      };
  }
});

watch(open, (isOpen) => {
  if (!isOpen || !props.post) return;
  error.value = "";
  reason.value = "";
  url.value = props.post.published_url || "";
  people.value =
    props.role && props.post[props.role] ? [props.post[props.role]!] : [];
  const request = ++teamRequest;
  teamLoaded.value = true;
  if (props.action === "assign" && props.role) {
    const role = props.role;
    const name = props.post.name;
    teamLoaded.value = false;
    // the post list only carries the main person; everyone else comes from here
    call("helpdesk.api.content_board.get_team_task_status", { posts: [name] })
      .then((team) => {
        if (request !== teamRequest) return;
        const onRole = team?.[name]?.[role];
        if (onRole?.length)
          people.value = onRole.map((p: { user: string }) => p.user);
        teamLoaded.value = true;
      })
      .catch((e: any) => {
        if (request !== teamRequest) return;
        error.value =
          e?.messages?.[0] ||
          __("Couldn't load who is on this role. Close and try again.");
      });
  }
  const next = dayjs(props.post.publish_on || undefined).add(1, "day");
  date.value = next.format("YYYY-MM-DD");
  time.value = props.post.publish_on
    ? dayjs(props.post.publish_on).format("HH:mm")
    : "10:00";
});

async function submit() {
  if (!teamLoaded.value) return;
  const post = props.post!;
  error.value = "";
  saving.value = true;
  try {
    if (props.action === "publish") {
      await call("frappe.client.set_value", {
        doctype: "HD Content Post",
        name: post.name,
        fieldname: { status: "Published", published_url: url.value.trim() },
      });
      toast.success(__("Marked as published"));
    } else if (props.action === "postpone") {
      await call("helpdesk.api.content_board.postpone", {
        post: post.name,
        publish_on: `${date.value} ${time.value}:00`,
        reason: reason.value,
      });
      toast.success(
        __(
          "Moved to {0}",
          dayjs(`${date.value} ${time.value}`).format("D MMM, h:mm A")
        )
      );
    } else if (props.action === "cancel") {
      await call("helpdesk.api.content_board.cancel", {
        post: post.name,
        reason: reason.value,
      });
      toast.success(__("Post cancelled"));
    } else {
      await call("helpdesk.api.content_board.assign", {
        post: post.name,
        role: props.role,
        users: people.value,
      });
      toast.success(
        people.value.length ? __("Team updated") : __("Unassigned")
      );
    }
    open.value = false;
    emit("done");
  } catch (e: any) {
    error.value = e?.messages?.[0] || __("Something went wrong. Try again.");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Dialog v-model:open="open" :options="{ size: 'md' }">
    <template #body-title>
      <div class="flex flex-col gap-0.5">
        <h3 class="text-xl-semibold text-ink-gray-9">{{ copy.title }}</h3>
        <p v-if="post" class="truncate text-p-sm text-ink-gray-5">
          {{ post.title }} · {{ post.channel }}
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
          <div class="grid grid-cols-2 gap-3">
            <FormControl
              v-model="date"
              type="date"
              :label="__('New posting date')"
              required
            />
            <FormControl
              v-model="time"
              type="time"
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
          <Link
            v-model="user"
            doctype="User"
            :label="__(roleLabel)"
            :placeholder="__('Pick a person, or clear to unassign')"
          />
          <FormControl
            v-if="user"
            v-model="hours"
            type="number"
            min="0"
            step="0.5"
            :label="__('Estimated hours')"
            :placeholder="__('Default from Settings → Content')"
            :description="
              existingTask
                ? __('Updates task {0}.', existingTask.name)
                : __('A task is created for them, due on the post\'s date.')
            "
          />
          <p v-else-if="existingTask" class="text-p-sm text-ink-gray-5">
            {{ __("Unassigning cancels task {0}.", existingTask.name) }}
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
          :label="copy.submit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Link } from "@/components";
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
import {
  TEAM_ROLES,
  type ContentPost,
  type EntryAction,
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
const user = ref("");
const hours = ref<string | number>("");
const roleTasks = ref<
  { name: string; content_role: string; expected_time: number }[]
>([]);
const existingTask = computed(() =>
  roleTasks.value.find((t) => t.content_role === props.role)
);
const error = ref("");
const saving = ref(false);

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
  user.value = (props.role && props.post[props.role]) || "";
  hours.value = "";
  roleTasks.value = [];
  if (props.action === "assign") {
    call("helpdesk.api.content_board.get_role_tasks", { post: props.post.name })
      .then((tasks) => {
        roleTasks.value = tasks;
        if (existingTask.value?.expected_time)
          hours.value = existingTask.value.expected_time;
      })
      .catch(() => {});
  }
  const next = dayjs(props.post.publish_on || undefined).add(1, "day");
  date.value = next.format("YYYY-MM-DD");
  time.value = props.post.publish_on
    ? dayjs(props.post.publish_on).format("HH:mm")
    : "10:00";
});

async function submit() {
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
          dayjs(`${date.value} ${time.value}`).format("D MMM, HH:mm")
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
        user: user.value || null,
        hours: Number(hours.value) || null,
      });
      toast.success(user.value ? __("Assigned") : __("Unassigned"));
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

<template>
  <Dialog v-model:open="open" :options="{ size: '2xl' }" :dismissible="false">
    <template #body-title>
      <div class="flex flex-col gap-0.5">
        <h3 class="text-xl-semibold text-ink-gray-9">
          {{ __("Add content entry") }}
        </h3>
        <p v-if="form.customer" class="text-p-sm text-ink-gray-5">
          {{ form.customer }}
          <template v-if="form.date"
            >· {{ dayjs(form.date).format("dddd, D MMMM") }}</template
          >
        </p>
      </div>
    </template>
    <template #body-content>
      <form
        id="add-entry-form"
        class="flex flex-col gap-4"
        @submit.prevent="save(false)"
      >
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Link
            v-model="form.customer"
            doctype="HD Customer"
            :label="__('Customer') + ' *'"
            :placeholder="__('Select customer')"
          />
          <Link
            v-model="form.campaign"
            doctype="HD Content Campaign"
            :filters="form.customer ? { customer: form.customer } : undefined"
            :label="__('Campaign (optional)')"
            :placeholder="__('Select campaign')"
          />
          <FormControl
            v-model="form.date"
            type="date"
            :label="__('Posting date')"
            :description="
              form.date ? '' : __('Leave empty to keep it as an idea')
            "
          />
          <FormControl
            v-model="form.time"
            type="time"
            format="h:mm A"
            :interval="5"
            :label="__('Posting time')"
            :disabled="!form.date"
          />
        </div>

        <fieldset class="flex flex-col gap-1.5">
          <legend class="mb-1.5 text-xs text-ink-gray-5">
            {{ __("Platforms") }} ·
            <span class="text-ink-gray-5">{{
              __("one post is created for each")
            }}</span>
          </legend>
          <div class="flex flex-wrap gap-1.5">
            <ChipToggle
              v-for="channel in CHANNELS"
              :key="channel"
              :label="channel"
              :pressed="form.channels.includes(channel)"
              @toggle="toggleChannel(channel)"
            />
          </div>
        </fieldset>

        <fieldset class="flex flex-col gap-1.5">
          <legend class="mb-1.5 text-xs text-ink-gray-5">
            {{ __("Post type") }}
          </legend>
          <div class="flex flex-wrap gap-1.5" role="radiogroup">
            <ChipToggle
              v-for="format in FORMATS"
              :key="format"
              :label="format"
              role="radio"
              :pressed="form.format === format"
              @toggle="form.format = format"
            />
          </div>
        </fieldset>

        <FormControl
          ref="titleInput"
          v-model="form.title"
          :label="__('Campaign or topic')"
          :placeholder="__('e.g. Diwali offer carousel')"
          required
        />

        <div class="flex flex-col gap-1.5">
          <div class="flex items-center justify-between">
            <label for="entry-caption" class="text-xs text-ink-gray-5">{{
              __("Post content")
            }}</label>
            <span
              class="font-mono text-xs tabular-nums"
              :class="captionTooLong ? 'text-danger' : 'text-ink-gray-5'"
              >{{ form.caption.length.toLocaleString() }} /
              {{ CAPTION_LIMIT.toLocaleString() }}</span
            >
          </div>
          <textarea
            id="entry-caption"
            v-model="form.caption"
            rows="4"
            class="form-textarea w-full resize-y rounded border-0 bg-surface-gray-2 text-p-base text-ink-gray-8 placeholder-ink-gray-4 focus:bg-surface-base focus:ring-2 focus:ring-outline-gray-3"
            :placeholder="__('Write the caption here')"
          />
          <p v-if="captionTooLong" class="text-xs text-danger" role="alert">
            {{ __("Instagram cuts captions off after 2,200 characters.") }}
          </p>
        </div>

        <FormControl
          v-model="form.brief"
          type="textarea"
          :rows="2"
          :label="__('Brief for the creative team')"
          :placeholder="__('What should the design or video look like?')"
        />
        <FormControl
          v-model="form.hashtags"
          :label="__('Hashtags')"
          :placeholder="__('#diwali #offers')"
        />

        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-ink-gray-5">{{
            __("Team · filled in from this customer's last post")
          }}</span>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Link
              v-for="role in TEAM_ROLES"
              :key="role.field"
              v-model="form[role.field]"
              doctype="User"
              :label="__(role.label)"
              :placeholder="__('Assign')"
            />
          </div>
        </div>

        <ErrorMessage :message="error" />
      </form>
    </template>
    <template #actions>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <Button :label="__('Cancel')" @click="open = false" />
        <Button
          :label="__('Save and add next')"
          :loading="saving === 'next'"
          :disabled="!!saving"
          @click="save(true)"
        />
        <Button
          variant="solid"
          type="submit"
          form="add-entry-form"
          :loading="saving === 'close'"
          :disabled="!!saving"
          :label="
            form.channels.length > 1
              ? __('Save {0} posts', String(form.channels.length))
              : __('Save entry')
          "
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
import { computed, nextTick, reactive, ref, watch } from "vue";
import { CHANNELS, FORMATS, TEAM_ROLES, textToHtml } from "../constants";
import ChipToggle from "./ChipToggle.vue";

const CAPTION_LIMIT = 2200;

const props = defineProps<{ customer?: string; date?: string }>();
const open = defineModel<boolean>("open", { default: false });
const emit = defineEmits<{ (e: "saved"): void }>();

const EMPTY = {
  customer: "",
  campaign: "",
  date: "",
  time: "10:00",
  channels: ["Instagram"] as string[],
  format: "Post",
  title: "",
  caption: "",
  brief: "",
  hashtags: "",
  writer: "",
  designer: "",
  marketer: "",
};
const form = reactive({ ...EMPTY, channels: [...EMPTY.channels] });
const error = ref("");
const saving = ref<"" | "next" | "close">("");
const titleInput = ref();

const captionTooLong = computed(() => form.caption.length > CAPTION_LIMIT);

watch(open, (isOpen) => {
  if (!isOpen) return;
  error.value = "";
  Object.assign(form, EMPTY, {
    channels: [...EMPTY.channels],
    customer: props.customer || "",
    date: props.date || "",
  });
  loadTeam(form.customer);
});

watch(
  () => form.customer,
  (customer, previous) => {
    if (open.value && customer !== previous) loadTeam(customer);
  }
);

async function loadTeam(customer: string) {
  if (!customer) return;
  try {
    const team = await call("helpdesk.api.content_board.get_team_defaults", {
      customer,
    });
    for (const role of TEAM_ROLES) form[role.field] = team[role.field] || "";
  } catch {
    // defaults are a convenience; the entry can still be saved without them
  }
}

function toggleChannel(channel: string) {
  form.channels = form.channels.includes(channel)
    ? form.channels.filter((c) => c !== channel)
    : [...form.channels, channel];
}

async function save(addNext: boolean) {
  error.value = "";
  if (!form.customer) return (error.value = __("Select a customer"));
  if (!form.title.trim())
    return (error.value = __("Name the campaign or topic"));
  if (!form.channels.length)
    return (error.value = __("Pick at least one platform"));

  saving.value = addNext ? "next" : "close";
  try {
    const names = await call("helpdesk.api.content_board.add_entries", {
      channels: form.channels,
      values: {
        customer: form.customer,
        campaign: form.campaign,
        title: form.title.trim(),
        format: form.format,
        status: form.date ? "Drafting" : "Idea",
        publish_on: form.date
          ? `${form.date} ${form.time || "10:00"}:00`
          : null,
        caption: textToHtml(form.caption),
        brief: form.brief,
        hashtags: form.hashtags,
        writer: form.writer,
        designer: form.designer,
        marketer: form.marketer,
      },
    });
    toast.success(
      names.length > 1
        ? __("{0} posts added", String(names.length))
        : __("Entry added")
    );
    emit("saved");
    if (!addNext) {
      open.value = false;
      return;
    }
    // keep customer, date, platforms and team; clear what is specific to one post
    Object.assign(form, { title: "", caption: "", brief: "", hashtags: "" });
    await nextTick();
    titleInput.value?.$el?.querySelector("input")?.focus();
  } catch (e: any) {
    error.value = e?.messages?.[0] || __("Couldn't save the entry");
  } finally {
    saving.value = "";
  }
}
</script>

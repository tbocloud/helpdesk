<template>
  <section
    v-if="info?.can_decide"
    class="mx-6 mt-6 flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4 md:mx-10"
    :aria-labelledby="headingId"
  >
    <h2 :id="headingId" class="text-base font-medium text-ink-gray-9">
      {{ __("Is this solved?") }}
    </h2>
    <p v-if="info.message" class="whitespace-pre-line text-p-sm text-ink-gray-7">
      {{ info.message }}
    </p>
    <FormControl
      v-if="reopening"
      v-model="note"
      type="textarea"
      :label="__('What is still wrong?')"
    />
    <div class="flex flex-wrap gap-2">
      <template v-if="!reopening">
        <Button
          variant="solid"
          :label="__('Yes, it is fixed')"
          :loading="deciding === 'confirm'"
          :disabled="!!deciding"
          @click="decide(true)"
        />
        <Button
          :label="__('No, still broken')"
          :disabled="!!deciding"
          @click="reopening = true"
        />
      </template>
      <template v-else>
        <Button
          variant="solid"
          :label="__('Reopen the ticket')"
          :loading="deciding === 'reopen'"
          :disabled="!!deciding || !note.trim()"
          @click="decide(false)"
        />
        <Button :label="__('Back')" :disabled="!!deciding" @click="reopening = false" />
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl, call, createResource, toast } from "frappe-ui";
import { computed, ref, useId } from "vue";

const props = defineProps<{ ticketId: string }>();
const emit = defineEmits<{ decided: [] }>();

const headingId = `copilot-banner-${useId()}`;
const resource = createResource({
  url: "helpdesk.api.copilot.get_resolution",
  makeParams: () => ({ ticket: props.ticketId }),
  auto: true,
});
const info = computed(() => resource.data);
const deciding = ref<"" | "confirm" | "reopen">("");
const reopening = ref(false);
const note = ref("");

async function decide(confirmed: boolean) {
  deciding.value = confirmed ? "confirm" : "reopen";
  try {
    await call("helpdesk.api.copilot.decide_resolution", {
      ticket: props.ticketId,
      confirmed: confirmed ? 1 : 0,
      note: note.value,
    });
    resource.reload();
    toast.success(
      confirmed
        ? __("Thank you. The ticket is closed.")
        : __("Thank you. A person at TBO will take it over.")
    );
    emit("decided");
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't save your answer. Try again."));
  } finally {
    deciding.value = "";
  }
}
</script>

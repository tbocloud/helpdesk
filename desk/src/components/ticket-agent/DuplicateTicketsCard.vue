<template>
  <section
    v-if="duplicates.length"
    class="px-5 py-4"
    :aria-labelledby="headingId"
  >
    <h2
      :id="headingId"
      class="mb-2.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5"
    >
      <LucideCopy class="size-3.5" aria-hidden="true" />
      {{ __("Possible duplicates") }}
    </h2>
    <p class="mb-2 text-p-xs text-ink-gray-6">
      {{
        __(
          "Open tickets from the same customer that look like the same request."
        )
      }}
    </p>

    <ul role="list" class="flex flex-col gap-2">
      <li
        v-for="dup in duplicates"
        :key="dup.name"
        class="rounded-md border border-outline-gray-2 p-2.5"
      >
        <RouterLink
          :to="{ name: 'TicketAgent', params: { ticketId: dup.name } }"
          class="block rounded text-sm text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          <span class="font-mono tabular-nums text-ink-gray-6"
            >#{{ dup.name }}</span
          >
          {{ dup.subject }}
        </RouterLink>
        <p class="mt-1 text-xs text-ink-gray-5">
          {{ dup.status }} · {{ dayjs(dup.creation).fromNow() }} ·
          {{
            dup.same_subject
              ? __("same subject")
              : __("{0} words in common", String(dup.shared_words))
          }}
        </p>
        <Button
          class="mt-2"
          size="sm"
          :label="mergeLabel(dup)"
          :icon-left="LucideMerge"
          @click="pending = dup"
        />
      </li>
    </ul>

    <Dialog
      :open="!!pending"
      :title="__('Merge tickets?')"
      size="md"
      @update:open="(open: boolean) => !open && (pending = null)"
    >
      <p v-if="pending" class="text-p-base text-ink-gray-8">
        {{
          __(
            "Emails and comments of #{0} move to #{1}, and #{0} is closed. This can't be undone.",
            mergePair(pending).source,
            mergePair(pending).target
          )
        }}
      </p>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="pending = null" />
          <Button
            variant="solid"
            :label="__('Merge')"
            :loading="merge.loading"
            @click="confirmMerge"
          />
        </div>
      </template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, createResource, dayjs, Dialog, toast } from "frappe-ui";
import { computed, inject, ref, useId, watch } from "vue";
import { useRouter } from "vue-router";
import LucideCopy from "~icons/lucide/copy";
import LucideMerge from "~icons/lucide/merge";

interface Duplicate {
  name: string;
  subject: string;
  status: string;
  creation: string;
  same_subject: boolean;
  shared_words: number;
  is_older: boolean;
}

const props = defineProps<{ ticketId: string }>();
const refreshTicket = inject<() => void>("refreshTicket", () => {});
const router = useRouter();
const headingId = `duplicates-${useId()}`;
const pending = ref<Duplicate | null>(null);

const resource = createResource({
  url: "helpdesk.api.duplicates.get_possible_duplicates",
  makeParams: () => ({ ticket: props.ticketId }),
  auto: true,
});
watch(
  () => props.ticketId,
  () => resource.reload()
);

const duplicates = computed<Duplicate[]>(() => resource.data ?? []);

// the older ticket is the original: the newer one is merged into it
function mergePair(dup: Duplicate) {
  return dup.is_older
    ? { source: props.ticketId, target: dup.name }
    : { source: dup.name, target: props.ticketId };
}

function mergeLabel(dup: Duplicate) {
  return dup.is_older
    ? __("Merge this into #{0}", dup.name)
    : __("Merge #{0} into this", dup.name);
}

const merge = createResource({
  url: "helpdesk.helpdesk.doctype.hd_ticket.api.merge_ticket",
});

function confirmMerge() {
  if (!pending.value) return;
  const { source, target } = mergePair(pending.value);
  merge.submit(
    { source, target },
    {
      onSuccess() {
        pending.value = null;
        toast.success(__("Merged into #{0}", target));
        if (source === props.ticketId) {
          router.push({ name: "TicketAgent", params: { ticketId: target } });
        } else {
          refreshTicket();
          resource.reload();
        }
      },
      onError(err: any) {
        toast.error(err?.messages?.[0] || __("Couldn't merge the tickets"));
      },
    }
  );
}
</script>

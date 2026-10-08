<template>
  <section
    class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4 sm:flex-row sm:items-center sm:justify-between"
    :aria-labelledby="headingId"
  >
    <div class="flex min-w-0 flex-col gap-1">
      <h2 :id="headingId" class="text-base-medium text-ink-gray-9">
        {{ __("Was this article helpful?") }}
      </h2>
      <p class="text-p-sm text-ink-gray-6">
        <template v-if="_feedback === 2">
          {{ __("Sorry it didn't help.") }}
        </template>
        {{ __("Still stuck?") }}
        <RouterLink
          :to="{ name: 'TicketNew' }"
          class="rounded font-medium text-ink-gray-8 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ __("Raise a ticket") }}
        </RouterLink>
      </p>
    </div>
    <div class="flex shrink-0 items-center gap-2">
      <NativeButton
        v-for="option in options"
        :key="option.value"
        type="button"
        class="inline-flex h-11 items-center gap-1.5 rounded-md border px-3 sm:h-9 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 disabled:opacity-60"
        :class="
          _feedback === option.value
            ? 'border-brand bg-brand-soft text-brand-ink'
            : 'border-outline-gray-2 text-ink-gray-7 hover:border-outline-gray-4'
        "
        :aria-pressed="_feedback === option.value"
        :disabled="setFeedback.loading"
        @click="handleFeedbackClick(option.value)"
      >
        <component
          :is="_feedback === option.value ? option.filled : option.icon"
          class="size-4"
          aria-hidden="true"
        />
        {{ option.label }}
      </NativeButton>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  ThumbsDownFilledIcon,
  ThumbsDownIcon,
  ThumbsUpFilledIcon,
  ThumbsUpIcon,
} from "@/components/icons";
import NativeButton from "@/components/NativeButton";
import { setFeedback } from "@/stores/knowledgeBase";
import { __ } from "@/translation";
import { FeedbackAction } from "@/types";
import { errorText } from "@/utils";
import { toast } from "frappe-ui";
import { ref, useId } from "vue";

interface P {
  feedback: FeedbackAction;
  articleId: string;
}

const props = withDefaults(defineProps<P>(), {
  feedback: 0,
});

const _feedback = ref(props.feedback);
const emit = defineEmits(["articleReaction"]);
const headingId = `article-feedback-${useId()}`;

const options = [
  {
    value: 1 as FeedbackAction,
    label: __("Yes"),
    icon: ThumbsUpIcon,
    filled: ThumbsUpFilledIcon,
  },
  {
    value: 2 as FeedbackAction,
    label: __("No"),
    icon: ThumbsDownIcon,
    filled: ThumbsDownFilledIcon,
  },
];

function handleFeedbackClick(action: FeedbackAction) {
  if (action === _feedback.value) {
    return;
  }
  const previous = _feedback.value;
  _feedback.value = action;
  setFeedback.submit(
    { articleId: props.articleId, action },
    {
      onSuccess: () => {
        emit("articleReaction", _feedback.value);
        if (_feedback.value === 0) {
          return;
        }
        toast.success(__("Thanks for the feedback."));
      },
      onError: (error: unknown) => {
        _feedback.value = previous;
        toast.error(
          errorText(error, __("Your feedback wasn't saved. Please try again."))
        );
      },
    }
  );
}
</script>

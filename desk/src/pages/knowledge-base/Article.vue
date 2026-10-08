<template>
  <div>
    <LayoutHeader>
      <template #left-header>
        <div class="flex gap-2 items-center crumbs max-w-[50vw]">
          <Breadcrumbs :items="breadcrumbs" class="-ms-0.5 truncate" />
          <TaskyBadge
            v-if="!isCustomerPortal && article.data?.status"
            v-bind="articleStatus(article.data.status)"
          />
        </div>
      </template>
      <template #right-header v-if="!isCustomerPortal">
        <!-- Default Buttons -->
        <div class="flex gap-2" v-if="!editable && !article.loading">
          <Button
            :label="
              article.data?.status === 'Draft' ? __('Publish') : __('Unpublish')
            "
            :iconLeft="article.data?.status !== 'Published' && 'lucide-globe'"
            @click="toggleStatus()"
          />
        </div>
      </template>
    </LayoutHeader>

    <TaskyState
      v-if="article.error && !article.data"
      :icon="LucideFileX"
      :title="__('This article isn\'t available')"
      :message="
        errorText(
          article.error,
          __('It may have been unpublished or moved. Try the knowledge base.')
        )
      "
      error
    >
      <Button :label="__('Retry')" @click="article.reload()" />
      <Button
        :label="__('Knowledge base')"
        @click="
          $router.push({
            name: isCustomerPortal
              ? 'CustomerKnowledgeBase'
              : 'AgentKnowledgeBase',
          })
        "
      />
    </TaskyState>
    <!-- reading: the text at ~70 characters a line, contents beside it on wide screens -->
    <div
      v-else-if="!article.loading && article.data"
      class="mx-auto grid w-full gap-8 px-4 py-4 md:px-5"
      :class="
        showToc ? 'max-w-5xl lg:grid-cols-[minmax(0,1fr)_14rem]' : 'max-w-3xl'
      "
    >
      <div class="flex min-w-0 flex-col gap-6">
        <!-- article Info -->
        <div
          class="flex flex-col gap-3 w-full"
          :class="editable ? 'border rounded-lg overflow-hidden p-4' : 'py-4'"
        >
          <!-- Top Element -->
          <div class="flex flex-col gap-3">
            <!-- Title -->
            <div class="flex sm:flex-row flex-col justify-between">
              <div class="w-full">
                <h1
                  v-if="!editable"
                  class="text-3xl font-bold text-ink-gray-9 break-words"
                >
                  {{ title }}
                </h1>
                <textarea
                  v-else
                  ref="titleRef"
                  class="w-full resize-none border-0 text-4xl-bold bg-transparent placeholder-ink-gray-3 p-0 focus:ring-0 overflow-hidden"
                  v-model="title"
                  :placeholder="__('Title')"
                  rows="1"
                  wrap="soft"
                  maxlength="140"
                  autofocus
                  :disabled="!editable"
                />
                <div
                  v-if="!editable && isCustomerPortal"
                  class="flex gap-1 items-center pt-1.5"
                >
                  <!-- Avatar -->
                  <div class="flex gap-2 pb-1.5 items-center justify-center">
                    <Avatar
                      :image="article.data.author.image"
                      :label="article.data.author.name"
                      size="md"
                    />
                    <div class="flex gap-1 items-end">
                      <p class="truncate capitalize text-base text-ink-gray-7">
                        {{ article.data.author.name }}
                      </p>
                      <IconDot class="h-4 w-4 text-ink-gray-5" />
                      <div class="text-base text-ink-gray-7">
                        {{
                          dayjsLocal(article.data.modified).format(
                            "MMM D, h:mm A"
                          )
                        }}
                      </div>
                    </div>
                  </div>
                </div>
                <div
                  v-if="!editable && !isCustomerPortal && !isMobileView"
                  class="text-p-sm text-ink-gray-4 items-center"
                >
                  <span>{{ views }} views</span>
                </div>
              </div>
              <div class="flex gap-4 justify-between sm:items-start">
                <div class="flex gap-4 text-p-sm items-center">
                  <div
                    class="flex items-center gap-2"
                    v-if="!editable && !isCustomerPortal"
                  >
                    <Button
                      variant="ghost"
                      size="md"
                      class="flex shrink-0 !w-auto"
                      :disabled="!isCustomerPortal"
                    >
                      <template #suffix>
                        {{ likes }}
                      </template>
                      <template #icon>
                        <ThumbsUpFilledIcon
                          v-if="feedback === 1 && isCustomerPortal"
                          class="size-4"
                        />
                        <ThumbsUpIcon v-else class="size-4" />
                      </template>
                    </Button>
                    <Button
                      variant="ghost"
                      size="md"
                      class="flex shrink-0 !w-auto"
                      :disabled="!isCustomerPortal"
                    >
                      <template #suffix>
                        {{ dislikes }}
                      </template>
                      <template #icon>
                        <ThumbsDownFilledIcon
                          v-if="feedback === 2 && isCustomerPortal"
                          class="size-4"
                        />
                        <ThumbsDownIcon v-else class="size-4" />
                      </template>
                    </Button>
                  </div>
                </div>
                <div class="flex gap-1 items-start justify-between">
                  <Dropdown
                    :options="articleActions"
                    v-if="!editable && !isCustomerPortal"
                    @click="isConfirmingDeleteArticle = false"
                  >
                    <Button size="md" variant="ghost">
                      <template #icon>
                        <IconMoreHorizontal class="h-4 w-4" />
                      </template>
                    </Button>
                  </Dropdown>
                  <div class="flex gap-2" v-if="editable">
                    <DiscardButton
                      :disabled="!isDirty"
                      :hide-dialog="!isDirty"
                      :title="__('Discard changes?')"
                      :message="__('Are you sure you want to discard changes?')"
                      @discard="handleDiscard"
                    />

                    <Button
                      :label="__('Save')"
                      @click="handleSave"
                      variant="solid"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Article Content -->
          <div :class="!editable && 'max-w-[70ch]'">
            <Editor
              ref="editorRef"
              :model-value="textEditorContentWithIDs"
              :extensions="extensions"
              :editable="editable"
              :upload-function="(file:any) => uploadFunction(file, 'HD Article', articleId, false)"
              @change="(event:string) => { content = event; }"
              :placeholder="__('Write your article here...')"
            >
              <template #default>
                <EditorContent :class="editorClass" />
                <EditorFixedMenu
                  v-if="editable"
                  class="-ml-1 overflow-x-auto w-full"
                  :items="fullToolbar"
                />
              </template>
            </Editor>
          </div>
          <div
            v-if="!editable && !isCustomerPortal"
            class="flex gap-1 items-center pt-1.5 mt-4"
          >
            <!-- Avatar -->
            <div class="flex gap-2 items-center justify-center">
              <Avatar
                :image="article.data.author.image"
                :label="article.data.author.name"
                size="lg"
              />
              <div class="flex flex-col justify-start gap-1">
                <p
                  class="truncate capitalize text-p-base-medium text-ink-gray-9"
                >
                  <span class="text-base text-ink-gray-5">published by </span>
                  {{ article.data.author.name }}
                </p>
                <div class="flex items-center gap-1">
                  <span class="text-p-xs text-ink-gray-7">
                    {{
                      dayjsLocal(article.data.modified).format("MMM D, h:mm A")
                    }}
                  </span>
                  <IconDot
                    v-if="!editable && !isCustomerPortal && isMobileView"
                    class="h-4 w-4 text-ink-gray-5"
                  />

                  <span
                    v-if="!editable && !isCustomerPortal && isMobileView"
                    class="text-p-xs text-ink-gray-4 items-center"
                    >{{ views }} views</span
                  >
                </div>
              </div>
            </div>
          </div>
        </div>

        <template v-if="isCustomerPortal && !editable">
          <ArticleFeedback :feedback="feedback" :article-id="articleId" />
          <SectionCard
            v-if="
              relatedForThisArticle &&
              (related.loading || related.error || relatedArticles.length)
            "
            :title="__('Related articles')"
            :to="{
              name: 'Articles',
              params: { categoryId: article.data.category_id },
            }"
            :link-label="
              article.data.category_name
                ? __('All in {0}', [article.data.category_name])
                : __('All in this topic')
            "
          >
            <ArticleList
              :articles="relatedArticles"
              :loading="related.loading"
              :error="related.error"
              :empty-text="__('No other articles in this topic yet.')"
              @retry="related.reload()"
            />
          </SectionCard>
        </template>
      </div>
      <!-- table of contents: long articles, wide screens -->
      <nav
        v-if="showToc"
        class="hidden lg:block"
        :aria-label="__('On this page')"
      >
        <div class="sticky top-4 flex flex-col gap-2 py-4">
          <h2 class="text-sm font-medium text-ink-gray-8">
            {{ __("On this page") }}
          </h2>
          <ol class="flex flex-col border-l border-outline-gray-2">
            <li v-for="heading in headings" :key="heading.id">
              <a
                :href="`#${heading.id}`"
                class="-ml-px block border-l py-1 pr-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
                :class="[
                  heading.level > 2 ? 'pl-6' : 'pl-3',
                  activeHeading === heading.id
                    ? 'border-brand font-medium text-ink-gray-9'
                    : 'border-transparent text-ink-gray-6 hover:text-ink-gray-8',
                ]"
                :aria-current="
                  activeHeading === heading.id ? 'location' : undefined
                "
                @click.prevent="goToHeading(heading.id)"
              >
                {{ heading.text }}
              </a>
            </li>
          </ol>
        </div>
      </nav>
    </div>
    <!-- Loading State: the layout is known, so a skeleton -->
    <div
      v-if="article.loading && !article.data"
      class="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-8 md:px-5"
      aria-busy="true"
      :aria-label="__('Loading article')"
    >
      <div class="h-8 w-3/4 animate-pulse rounded bg-surface-gray-2" />
      <div class="h-4 w-1/3 animate-pulse rounded bg-surface-gray-2" />
      <div class="mt-4 h-4 w-full animate-pulse rounded bg-surface-gray-2" />
      <div class="h-4 w-full animate-pulse rounded bg-surface-gray-2" />
      <div class="h-4 w-5/6 animate-pulse rounded bg-surface-gray-2" />
    </div>
    <MoveToCategoryModal
      v-model="moveToModal"
      @move="handleMoveToCategory"
      :exclude-category="article.data?.category_id"
    />
    <CategoryModal
      :edit="editTitle"
      v-model:title="category.title"
      v-model="showCategoryModal"
      @create="handleCategoryCreate"
    />
  </div>
</template>

<script setup lang="ts">
import DiscardButton from "@/components/DiscardButton.vue";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { buildEditorExtensions, fullToolbar } from "@/components/editor/config";
import {
  ThumbsDownFilledIcon,
  ThumbsDownIcon,
  ThumbsUpFilledIcon,
  ThumbsUpIcon,
} from "@/components/icons";
import ArticleFeedback from "@/components/knowledge-base/ArticleFeedback.vue";
import ArticleList from "@/components/knowledge-base/ArticleList.vue";
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import CategoryModal from "@/components/knowledge-base/CategoryModal.vue";
import MoveToCategoryModal from "@/components/knowledge-base/MoveToCategoryModal.vue";
import { useScreenSize } from "@/composables/screen";
import { useAuthStore } from "@/stores/auth";
import {
  deleteRes as deleteArticle,
  incrementView,
  moveToCategory,
  newCategory,
  updateRes as updateArticle,
} from "@/stores/knowledgeBase";
import { capture } from "@/telemetry";
import { __ } from "@/translation";
import { Article, Breadcrumb, Error, FeedbackAction, Resource } from "@/types";
import {
  ConfirmDelete,
  copyToClipboard,
  errorText,
  isCustomerPortal,
  uploadFunction,
} from "@/utils";
import {
  Avatar,
  Breadcrumbs,
  Button,
  createResource,
  dayjsLocal,
  debounce,
  Dropdown,
  toast,
  usePageMeta,
} from "frappe-ui";
import { Editor, EditorContent, EditorFixedMenu } from "frappe-ui/editor";
import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import IconDot from "~icons/lucide/dot";
import IconMoreHorizontal from "~icons/lucide/more-horizontal";
import LucideFileX from "~icons/lucide/file-x";
import { articleStatus } from "./articleStatus";

const extensions = buildEditorExtensions();
const { isMobileView } = useScreenSize();

const props = defineProps({
  articleId: {
    type: String,
    required: true,
  },
});

const showCategoryModal = ref(false);
const editTitle = ref(false);

function handleCategoryCreate() {
  newCategory.submit(
    {
      title: category.title,
    },
    {
      onSuccess: (data: any) => {
        showCategoryModal.value = false;
        router.push({
          name: "Article",
          params: {
            articleId: data.article,
          },
          query: {
            category: data.category,
            title: category.title,
            isEdit: 1,
          },
        });
        //update category name in breadcrumb
        article.data.category_name = category.title;
        toast.success(__("Category created successfully."));
      },
      onError: (error: string) => {
        toast.error(error);
      },
    }
  );
}

const category = reactive({
  title: "",
  id: "",
});

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const editorRef = ref(null);
const editable = ref(route.query.isEdit ?? false);
const likes = ref(0);
const dislikes = ref(0);
const views = ref(0);
const content = ref("");
const title = ref("");
const feedback = ref<FeedbackAction>();

const titleRef = ref(null);
watch(
  () => titleRef.value,
  (newVal) => {
    if (!newVal) return;

    if (newVal.scrollHeight > newVal.clientHeight) {
      newVal.style.height = newVal.scrollHeight + "px";
    }
  }
);

const categories = createResource({
  url: "frappe.client.get_count",
  makeParams: () => ({
    doctype: "HD Article Category",
  }),
  auto: true,
});

const article: Resource<Article> = createResource({
  url: "helpdesk.api.knowledge_base.get_article",
  params: {
    name: props.articleId,
  },
  auto: true,
  onSuccess: (data: Article) => {
    content.value = data.content;
    title.value = data.title;
    feedback.value = data.feedback;
    if (isCustomerPortal.value && data.category_id) {
      related.fetch();
    }
    if (isCustomerPortal.value) {
      capture("article_viewed", {
        data: {
          user: authStore.userId,
          article: data.name,
          title: data.title,
        },
      });
      incrementArticleViews(data.name);
    }
  },
  onError: (err: Error) => {
    if (err.exc_type === "PermissionError") {
      router.replace({
        name: "CustomerKnowledgeBase",
      });
    }
  },
});

// other published articles in the same topic
const related = createResource({
  url: "helpdesk.api.knowledge_base.get_category_articles",
  makeParams: () => ({ category: article.data?.category_id }),
});
// only the current article's topic: an article without one shows no card, and a
// previous article's list never shows under the next one
const relatedForThisArticle = computed(
  () =>
    !!article.data?.category_id &&
    related.params?.category === article.data.category_id
);
const relatedArticles = computed(() =>
  (related.data || [])
    .filter((a: Article) => a.name !== props.articleId)
    .slice(0, 5)
);

const articleStats = createResource({
  url: "helpdesk.api.article.get_article_stats",
  params: { article_name: props.articleId },
  onSuccess(data) {
    likes.value = data.likes;
    dislikes.value = data.dislikes;
    views.value = data.views;
  },
  auto: true,
});

function incrementArticleViews(articleId: string) {
  incrementView.submit(
    {
      article: articleId,
    },
    {
      onError: (err: Error) => {
        if (err.exc_type === "RateLimitExceededError") {
          return;
        }
      },
    }
  );
}

const toggleStatus = debounce(() => {
  const status = article.data?.status === "Published" ? "Draft" : "Published";
  updateArticle.submit(
    {
      doctype: "HD Article",
      name: article.data.name,
      fieldname: "status",
      value: status,
    },
    {
      onSuccess: () => {
        if (status === "Published")
          toast.success("Article published successfully.");
        else toast.success("Article unpublished successfully.");
        article.reload();
      },
    }
  );
}, 300);
const isDirty = ref(false);

const moveToModal = ref(false);

function handleMoveToCategory(category: string) {
  moveToCategory.submit(
    {
      category,
      articles: [props.articleId],
    },
    {
      onSuccess: () => {
        article.reload();
        moveToModal.value = false;
        toast.success(__(`Article has been successfully moved.`));
      },
      onError: (error: Error) => {
        let msg = error?.messages?.[0] || error.message;
        toast.error(msg);
        moveToModal.value = false;
      },
    }
  );
}

function handleEditMode() {
  editable.value = true;
  editorRef.value.editor.chain().focus("end").run();
}

function handleDiscard() {
  editable.value = false;
  isDirty.value = false;
  title.value = article.data.title;
  content.value = article.data.content;
  const original = addLinksToHeadings(article.data.content);
  textEditorContentWithIDs.value = null;
  nextTick(() => {
    textEditorContentWithIDs.value = original;
  });
}

function hasParagraphContent(html: string) {
  if (!html) return false;
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const paragraphs = doc.querySelectorAll("p");
  return Array.from(paragraphs).some((p) => {
    return p.textContent.trim().length > 0;
  });
}

function handleSave() {
  const titleVal = title.value?.trim();
  const bodyText = hasParagraphContent(content.value);

  if (!titleVal) {
    toast.error(__("Article title cannot be set as empty"));
    return;
  }

  if (!bodyText) {
    toast.error(__("Article body cannot be set as empty."));
    return;
  }

  editable.value = false;
  handleArticleUpdate();
}

function handleArticleUpdate() {
  if (!isDirty.value) return;
  updateArticle.submit(
    {
      doctype: "HD Article",
      name: article.data.name,
      fieldname: {
        content: content.value,
        title: title.value,
      },
    },
    {
      onSuccess: () => {
        capture("article_updated", {
          data: {
            category: props.articleId,
          },
        });
        toast.success(__("Article updated successfully."));
        isDirty.value = false;
        article.reload();
      },
    }
  );
}

function handleDelete() {
  deleteArticle.submit(
    { doctype: "HD Article", name: article.data.name },
    {
      onSuccess: () => {
        toast.success(__("Article deleted successfully."));
        router.push({ name: "AgentKnowledgeBase" });
      },
    }
  );
}
const textEditorContentWithIDs = ref(null);
watch(
  () => article.data?.content,
  (newContent) => {
    if (newContent) {
      textEditorContentWithIDs.value = addLinksToHeadings(newContent);
    }
  },
  { immediate: true }
);

// the contents list: h2 and h3 of articles long enough to need one
const headings = computed(() => {
  if (!textEditorContentWithIDs.value) return [];
  const doc = new DOMParser().parseFromString(
    textEditorContentWithIDs.value,
    "text/html"
  );
  return Array.from(doc.querySelectorAll("h2, h3"))
    .map((h) => ({
      id: h.getAttribute("id") || "",
      text: h.textContent?.trim() || "",
      level: Number(h.tagName[1]),
    }))
    .filter((h) => h.id && h.text);
});
const showToc = computed(() => !editable.value && headings.value.length >= 3);

const activeHeading = ref("");
let headingObserver: IntersectionObserver | null = null;

function goToHeading(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  activeHeading.value = id;
  router.replace({ hash: `#${id}` });
}

watch(
  [showToc, headings],
  async () => {
    headingObserver?.disconnect();
    if (!showToc.value) return;
    await nextTick();
    headingObserver = new IntersectionObserver(
      (entries) => {
        const visible = entries.find((e) => e.isIntersecting);
        if (visible) activeHeading.value = visible.target.id;
      },
      { rootMargin: "0px 0px -70% 0px" }
    );
    headings.value.forEach((h) => {
      const el = document.getElementById(h.id);
      if (el) headingObserver?.observe(el);
    });
  },
  { immediate: true }
);
onUnmounted(() => headingObserver?.disconnect());

function addLinksToHeadings(content: string) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(content, "text/html");
  const headings = doc.querySelectorAll("h2, h3, h4, h5, h6");
  headings.forEach((heading) => {
    const text = heading.textContent.trim();
    const id = text.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
    heading.setAttribute("id", id);
  });
  return doc.body.innerHTML;
}
function scrollToHeading() {
  const articleHeading = window.location.hash;
  if (!articleHeading) return;
  const headingElement = document.querySelector(articleHeading) as HTMLElement;
  if (!headingElement) return;
  headingElement.scrollIntoView({ behavior: "smooth" });
  headingElement.classList.add("transition-all");
  const fontSize = headingElement.style.fontSize;
  setTimeout(() => {
    headingElement.style.fontSize = "1.5rem";
    setTimeout(() => {
      headingElement.style.fontSize = fontSize;
    }, 500);
  }, 500);
}

watch(articleStats.data, () => {
  if (articleStats.data) {
    likes.value = articleStats.data.likes;
    dislikes.value = articleStats.data.dislikes;
  }
});

watch([() => content.value, () => title.value], ([newContent, newTitle]) => {
  isDirty.value =
    newContent !== article.data.content || newTitle !== article.data.title;
});

const editorClass = computed(() => {
  return [
    "rounded-b-lg max-w-[unset]",
    editable.value
      ? "prose-sm overflow-auto h-[calc(100vh-340px)] sm:h-[calc(100vh-250px)]"
      : "prose-base",
  ];
});

const isConfirmingDeleteArticle = ref(false);

const articleActions = computed(() => [
  {
    label: __("Edit"),
    icon: "lucide-edit",
    onClick: () => {
      handleEditMode();
    },
  },

  ...(categories.data && categories.data > 1
    ? [
        {
          label: __("Move To"),
          icon: "lucide-corner-up-right",
          onClick: () => (moveToModal.value = true),
        },
      ]
    : [
        {
          label: __("Add Category"),
          icon: "lucide-folder-plus",
          onClick: () => (showCategoryModal.value = true),
        },
      ]),
  {
    label: __("Share"),
    icon: "lucide-link",
    onClick: () => {
      const url = new URL(window.location.href);
      url.pathname = `/helpdesk/kb-public/articles/${props.articleId}`;
      copyToClipboard(url.toString(), __("Article link copied to clipboard"));
    },
  },
  {
    group: __("Danger"),
    hideLabel: true,
    items: [
      ...ConfirmDelete({
        onConfirmDelete: handleDelete,
        isConfirmingDelete: isConfirmingDeleteArticle,
      }),
    ],
  },
]);

const breadcrumbs = computed(() => {
  const items: Breadcrumb[] = [
    {
      label: isMobileView.value ? "" : __("Knowledge base"),
      route: {
        name: isCustomerPortal.value
          ? "CustomerKnowledgeBase"
          : "AgentKnowledgeBase",
      },
    },
  ];
  if (article.data?.category_name) {
    let item = {
      label: article.data?.category_name,
    };
    if (isCustomerPortal.value) {
      item["route"] = {
        name: "Articles",
        params: {
          categoryId: article.data?.category_id,
        },
      };
    } else {
      item["route"] = {
        name: "AgentKnowledgeBase",
      };
    }
    items.push(item);
  }
  if (article.data?.title) {
    items.push({
      label: article.data?.title,
      route: { name: "Article" },
    });
  }
  return items;
});

onMounted(() => {
  setTimeout(() => {
    scrollToHeading();
  }, 100);
});

usePageMeta(() => {
  return {
    title: article.data?.title + ` - ${article.data?.category_name} `,
  };
});
</script>

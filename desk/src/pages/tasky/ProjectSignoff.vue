<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId">
      <template #actions>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="detail.loading && !!detail.data"
          @click="reloadAll"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="relative flex-1 overflow-auto">
      <div
        class="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-5 md:px-6"
      >
        <router-link
          :to="{ name: 'TaskySignoffs', params: { projectId } }"
          class="inline-flex w-fit items-center gap-1 rounded text-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        >
          <LucideArrowLeft class="size-4" aria-hidden="true" />
          {{ __("All sign-offs") }}
        </router-link>

        <TaskyState
          v-if="detail.error && !detail.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load this sign-off')"
          :message="loadErrorMessage(detail.error)"
        >
          <Button :label="__('Retry')" @click="detail.reload()" />
        </TaskyState>

        <div
          v-else-if="!s"
          class="flex flex-col gap-3"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="h-6 w-1/3 animate-pulse rounded bg-surface-gray-2" />
          <div class="h-4 w-1/2 animate-pulse rounded bg-surface-gray-2" />
          <div
            class="mt-2 h-40 w-full animate-pulse rounded-xl bg-surface-gray-1"
          />
        </div>

        <template v-else>
          <!-- header -->
          <header class="flex flex-col gap-3 md:flex-row md:items-start">
            <div class="flex min-w-0 flex-1 flex-col gap-1.5">
              <div class="flex min-w-0 flex-wrap items-center gap-2">
                <h2 class="truncate text-xl font-semibold text-ink-gray-9">
                  {{ s.module_title || s.template || s.name }}
                </h2>
                <TaskyBadge
                  :label="__(status.label)"
                  :tone="status.tone"
                  :icon="status.icon"
                />
                <span class="font-mono text-xs text-ink-gray-5">{{
                  s.name
                }}</span>
              </div>
              <p class="flex items-center gap-1.5 text-p-sm text-ink-gray-6">
                <component
                  :is="sentLine.icon"
                  class="size-4 shrink-0"
                  aria-hidden="true"
                />
                {{ sentLine.text }}
              </p>
            </div>

            <div class="flex shrink-0 flex-wrap items-center gap-2">
              <template v-if="s.status === 'Sent' && s.can_send">
                <Button
                  :label="__('Mark changes requested')"
                  @click="startChanges"
                />
                <Button
                  :label="__('Send reminder')"
                  @click="confirming = 'remind'"
                >
                  <template #prefix
                    ><LucideBellRing class="size-4" aria-hidden="true"
                  /></template>
                </Button>
                <Button
                  variant="solid"
                  :label="__('Mark signed off')"
                  @click="startSignedOff"
                >
                  <template #prefix
                    ><LucideBadgeCheck class="size-4" aria-hidden="true"
                  /></template>
                </Button>
              </template>
              <!-- a UAT's state the ERP site couldn't take yet (the history says why) -->
              <Button
                v-if="notRecorded && s.can_send"
                :label="__('Record on the ERP site')"
                :loading="busy === 'record'"
                @click="
                  run(
                    'record',
                    'record_uat_again',
                    {},
                    __('Recorded on the ERP site')
                  )
                "
              >
                <template #prefix
                  ><LucideRefreshCw class="size-4" aria-hidden="true"
                /></template>
              </Button>
              <a
                v-if="s.signed_pdf"
                :href="s.signed_pdf.file_url"
                target="_blank"
                rel="noopener"
                class="inline-flex h-7 items-center gap-1.5 rounded-md bg-surface-gray-2 px-2 text-base font-medium text-ink-gray-8 hover:bg-surface-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >
                <LucideDownload class="size-4" aria-hidden="true" />
                {{ __("Signed PDF") }}
              </a>
              <Dropdown v-if="menu.length" :options="menu" align="end">
                <Button
                  variant="ghost"
                  :aria-label="
                    __('More actions for {0}', s.module_title || s.name)
                  "
                >
                  <template #icon
                    ><LucideEllipsis class="size-4" aria-hidden="true"
                  /></template>
                </Button>
              </Dropdown>
            </div>
          </header>

          <p
            v-if="s.remarks && s.status !== 'Signed Off'"
            class="flex items-start gap-2 rounded-md px-3 py-2 text-p-sm text-ink-gray-9"
            :class="
              s.status === 'Cancelled' ? 'bg-surface-gray-2' : 'bg-warning-soft'
            "
          >
            <LucideRotateCcw
              v-if="s.status === 'Changes Requested'"
              class="mt-0.5 size-4 shrink-0 text-warning"
              aria-hidden="true"
            />
            <LucideCircleSlash
              v-else
              class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
              aria-hidden="true"
            />
            <span>
              {{
                s.status === "Cancelled"
                  ? __("Cancelled: {0}", s.remarks)
                  : __("Changes requested: {0}", s.remarks)
              }}
            </span>
          </p>

          <!-- Draft or Changes Requested: the full page's form -->
          <SignoffEditorForm
            v-if="s.can_edit"
            :project-id="projectId"
            :signoff="s"
            @saved="detail.reload()"
            @back="
              router.push({ name: 'TaskySignoffs', params: { projectId } })
            "
          />

          <!-- sent, signed off or cancelled: read-only, with its status actions -->
          <div
            v-else
            class="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
          >
            <div class="flex min-w-0 flex-col gap-4">
              <SectionCard :title="__('Details')">
                <dl
                  class="grid grid-cols-1 gap-x-6 gap-y-2 px-4 py-3 text-sm sm:grid-cols-[8rem_minmax(0,1fr)]"
                >
                  <dt class="text-ink-gray-5">{{ __("Customer") }}</dt>
                  <dd class="text-ink-gray-8">{{ s.customer_name }}</dd>
                  <dt class="text-ink-gray-5">{{ __("Address") }}</dt>
                  <dd class="whitespace-pre-line text-ink-gray-8">
                    {{ addressText || __("No address on file") }}
                  </dd>
                  <dt class="text-ink-gray-5">{{ __("To") }}</dt>
                  <dd class="min-w-0 text-ink-gray-8">
                    {{ s.signatory_name }}
                    <template v-if="s.signatory_designation"
                      >, {{ s.signatory_designation }}</template
                    >
                    <span class="block font-mono text-xs text-ink-gray-5">{{
                      s.signatory_email
                    }}</span>
                  </dd>
                  <template v-if="s.cc_emails">
                    <dt class="text-ink-gray-5">{{ __("CC") }}</dt>
                    <dd class="break-words font-mono text-xs text-ink-gray-7">
                      {{ s.cc_emails }}
                    </dd>
                  </template>
                  <template v-if="s.trainer_name">
                    <dt class="text-ink-gray-5">
                      {{ uat ? __("Tests with") : __("Trainer") }}
                    </dt>
                    <dd class="text-ink-gray-8">{{ s.trainer_name }}</dd>
                  </template>
                  <template v-if="s.training_date">
                    <dt class="text-ink-gray-5">{{ __("Training date") }}</dt>
                    <dd class="tabular-nums text-ink-gray-8">
                      {{ dateFormat(s.training_date, "D MMM YYYY") }}
                    </dd>
                  </template>
                  <template v-if="s.stage">
                    <dt class="text-ink-gray-5">{{ __("Stage") }}</dt>
                    <dd class="text-ink-gray-8">{{ __(s.stage) }}</dd>
                  </template>
                  <template v-if="s.template">
                    <dt class="text-ink-gray-5">{{ __("Template") }}</dt>
                    <dd class="text-ink-gray-8">{{ s.template }}</dd>
                  </template>
                  <template v-if="s.sent_pdf">
                    <dt class="text-ink-gray-5">{{ __("Document sent") }}</dt>
                    <dd>
                      <a
                        :href="s.sent_pdf.file_url"
                        target="_blank"
                        rel="noopener"
                        class="rounded text-ink-gray-8 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                        >{{ s.sent_pdf.file_name }}</a
                      >
                    </dd>
                  </template>
                </dl>
              </SectionCard>

              <SectionCard
                v-if="s.status === 'Signed Off'"
                :title="__('Signed off')"
                :icon="LucideBadgeCheck"
                icon-class="text-success"
              >
                <dl
                  class="grid grid-cols-1 gap-x-6 gap-y-2 px-4 py-3 text-sm sm:grid-cols-[8rem_minmax(0,1fr)]"
                >
                  <dt class="text-ink-gray-5">{{ __("Signed off by") }}</dt>
                  <dd class="text-ink-gray-8">
                    {{ s.signer_name
                    }}<template v-if="s.signer_designation"
                      >, {{ s.signer_designation }}</template
                    >
                    <span class="block font-mono text-xs text-ink-gray-5">{{
                      s.signer_email
                    }}</span>
                  </dd>
                  <dt class="text-ink-gray-5">{{ __("Signed off on") }}</dt>
                  <dd class="tabular-nums text-ink-gray-8">
                    {{ dateFormat(s.signed_on, "D MMM YYYY") }}
                  </dd>
                  <dt class="text-ink-gray-5">{{ __("Acceptance") }}</dt>
                  <dd class="text-ink-gray-8">
                    <template v-if="s.acceptance_reference">{{
                      __("Their reply, kept in the mail history")
                    }}</template>
                    <a
                      v-else-if="s.signed_copy"
                      :href="s.signed_copy"
                      target="_blank"
                      rel="noopener"
                      class="rounded underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                      >{{ __("Signed copy") }}</a
                    >
                    <template v-else>{{
                      __("Recorded without a reply in the mail history")
                    }}</template>
                  </dd>
                </dl>
              </SectionCard>

              <!-- the questions page's answers -->
              <template v-if="s.items.length">
                <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <StatTile
                    compact
                    :label="__(responseMeta('Done', uat).label)"
                    :value="
                      __(
                        '{0} of {1}',
                        String(s.counts.done),
                        String(s.counts.total)
                      )
                    "
                    :meter="(s.counts.done / s.counts.total) * 100"
                    :tone="
                      s.counts.done === s.counts.total ? 'success' : 'neutral'
                    "
                  />
                  <StatTile
                    compact
                    :label="__(responseMeta('Not clear', uat).label)"
                    :value="s.counts.not_clear"
                    :icon="LucideCircleHelp"
                    :icon-tone="s.counts.not_clear ? 'warning' : 'neutral'"
                  />
                  <StatTile
                    compact
                    :label="__(responseMeta('Escalated', uat).label)"
                    :value="s.counts.escalated"
                    :icon="LucideTriangleAlert"
                    :icon-tone="s.counts.escalated ? 'danger' : 'neutral'"
                  />
                  <StatTile
                    compact
                    :label="__('Waiting for an answer')"
                    :value="s.counts.pending"
                    :icon="LucideCircle"
                  />
                </div>
                <SectionCard
                  v-for="group in groups"
                  :key="group.section"
                  :title="group.section"
                  :count="group.items.length"
                >
                  <ol class="divide-y divide-outline-gray-1">
                    <li
                      v-for="item in group.items"
                      :key="item.name"
                      class="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-start sm:gap-4"
                    >
                      <div class="flex min-w-0 flex-1 gap-3">
                        <span
                          class="w-5 shrink-0 text-right font-mono text-xs tabular-nums text-ink-gray-5"
                          >{{ item.n }}</span
                        >
                        <div class="flex min-w-0 flex-1 flex-col gap-1">
                          <p class="text-p-base text-ink-gray-9">
                            {{ item.question }}
                          </p>
                          <p
                            v-if="item.help_text"
                            class="text-p-sm text-ink-gray-5"
                          >
                            {{ item.help_text }}
                          </p>
                          <blockquote
                            v-if="item.customer_comment"
                            class="mt-1 border-l-2 border-outline-gray-3 pl-3 text-p-sm text-ink-gray-7"
                          >
                            {{ item.customer_comment }}
                            <span class="block text-xs text-ink-gray-5">
                              {{ s.signatory_name
                              }}<template v-if="item.responded_on">
                                · {{ timeAgo(item.responded_on) }}</template
                              >
                            </span>
                          </blockquote>
                          <p
                            v-if="item.clarified_on"
                            class="flex items-start gap-1.5 text-p-sm text-ink-gray-6"
                          >
                            <LucideMessageCircleReply
                              class="mt-0.5 size-4 shrink-0"
                              aria-hidden="true"
                            />
                            <span>
                              {{
                                __(
                                  "Clarified by {0}, {1}",
                                  item.clarified_by_name || "",
                                  timeAgo(item.clarified_on)
                                )
                              }}<template v-if="item.clarification_note"
                                >: {{ item.clarification_note }}</template
                              >
                            </span>
                          </p>
                        </div>
                      </div>
                      <div
                        class="flex shrink-0 flex-wrap items-center gap-2 pl-8 sm:pl-0"
                      >
                        <TaskyBadge
                          :label="__(responseMeta(item.response, uat).label)"
                          :tone="responseMeta(item.response, uat).tone"
                          :icon="responseMeta(item.response, uat).icon"
                        />
                        <Button
                          v-if="item.clarification_task"
                          variant="ghost"
                          :label="__('Task')"
                          :aria-label="
                            __(
                              'Open the clarification task for question {0}',
                              String(item.n)
                            )
                          "
                          @click="
                            openTask = {
                              name: item.clarification_task,
                              project: s.project,
                              project_name: s.project_name,
                            }
                          "
                        >
                          <template #prefix
                            ><LucideSquareCheck
                              class="size-4"
                              aria-hidden="true"
                          /></template>
                        </Button>
                        <Button
                          v-if="
                            s.can_clarify &&
                            s.status === 'Sent' &&
                            needsFollowUp(item.response)
                          "
                          :label="uat ? __('Mark fixed') : __('Mark clarified')"
                          :aria-label="
                            uat
                              ? __('Mark test {0} fixed', String(item.n))
                              : __(
                                  'Mark question {0} clarified',
                                  String(item.n)
                                )
                          "
                          @click="startClarify(item)"
                        />
                      </div>
                    </li>
                  </ol>
                </SectionCard>
              </template>

              <!-- View mail history -->
              <SectionCard
                :title="__('Mail history')"
                :description="
                  __('Every mail sent and received for this sign-off.')
                "
                :count="mails.data?.length"
              >
                <p
                  v-if="mails.error"
                  class="px-4 py-3 text-p-sm text-danger"
                  role="alert"
                >
                  {{ errorText(mails.error, __("Couldn't load the mails.")) }}
                </p>
                <p
                  v-else-if="mails.data && !mails.data.length"
                  class="px-4 py-3 text-p-sm text-ink-gray-6"
                >
                  {{ __("No mails yet.") }}
                </p>
                <ul v-else class="divide-y divide-outline-gray-1">
                  <li v-for="m in mails.data ?? []" :key="m.name">
                    <button
                      type="button"
                      class="flex w-full flex-col gap-0.5 px-4 py-2.5 text-left hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
                      :aria-expanded="openMail === m.name"
                      @click="openMail = openMail === m.name ? null : m.name"
                    >
                      <span class="flex min-w-0 items-center gap-2">
                        <component
                          :is="
                            m.sent_or_received === 'Received'
                              ? LucideMailOpen
                              : LucideSend
                          "
                          class="size-4 shrink-0 text-ink-gray-5"
                          aria-hidden="true"
                        />
                        <span
                          class="min-w-0 flex-1 truncate text-sm font-medium text-ink-gray-9"
                          >{{ m.subject }}</span
                        >
                        <time
                          class="shrink-0 text-xs tabular-nums text-ink-gray-5"
                          :datetime="m.communication_date"
                          >{{
                            dateFormat(m.communication_date, "D MMM, h:mm A")
                          }}</time
                        >
                      </span>
                      <span class="truncate pl-6 text-xs text-ink-gray-6">
                        {{
                          m.sent_or_received === "Received"
                            ? __("From {0}", m.sender_full_name || m.sender)
                            : __("To {0}", m.recipients)
                        }}
                        <template v-if="m.cc">
                          · {{ __("CC {0}", m.cc) }}</template
                        >
                      </span>
                    </button>
                    <div v-if="openMail === m.name" class="px-4 pb-3">
                      <iframe
                        :title="m.subject"
                        sandbox=""
                        :srcdoc="mailDoc(m.content)"
                        class="h-72 w-full rounded border border-outline-gray-2 bg-white"
                      />
                      <div
                        v-if="m.attachments.length"
                        class="mt-2 flex flex-wrap gap-2"
                      >
                        <a
                          v-for="a in m.attachments"
                          :key="a.name"
                          :href="a.file_url"
                          target="_blank"
                          rel="noopener"
                          class="inline-flex items-center gap-1 rounded text-xs text-ink-gray-8 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                        >
                          <LucidePaperclip
                            class="size-3.5"
                            aria-hidden="true"
                          />
                          {{ a.file_name }}
                        </a>
                      </div>
                    </div>
                  </li>
                </ul>
              </SectionCard>

              <!-- history -->
              <SectionCard
                :title="__('History')"
                :description="__('Every step, with who took it and when.')"
              >
                <ol class="divide-y divide-outline-gray-1">
                  <li
                    v-for="(entry, i) in visibleLog"
                    :key="i"
                    class="flex flex-col gap-0.5 px-4 py-2.5 text-sm sm:flex-row sm:items-baseline sm:gap-4"
                  >
                    <span class="w-40 shrink-0 tabular-nums text-ink-gray-5">
                      <time
                        :datetime="entry.at"
                        :title="dateFormat(entry.at, dateTooltipFormat)"
                        >{{ dateFormat(entry.at, "D MMM, h:mm A") }}</time
                      >
                    </span>
                    <span class="min-w-0 flex-1 text-ink-gray-8">
                      <span class="font-medium">{{ __(entry.event) }}</span>
                      <template v-if="entry.item && itemNumber[entry.item]">
                        ·
                        {{
                          __("question {0}", String(itemNumber[entry.item]))
                        }}</template
                      >
                      <template v-if="entry.detail"
                        >:
                        <span class="text-ink-gray-7">{{
                          entry.detail
                        }}</span></template
                      >
                    </span>
                    <span class="shrink-0 text-ink-gray-6">{{
                      entry.by_name
                    }}</span>
                  </li>
                </ol>
                <div
                  v-if="s.log.length > visibleLog.length"
                  class="border-t border-outline-gray-1 px-4 py-2"
                >
                  <Button
                    variant="ghost"
                    :label="__('Show all {0}', String(s.log.length))"
                    @click="showAllLog = true"
                  />
                </div>
              </SectionCard>
            </div>

            <SignoffPreview
              class="lg:sticky lg:top-4 lg:max-h-[calc(100vh-8rem)]"
              :mail="{
                subject: s.email_subject || '',
                toName: s.signatory_name,
                toEmail: s.signatory_email,
                cc: splitEmails(s.cc_emails || ''),
                body: s.email_body || '',
              }"
              :signoff="s.name"
            />
          </div>
        </template>
      </div>
    </div>

    <TaskDetailDialog
      v-model:task="openTask"
      :mine="s?.trainer === auth.userId"
      @changed="detail.reload()"
    />

    <!-- mark clarified -->
    <Dialog
      :open="!!clarifying"
      :title="uat ? __('Mark fixed') : __('Mark clarified')"
      size="lg"
      @update:open="(v: boolean) => !v && (clarifying = null)"
    >
      <div class="flex flex-col gap-3">
        <p class="text-p-sm text-ink-gray-7">{{ clarifying?.question }}</p>
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "The item goes back to the customer to answer again, its task is closed, and the customer gets an email with a new link."
            )
          }}
        </p>
        <FormControl
          v-model="clarifyNote"
          type="textarea"
          :label="__('Note to the customer (optional)')"
          :placeholder="__('e.g. We went through it on a call on 12 Oct.')"
          :rows="3"
          maxlength="1000"
        />
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="clarifying = null" />
          <Button
            variant="solid"
            :label="uat ? __('Mark fixed') : __('Mark clarified')"
            :loading="busy === 'clarify'"
            @click="clarify"
          />
        </div>
      </template>
    </Dialog>

    <!-- mark signed off: from the customer's reply -->
    <Dialog
      :open="confirming === 'signed'"
      :title="__('Mark signed off')"
      size="lg"
      @update:open="(v: boolean) => !v && (confirming = null)"
    >
      <div class="flex flex-col gap-3">
        <p class="text-p-sm text-ink-gray-7">
          {{
            __(
              "Record that the customer accepted this sign-off. The signed PDF is saved on the project and sent to them and to our team."
            )
          }}
        </p>
        <FormControl
          v-model="signedOff.reply"
          type="select"
          :label="__('Their reply (acceptance reference)')"
          :options="replyOptions"
        />
        <p
          v-if="replyOptions.length === 1"
          class="-mt-2 text-p-xs text-ink-gray-5"
        >
          {{
            __(
              "No reply has come into the mail history. You can still record it, for example from a reply that came to another mailbox."
            )
          }}
        </p>
        <!-- the requirements' other acceptance: a signed copy of the document -->
        <div v-if="!signedOff.reply" class="flex flex-col gap-1.5">
          <span class="text-xs text-ink-gray-5">{{
            __("Signed copy (optional)")
          }}</span>
          <div class="flex flex-wrap items-center gap-2">
            <span
              v-if="signedOff.copy"
              class="truncate text-sm text-ink-gray-8"
              >{{ signedOff.copy.split("/").pop() }}</span
            >
            <FileUploader
              :upload-args="{ private: true }"
              @success="(file: { file_url: string }) => (signedOff.copy = file.file_url)"
            >
              <template #default="{ openFileSelector, uploading }">
                <Button
                  size="sm"
                  :label="signedOff.copy ? __('Replace') : __('Upload')"
                  :loading="uploading"
                  @click="openFileSelector()"
                />
              </template>
            </FileUploader>
          </div>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextInput
            v-model="signedOff.date"
            type="date"
            :label="__('Signed off on')"
            :max="today"
          />
          <FormControl
            v-model="signedOff.contact"
            type="select"
            :label="__('Signed off by')"
            :options="contactOptions"
          />
        </div>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="confirming = null" />
          <Button
            variant="solid"
            :label="__('Mark signed off')"
            :loading="busy === 'signed'"
            :disabled="!signedOff.date || busy === 'signed'"
            @click="markSignedOff"
          />
        </div>
      </template>
    </Dialog>

    <!-- changes requested, cancel: a reason each -->
    <Dialog
      :open="confirming === 'changes' || confirming === 'cancel'"
      :title="
        confirming === 'cancel'
          ? __('Cancel this sign-off?')
          : __('Mark changes requested')
      "
      size="lg"
      @update:open="(v: boolean) => !v && (confirming = null)"
    >
      <div class="flex flex-col gap-3">
        <p class="text-p-sm text-ink-gray-7">
          {{
            confirming === "cancel"
              ? __(
                  "A cancelled sign-off no longer counts; a signed-off training leaves the completion letter. The record stays, with your reason."
                )
              : __(
                  "The sign-off can be edited again and sent as a new mail in the same thread. The questions link stops working until then."
                )
          }}
        </p>
        <FormControl
          v-model="reason"
          type="textarea"
          :label="
            confirming === 'cancel'
              ? __('Reason')
              : __('What did the customer ask to change?')
          "
          :rows="3"
          maxlength="1000"
          required
        />
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Back')" @click="confirming = null" />
          <Button
            variant="solid"
            :theme="confirming === 'cancel' ? 'red' : 'gray'"
            :label="
              confirming === 'cancel'
                ? __('Cancel sign-off')
                : __('Mark changes requested')
            "
            :loading="busy === confirming"
            :disabled="!reason.trim()"
            @click="
              confirming === 'cancel'
                ? run(
                    'cancel',
                    'cancel_signoff',
                    { reason },
                    __('Sign-off cancelled')
                  )
                : run(
                    'changes',
                    'mark_changes_requested',
                    { remarks: reason },
                    __('Marked changes requested')
                  )
            "
          />
        </div>
      </template>
    </Dialog>

    <SignoffSendConfirm
      :open="confirming === 'remind'"
      reminder
      :name="s?.signatory_name || ''"
      :email="s?.signatory_email || ''"
      :cc="splitEmails(s?.cc_emails || '')"
      :loading="busy === 'remind'"
      @update:open="(v: boolean) => !v && (confirming = null)"
      @send="run('remind', 'send_signoff_reminder', {}, __('Reminder sent'))"
    />

    <!-- revoke, delete -->
    <Dialog
      :open="confirming === 'revoke' || confirming === 'delete'"
      :title="confirmCopy.title"
      :message="confirmCopy.message"
      size="md"
      @update:open="(v: boolean) => !v && (confirming = null)"
    >
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Back')" @click="confirming = null" />
          <Button
            variant="solid"
            theme="red"
            :label="confirmCopy.action"
            :loading="!!busy"
            @click="confirmCopy.run()"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat, errorText, timeAgo } from "@/utils";
import {
  Button,
  Dialog,
  Dropdown,
  FileUploader,
  FormControl,
  TextInput,
  call,
  createResource,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import LucideBadgeCheck from "~icons/lucide/badge-check";
import LucideBellRing from "~icons/lucide/bell-ring";
import LucideCircle from "~icons/lucide/circle";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideCircleHelp from "~icons/lucide/circle-help";
import LucideCircleSlash from "~icons/lucide/circle-slash";
import LucideDownload from "~icons/lucide/download";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideLinkOff from "~icons/lucide/link-2-off";
import LucideMailOpen from "~icons/lucide/mail-open";
import LucideMessageCircleReply from "~icons/lucide/message-circle-reply";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideRotateCcw from "~icons/lucide/rotate-ccw";
import LucideSend from "~icons/lucide/send";
import LucideSquareCheck from "~icons/lucide/square-check";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import ProjectNav from "./components/ProjectNav.vue";
import SignoffEditorForm from "./components/SignoffEditorForm.vue";
import SignoffPreview from "./components/SignoffPreview.vue";
import SignoffSendConfirm from "./components/SignoffSendConfirm.vue";
import TaskDetailDialog, {
  type TaskRef,
} from "./components/TaskDetailDialog.vue";
import {
  groupBySection,
  needsFollowUp,
  responseMeta,
  signoffStatusMeta,
  type SignoffQuestion,
} from "./signoffMeta";
import { loadErrorMessage } from "./taskMeta";
import { splitEmails, type SignoffSource } from "./useSignoffForm";

interface SignoffItem extends SignoffQuestion {
  name: string;
  response: string;
  customer_comment?: string | null;
  responded_on?: string | null;
  clarification_task?: string | null;
  clarified_on?: string | null;
  clarified_by_name?: string | null;
  clarification_note?: string | null;
}

interface SignoffDetail extends SignoffSource {
  name: string;
  project: string;
  project_name: string;
  customer_name?: string | null;
  address_display?: string | null;
  module_title: string;
  /** Training, or UAT (Pass / Fail / Blocker against the SRS's tests) */
  signoff_type: "Training" | "UAT";
  /** a UAT's last state on the ERP site (Signed, Reopened) */
  crm_recorded?: string | null;
  crm_failed?: boolean;
  status: string;
  trainer_name?: string | null;
  signatory_name: string;
  signatory_email: string;
  signatory_designation?: string | null;
  link_open: boolean;
  link_sent_on?: string | null;
  reminder_sent_on?: string | null;
  /** the status in the customer's terms (Viewed) */
  customer_status?: string;
  remarks?: string | null;
  sent_pdf?: { file_name: string; file_url: string } | null;
  signed_on?: string | null;
  signer_name?: string | null;
  signer_designation?: string | null;
  signer_email?: string | null;
  signed_off_by?: string | null;
  acceptance_reference?: string | null;
  signed_copy?: string | null;
  signed_pdf?: { file_name: string; file_url: string } | null;
  counts: {
    total: number;
    done: number;
    not_clear: number;
    escalated: number;
    pending: number;
  };
  items: SignoffItem[];
  log: {
    event: string;
    item?: string | null;
    detail?: string | null;
    by_name?: string | null;
    at: string;
  }[];
  can_edit: boolean;
  can_send: boolean;
  can_clarify: boolean;
  can_cancel: boolean;
}

interface SignoffMail {
  name: string;
  subject: string;
  content: string;
  sender: string;
  sender_full_name?: string | null;
  recipients: string;
  cc?: string | null;
  sent_or_received: "Sent" | "Received";
  communication_date: string;
  attachments: { name: string; file_name: string; file_url: string }[];
}

const props = defineProps<{ projectId: string; signoffId: string }>();
const router = useRouter();
const auth = useAuthStore();

const detail = createResource({
  url: "helpdesk.api.project_signoff.get_signoff",
  makeParams: () => ({ signoff: props.signoffId }),
  auto: true,
  onError() {},
});
const mails = createResource({
  url: "helpdesk.api.project_signoff.get_signoff_mails",
  makeParams: () => ({ signoff: props.signoffId }),
  auto: true,
  onError() {},
});
function reloadAll() {
  detail.reload();
  mails.reload();
}
watch(() => props.signoffId, reloadAll);

const s = computed(() => detail.data as SignoffDetail | undefined);
const uat = computed(() => s.value?.signoff_type === "UAT");
// the ERP site's words for the UAT's state now
const erpState = computed(
  () =>
    ((
      { "Signed Off": "Signed", Cancelled: "Reopened" } as Record<
        string,
        string
      >
    )[s.value?.status ?? ""])
);
// signed off or cancelled here, but the ERP site's plan doesn't have it yet
const notRecorded = computed(
  () =>
    uat.value &&
    !!erpState.value &&
    s.value?.crm_recorded !== erpState.value &&
    // not while the first try is still queued: only once one failed
    !!s.value?.crm_failed
);
// in the customer's terms: Sent turns Viewed once they opened the link with their code
const status = computed(() =>
  signoffStatusMeta(s.value?.customer_status ?? s.value?.status ?? "Draft")
);
const groups = computed(() =>
  groupBySection(s.value?.items ?? [], __("General"))
);
const itemNumber = computed(() =>
  Object.fromEntries(
    (s.value?.items ?? []).map((item, i) => [item.name, i + 1])
  )
);
const addressText = computed(() =>
  (s.value?.address_display || "").replace(/<br\s*\/?>/gi, "\n").trim()
);

const showAllLog = ref(false);
const visibleLog = computed(() =>
  showAllLog.value ? s.value?.log ?? [] : (s.value?.log ?? []).slice(0, 8)
);

const sentLine = computed(() => {
  const d = s.value!;
  if (d.status === "Signed Off")
    return {
      icon: LucideBadgeCheck,
      text: __("Signed off {0}", dateFormat(d.signed_on, "D MMM YYYY")),
    };
  if (d.status === "Sent" && d.reminder_sent_on)
    return {
      icon: LucideSend,
      text: __(
        "Sent {0}; reminder sent {1}",
        dateFormat(d.link_sent_on, "D MMM YYYY"),
        dateFormat(d.reminder_sent_on, "D MMM YYYY")
      ),
    };
  if (d.status === "Sent")
    return {
      icon: LucideSend,
      text: __(
        "Sent {0}; waiting for the customer's reply",
        dateFormat(d.link_sent_on, "D MMM YYYY")
      ),
    };
  if (d.status === "Changes Requested")
    return {
      icon: LucideRotateCcw,
      text: __("The customer asked for changes: edit it and send it again"),
    };
  if (d.status === "Cancelled")
    return { icon: LucideCircleSlash, text: __("Cancelled") };
  return { icon: LucideCircleDashed, text: __("Not sent to the customer yet") };
});

function mailDoc(content: string) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    body{font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;font-size:14px;
    line-height:1.55;color:#1f2430;margin:12px;overflow-wrap:anywhere}</style></head>
    <body>${content || ""}</body></html>`;
}
const openMail = ref<string | null>(null);

const openTask = ref<TaskRef | null>(null);
const busy = ref<string | null>(null);
const confirming = ref<
  "remind" | "signed" | "changes" | "cancel" | "revoke" | "delete" | null
>(null);
const reason = ref("");
const clarifying = ref<SignoffItem | null>(null);
const clarifyNote = ref("");

const menu = computed(() => {
  const d = s.value;
  if (!d) return [];
  const items = [];
  if (d.link_open && d.can_send)
    items.push({
      label: __("Revoke questions link"),
      icon: LucideLinkOff,
      onClick: () => (confirming.value = "revoke"),
    });
  if (d.status === "Draft" && d.can_edit)
    items.push({
      label: __("Delete draft"),
      icon: LucideTrash2,
      onClick: () => (confirming.value = "delete"),
    });
  if (d.can_cancel)
    items.push({
      label: __("Cancel sign-off"),
      icon: LucideCircleSlash,
      onClick: () => {
        reason.value = "";
        confirming.value = "cancel";
      },
    });
  return items;
});

const confirmCopy = computed(() => {
  if (confirming.value === "delete")
    return {
      title: __("Delete this draft?"),
      message: __("The customer has never seen it. This can't be undone."),
      action: __("Delete draft"),
      run: () => remove(),
    };
  if (confirming.value === "send")
    return {
      title: __("Send the sign-off?"),
      message: __(
        "The mail goes to {0} ({1}) with their link to sign.",
        s.value?.signatory_name ?? "",
        email
      ),
      action: __("Send"),
      run: () => send(),
    };
  return {
    title: __("Revoke the questions link?"),
    message: __(
      "The link stops working at once, and the customer can't answer the questions until you send the mail again."
    ),
    action: __("Revoke link"),
    run: () => run("revoke", "revoke_signoff_link", {}, __("Link revoked")),
  };
});

async function run(
  key: string,
  method: string,
  args: Record<string, unknown>,
  success: string
) {
  busy.value = key;
  try {
    await call(`helpdesk.api.project_signoff.${method}`, {
      signoff: props.signoffId,
      ...args,
    });
    toast.success(success);
    confirming.value = null;
    clarifying.value = null;
    reloadAll();
  } catch (e) {
    toast.error(errorText(e, __("That didn't work. Try again.")));
  } finally {
    busy.value = null;
  }
}

function startChanges() {
  reason.value = "";
  confirming.value = "changes";
}

// ---------- mark signed off ----------

const today = new Date().toISOString().slice(0, 10);
const signedOff = reactive({ reply: "", date: today, contact: "", copy: "" });
const contacts = ref<{ contact: string; full_name: string; email: string }[]>(
  []
);
const replies = computed(
  () =>
    (mails.data as SignoffMail[] | undefined)?.filter(
      (m) => m.sent_or_received === "Received"
    ) ?? []
);
const replyOptions = computed(() => [
  ...replies.value.map((m) => ({
    label: `${dateFormat(m.communication_date, "D MMM, h:mm A")} · ${
      m.sender_full_name || m.sender
    }: ${m.subject}`,
    value: m.name,
  })),
  { label: __("No reply in the mail history"), value: "" },
]);
const contactOptions = computed(() => {
  const own = {
    label: s.value?.signatory_name || "",
    value: s.value?.signatory_contact || "",
  };
  return [
    own,
    ...contacts.value
      .filter((c) => c.contact !== own.value)
      .map((c) => ({ label: c.full_name, value: c.contact })),
  ];
});

async function startSignedOff() {
  const reply = replies.value[0];
  Object.assign(signedOff, {
    copy: "",
    reply: reply?.name ?? "",
    date: reply ? reply.communication_date.slice(0, 10) : today,
    contact: s.value?.signatory_contact || "",
  });
  confirming.value = "signed";
  try {
    const form = await call("helpdesk.api.project_signoff.get_signoff_form", {
      project: props.projectId,
    });
    contacts.value = form.contacts;
  } catch {
    // only the signatory can be picked then; that is the usual case anyway
  }
}

function markSignedOff() {
  run(
    "signed",
    "mark_signed_off",
    {
      acceptance_reference: signedOff.reply || null,
      signed_on: signedOff.date,
      signed_off_by: signedOff.contact || null,
      signed_copy: signedOff.reply ? null : signedOff.copy || null,
    },
    __("Marked signed off; the signed PDF is on the project")
  );
}

// ---------- clarify, delete ----------

function startClarify(item: SignoffItem) {
  clarifyNote.value = "";
  clarifying.value = item;
}

function clarify() {
  if (!clarifying.value) return;
  run(
    "clarify",
    "mark_item_clarified",
    { item: clarifying.value.name, note: clarifyNote.value },
    uat.value
      ? __("Marked fixed; the customer has been asked to test it again")
      : __("Marked clarified; the customer has been emailed")
  );
}

async function remove() {
  busy.value = "delete";
  try {
    await call("helpdesk.api.project_signoff.delete_signoff", {
      signoff: props.signoffId,
    });
    toast.success(__("Draft deleted"));
    router.replace({
      name: "TaskySignoffs",
      params: { projectId: props.projectId },
    });
  } catch (e) {
    toast.error(errorText(e, __("Couldn't delete the draft.")));
  } finally {
    busy.value = null;
    confirming.value = null;
  }
}
</script>

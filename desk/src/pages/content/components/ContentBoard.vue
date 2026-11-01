<template>
  <DefineTodayMarker>
    <p
      id="day-today"
      class="flex scroll-mt-2 flex-wrap items-center gap-x-2 gap-y-0.5 rounded-xl border border-dashed border-outline-gray-3 px-3 py-2 text-sm text-ink-gray-7"
    >
      <!-- the same orange ring that marks today on the date pages -->
      <span
        class="size-2.5 shrink-0 rounded-full ring-2 ring-highlight"
        aria-hidden="true"
      />
      <span
        ><span class="font-medium text-ink-gray-9">{{ __("Today") }}:</span>
        {{
          filter === "upcoming"
            ? __("nothing else coming up")
            : __("nothing scheduled")
        }}</span
      >
      <span aria-hidden="true">·</span>
      <span>{{
        plan.next
          ? __("Next: {0}", dayjs(plan.next).format("ddd D MMM"))
          : period === "week"
          ? __("Nothing else this week")
          : __("Nothing else this month")
      }}</span>
    </p>
  </DefineTodayMarker>

  <div class="flex flex-col gap-3">
    <section
      class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
      :aria-label="__('Summary')"
    >
      <div
        v-for="tile in tiles"
        :key="tile.key"
        class="flex items-center gap-3 rounded-xl border px-4 py-3"
        :class="
          tile.warn
            ? 'stat-warning bg-warning-soft'
            : 'border-outline-gray-2 bg-surface-base'
        "
      >
        <div class="min-w-0 flex-1">
          <p
            class="text-sm"
            :class="tile.warn ? 'text-warning' : 'text-ink-gray-7'"
          >
            {{ tile.label }}
          </p>
          <p
            class="truncate font-mono text-[20px] font-semibold tabular-nums leading-snug"
            :class="tile.warn ? 'text-warning' : 'text-ink-gray-9'"
          >
            {{ tile.value }}
          </p>
          <p
            class="truncate text-xs"
            :class="tile.warn ? 'text-warning' : 'text-ink-gray-6'"
            :title="tile.sub"
          >
            {{ tile.sub }}
          </p>
        </div>
        <!-- how much of the period is published, as a ring -->
        <svg
          v-if="tile.ring !== undefined"
          viewBox="0 0 38 38"
          class="size-8 shrink-0 -rotate-90"
          aria-hidden="true"
        >
          <circle
            cx="19"
            cy="19"
            r="15"
            fill="none"
            stroke-width="4"
            style="stroke: var(--outline-gray-2)"
          />
          <circle
            v-if="tile.ring > 0"
            cx="19"
            cy="19"
            r="15"
            fill="none"
            stroke-width="4"
            stroke-linecap="round"
            style="stroke: var(--brand)"
            :stroke-dasharray="`${(tile.ring / 100) * RING} ${RING}`"
          />
          <!-- at 0% a dot marks where progress starts -->
          <circle v-else cx="34" cy="19" r="2.5" style="fill: var(--brand)" />
        </svg>
        <span
          v-else
          class="grid size-8 shrink-0 place-items-center rounded-[10px]"
          :class="tile.iconClass"
        >
          <component :is="tile.icon" class="size-4" aria-hidden="true" />
        </span>
      </div>
    </section>

    <div v-if="active.length" class="flex flex-col gap-1.5">
      <!-- a segment per post while they fit; past that, one block per bucket -->
      <div
        v-if="segments.length <= MAX_SEGMENTS"
        class="flex h-1 gap-1"
        role="img"
        :aria-label="barLabel"
      >
        <div
          v-for="(swatch, i) in segments"
          :key="i"
          class="flex-1 rounded-full"
          :class="swatch"
        />
      </div>
      <div
        v-else
        class="flex h-1 gap-0.5 overflow-hidden rounded-full bg-surface-gray-2"
        role="img"
        :aria-label="barLabel"
      >
        <div
          v-for="b in buckets"
          :key="b.key"
          :class="b.swatch"
          :style="{ flex: b.count }"
        />
      </div>
      <div
        class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-gray-7"
        aria-hidden="true"
      >
        <span
          v-for="b in buckets"
          :key="b.key"
          class="flex items-center gap-1.5"
        >
          <span class="size-1.5 rounded-full" :class="b.swatch" />
          <span class="font-mono font-semibold tabular-nums text-ink-gray-9">{{
            b.count
          }}</span>
          {{ b.label }}
        </span>
      </div>
    </div>

    <div
      v-if="missed.length"
      class="action-banner flex flex-wrap items-center gap-2.5 rounded-xl border bg-danger-soft px-3 py-2 text-sm text-danger"
      role="status"
    >
      <span
        class="grid size-6 shrink-0 place-items-center rounded-[6px] bg-surface-base"
      >
        <LucideCircleAlert class="size-3.5" aria-hidden="true" />
      </span>
      <span class="min-w-0 flex-1 basis-56">
        <b class="font-semibold">{{
          missed.length === 1
            ? __("1 post needs action.")
            : __("{0} posts need action.", String(missed.length))
        }}</b>
        {{
          missed.length === 1
            ? __("Not published on the planned date. Publish or postpone it.")
            : __("Not published on the planned date. Publish or postpone them.")
        }}
      </span>
      <button
        v-if="filter !== 'missed'"
        type="button"
        class="action-banner-btn inline-flex h-7 shrink-0 items-center rounded-[8px] border bg-surface-base px-3 text-sm font-medium text-danger transition-colors hover:bg-danger-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        @click="filter = 'missed'"
      >
        {{ missed.length === 1 ? __("Show it") : __("Show them") }}
      </button>
    </div>

    <!-- the next posts at a glance, so later days are never only below the fold -->
    <section
      v-if="comingUp.length && period !== 'day'"
      class="flex min-w-0 flex-col gap-1.5"
      :aria-labelledby="comingUpId"
    >
      <div class="flex items-center justify-between gap-2">
        <h2 :id="comingUpId" class="text-sm font-medium text-ink-gray-7">
          {{ __("Coming up") }}
        </h2>
        <button
          v-if="filter !== 'upcoming'"
          type="button"
          class="relative inline-flex h-8 items-center rounded-[8px] px-2 text-sm font-medium text-ink-gray-7 transition-colors after:absolute after:-inset-1.5 hover:bg-surface-gray-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          @click="filter = 'upcoming'"
        >
          {{ __("View all upcoming") }}
          <span class="ml-1 font-mono tabular-nums text-ink-gray-5">{{
            upcoming.length
          }}</span>
        </button>
      </div>
      <ul class="-mx-1 flex gap-2 overflow-x-auto px-1 py-1">
        <li v-for="p in comingUp" :key="p.name" class="shrink-0">
          <button
            type="button"
            class="flex min-h-[44px] w-[272px] flex-col gap-0.5 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-1.5 text-left transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            :aria-label="
              __(
                'Go to {0}: {1}, {2}, {3}',
                dayjs(p.publish_on).format('ddd D MMM, h:mm A'),
                p.customer,
                copyOf(p),
                __(p.status)
              )
            "
            @click="jumpTo(p)"
          >
            <span class="flex items-center gap-2" aria-hidden="true">
              <span
                class="whitespace-nowrap font-mono text-xs tabular-nums text-ink-gray-6"
                :class="dateOf(p) === today && 'font-semibold text-ink-gray-8'"
                >{{
                  dateOf(p) === today
                    ? __("Today")
                    : dayjs(p.publish_on).format("ddd D MMM")
                }}
                · {{ dayjs(p.publish_on).format("h:mm A") }}</span
              >
              <span class="ml-auto flex items-center gap-1">
                <ClientApprovalChip :status="p.status" />
                <StatusPill :post="p" />
              </span>
            </span>
            <span class="truncate text-sm" aria-hidden="true">
              <span class="font-semibold text-ink-gray-9">{{
                p.customer
              }}</span>
              <span class="text-ink-gray-7"> · {{ copyOf(p) }}</span>
            </span>
          </button>
        </li>
      </ul>
    </section>

    <div
      class="flex flex-wrap items-center gap-2"
      role="group"
      :aria-label="__('Filter entries')"
    >
      <button
        v-for="f in filterChips"
        :key="f.key"
        type="button"
        :aria-pressed="filter === f.key"
        class="inline-flex h-8 items-center gap-1.5 rounded-full border pl-3 pr-1 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        :class="
          filter === f.key
            ? 'border-brand bg-brand-soft text-brand-ink'
            : 'border-outline-gray-2 bg-surface-base text-ink-gray-8 hover:bg-surface-gray-2'
        "
        @click="filter = f.key"
      >
        {{ f.label }}
        <span
          class="grid h-5 min-w-[1.25rem] place-items-center rounded-full px-1.5 font-mono text-xs tabular-nums"
          :class="
            filter === f.key
              ? 'bg-brand text-brand-on'
              : f.key === 'missed'
              ? 'bg-danger-soft text-danger'
              : 'bg-surface-gray-2 text-ink-gray-7'
          "
          >{{ f.count }}</span
        >
      </button>
    </div>

    <div v-if="loading && !posts.length" class="flex flex-col gap-3">
      <div
        v-for="i in 3"
        :key="i"
        class="h-28 animate-pulse rounded-lg bg-surface-gray-2"
      />
    </div>

    <div
      v-else-if="!days.length"
      class="flex flex-col items-center gap-3 rounded-lg border border-dashed border-outline-gray-3 px-4 py-12 text-center"
    >
      <p class="text-p-sm text-ink-gray-5">
        {{
          posts.length
            ? __("No entries match this filter.")
            : day
            ? __("Nothing planned for {0}.", dayjs(day).format("ddd D MMM"))
            : PERIOD_TEXT[period || "month"].empty
        }}
      </p>
      <Button
        v-if="auth.canEditContent"
        :label="day ? __('Add entry for this day') : __('Add entry')"
        @click="emit('add', day || undefined)"
      >
        <template #prefix
          ><LucidePlus class="size-4" aria-hidden="true"
        /></template>
      </Button>
    </div>

    <!-- past days with nothing left to do fold away; missed ones stay listed -->
    <div
      v-if="plan.earlier.length"
      class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-1.5 text-sm"
    >
      <LucideHistory
        class="size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      <p class="min-w-0 flex-1 text-ink-gray-7">
        <span class="font-medium text-ink-gray-9">{{
          period === "week" ? __("Earlier this week") : __("Earlier this month")
        }}</span>
        ·
        <span class="font-mono tabular-nums">{{ earlierCount }}</span>
        {{ earlierCount === 1 ? __("entry") : __("entries") }}
        <span class="hidden sm:inline">
          · {{ __("published or cancelled") }}</span
        >
      </p>
      <button
        type="button"
        :class="[OUTLINE_BTN, 'relative after:absolute after:-inset-1.5']"
        :aria-expanded="showEarlier"
        @click="showEarlier = !showEarlier"
      >
        {{ showEarlier ? __("Hide") : __("Show") }}
      </button>
    </div>

    <template v-for="day in listedDays" :key="day.date">
      <TodayMarker v-if="plan.todayMarker && day.date === plan.next" />
      <section
        :id="`day-${day.date}`"
        class="flex scroll-mt-2 flex-col gap-2 sm:flex-row sm:gap-4"
        :aria-label="dayjs(day.date).format('dddd D MMMM')"
      >
        <div
          class="flex shrink-0 flex-wrap items-center gap-2 sm:sticky sm:top-0 sm:w-[88px] sm:flex-col sm:flex-nowrap sm:items-stretch sm:self-start"
        >
          <!-- a calendar page: month band, date, weekday -->
          <div
            class="w-[64px] shrink-0 overflow-hidden rounded-[10px] border bg-surface-base pb-1 text-center shadow-sm"
            :class="
              day.date === today
                ? 'border-highlight ring-1 ring-highlight'
                : 'border-outline-gray-2'
            "
            aria-hidden="true"
          >
            <div
              class="grid h-6 place-items-center bg-brand text-[11px] font-bold uppercase tracking-[0.1em] text-brand-on"
            >
              {{ dayjs(day.date).format("MMM") }}
            </div>
            <div
              class="font-mono text-[22px] font-medium tabular-nums leading-tight text-ink-gray-9"
            >
              {{ dayjs(day.date).format("D") }}
            </div>
            <div
              class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6"
            >
              {{ dayjs(day.date).format("ddd") }}
            </div>
          </div>
          <div class="flex flex-col gap-1.5 sm:items-start">
            <span class="text-[13px] text-ink-gray-6">
              <template v-if="day.date === today"
                ><span class="font-medium text-ink-gray-8 sm:block">{{
                  __("Today")
                }}</span
                ><span class="sm:hidden"> · </span></template
              >
              {{
                day.total === 1
                  ? __("1 entry")
                  : __("{0} entries", String(day.total))
              }}
            </span>
            <SpecialDayBadge
              v-for="name in day.specialDays"
              :key="name"
              :name="name"
            />
          </div>
        </div>

        <div class="flex min-w-0 flex-1 flex-col gap-3">
          <!-- a Coming up chip outlines its entry inside the card's edge, where the
             list's scroll box can't clip it -->
          <article
            v-for="post in day.posts"
            :key="post.name"
            :id="`post-${post.name}`"
            class="entry scroll-mt-4 overflow-hidden rounded-[16px] border"
            :class="[
              `entry-${entryTone(post)}`,
              flashed === post.name &&
                'outline outline-2 -outline-offset-2 outline-brand',
            ]"
            :aria-labelledby="`client-${post.name} entry-${post.name}`"
          >
            <header
              class="flex flex-wrap items-start gap-x-3 gap-y-2 px-4 pt-3"
            >
              <div class="flex min-w-0 flex-1 basis-72 gap-3">
                <span
                  class="grid size-10 shrink-0 place-items-center rounded-[10px] border border-outline-gray-2 bg-surface-base text-ink-gray-7 shadow-sm"
                  aria-hidden="true"
                >
                  <LucideBuilding2 class="size-[18px]" />
                </span>
                <div class="min-w-0 flex-1">
                  <!-- the client leads, shown even when filtered, so every card says whose it is -->
                  <p
                    v-if="post.customer"
                    :id="`client-${post.name}`"
                    class="truncate text-lg font-semibold text-ink-gray-9"
                    :title="post.customer"
                  >
                    {{ post.customer }}
                  </p>
                  <p
                    class="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1"
                  >
                    <!-- named like the Sub copy box below, so the copy reads as the post's copy -->
                    <span
                      class="shrink-0 text-sm text-ink-gray-5"
                      aria-hidden="true"
                      >{{ __("Copy") }}:</span
                    >
                    <button
                      :id="`entry-${post.name}`"
                      type="button"
                      :aria-label="__('Copy: {0}', copyOf(post))"
                      class="min-w-0 max-w-full truncate rounded text-left text-base font-medium text-ink-gray-8 hover:text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      :class="!post.title && 'italic text-ink-gray-6'"
                      :title="copyOf(post)"
                      @click="emit('open', post.name)"
                    >
                      {{ post.title || __("No copy yet") }}
                    </button>
                    <!-- the post type stands out: a tinted tag with the same icon as the
                         dialogs' post type chips (owner's request, 2026-10-14) -->
                    <span
                      v-if="post.format"
                      class="inline-flex h-7 shrink-0 items-center gap-1.5 self-center rounded-full bg-brand-soft px-2.5 text-sm font-semibold text-brand-ink"
                    >
                      <PostTypeIcon :post-type="post.format" class="size-4" />
                      {{ post.format }}
                    </span>
                  </p>
                  <SpecialDayBadge
                    v-if="post.special_day"
                    :name="post.special_day"
                    class="mt-1.5"
                  />
                  <p
                    v-if="needsApprovalSoon(post, now)"
                    class="mt-1.5 inline-flex items-center gap-1.5 rounded-md bg-danger-soft px-2 py-0.5 text-sm text-danger"
                  >
                    <LucideTriangleAlert
                      class="size-3.5 shrink-0"
                      aria-hidden="true"
                    />
                    {{ __("Goes live within 2 days and isn't approved yet.") }}
                  </p>
                </div>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <ul
                  class="flex flex-wrap items-center gap-2"
                  :aria-label="__('Platforms')"
                >
                  <li
                    v-for="p in platformsOf(post)"
                    :key="p"
                    class="inline-flex h-7 items-center gap-1.5 rounded-full border border-outline-gray-2 bg-surface-base px-2.5 text-sm text-ink-gray-8"
                  >
                    <ChannelIcon :channel="p" class="size-[15px] shrink-0" />{{
                      __(p)
                    }}
                  </li>
                </ul>
                <span
                  class="inline-flex h-7 items-center gap-1.5 rounded-full border border-outline-gray-2 bg-surface-base px-2.5 font-mono text-sm tabular-nums text-ink-gray-8"
                >
                  <LucideClock
                    class="size-3.5 shrink-0 text-ink-gray-5"
                    aria-hidden="true"
                  /><span class="sr-only">{{ __("Time:") }}</span
                  ><time :datetime="post.publish_on">{{
                    dayjs(post.publish_on).format("h:mm A")
                  }}</time></span
                >
                <StatusPill :post="post" size="md" />
                <ClientApprovalChip :status="post.status" />
                <Tooltip
                  :text="
                    auth.canEditContent
                      ? __('Edit entry')
                      : __('Open to add files')
                  "
                >
                  <button
                    type="button"
                    class="grid size-7 place-items-center rounded-full border border-outline-gray-2 bg-surface-base text-ink-gray-7 transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    :aria-label="
                      auth.canEditContent
                        ? __('Edit {0}', copyOf(post))
                        : __('Open {0} to add files', copyOf(post))
                    "
                    @click="emit('open', post.name)"
                  >
                    <LucidePencil
                      v-if="auth.canEditContent"
                      class="size-3.5"
                      aria-hidden="true"
                    />
                    <LucidePaperclip
                      v-else
                      class="size-3.5"
                      aria-hidden="true"
                    />
                  </button>
                </Tooltip>
              </div>
            </header>

            <div
              class="grid grid-cols-1 gap-2 px-4 pt-2.5 md:grid-cols-[1.65fr_1fr]"
            >
              <div
                class="min-w-0 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-2"
              >
                <p class="text-[13px] text-ink-gray-6">{{ __("Sub copy") }}</p>
                <p
                  class="mt-0.5 line-clamp-2 whitespace-pre-line text-sm leading-snug"
                  :class="
                    captionOf(post)
                      ? 'text-ink-gray-9'
                      : 'italic text-ink-gray-5'
                  "
                >
                  {{ captionOf(post) || __("Not written yet") }}
                </p>
              </div>
              <div
                class="min-w-0 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-2"
              >
                <p class="text-[13px] text-ink-gray-6">
                  {{ __("Description") }}
                </p>
                <p
                  class="mt-0.5 line-clamp-2 whitespace-pre-line text-sm leading-snug"
                  :class="
                    post.brief ? 'text-ink-gray-9' : 'italic text-ink-gray-5'
                  "
                >
                  {{ post.brief || __("No description yet") }}
                </p>
              </div>
            </div>

            <!-- a published post's work is done: who did it stays, but read-only -->
            <div
              class="grid grid-cols-1 gap-2 px-4 pt-2 min-[420px]:grid-cols-2 lg:grid-cols-4"
            >
              <RoleBox
                v-for="role in TEAM_ROLES"
                :key="role.field"
                :label="role.label"
                :role="role.field"
                :people="peopleOf(post, role.field)"
                :can-edit="auth.canEditContent"
                :readonly="post.status === 'Published'"
                :context="`${post.customer} · ${copyOf(post)}`"
                :step="boxStep(roleTask(post, role.field))"
                :busy="
                  !!stepBusy && stepBusy === roleTaskName(post, role.field)
                "
                @assign="emit('action', post, 'assign', role.field)"
                @open-task="showTask(post, role.field, $event)"
                @step="runStep($event, roleTask(post, role.field)!)"
              />
            </div>

            <!-- how far the post's parts are and who it waits on, from its role tasks -->
            <p
              v-if="post.status !== 'Published' && progressLines[post.name]"
              class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 px-4 pt-2 text-sm text-ink-gray-7"
            >
              <LucideListChecks
                class="size-4 shrink-0 text-ink-gray-5"
                aria-hidden="true"
              />
              <span>{{ progressLines[post.name].parts }}</span>
              <template v-if="progressLines[post.name].waiting">
                <span aria-hidden="true">·</span>
                <span
                  >{{ progressLines[post.name].waiting
                  }}<template v-if="progressLines[post.name].due"
                    >,</template
                  ></span
                >
                <span
                  v-if="progressLines[post.name].due"
                  class="inline-flex items-center gap-1"
                  :class="
                    progressLines[post.name].late && 'font-medium text-danger'
                  "
                >
                  <LucideCircleAlert
                    v-if="progressLines[post.name].late"
                    class="size-3.5"
                    aria-hidden="true"
                  />{{ progressLines[post.name].due }}</span
                >
              </template>
            </p>

            <footer
              class="entry-footer mt-3 flex flex-wrap items-center gap-2 border-t px-4 py-2"
            >
              <p
                class="flex flex-1 basis-48 items-center gap-2 text-base"
                :class="isMissed(post, now) ? 'text-danger' : 'text-ink-gray-7'"
              >
                <component
                  :is="statusIcon(post)"
                  class="size-[15px] shrink-0"
                  aria-hidden="true"
                />
                {{ statusLine(post) }}
              </p>
              <!-- scheduled to go out on Facebook / Instagram by the hub itself -->
              <TaskyBadge
                v-if="post.meta_publish_on && post.status === 'Scheduled'"
                tone="info"
                :icon="LucideClock"
                :label="
                  __(
                    'Auto-publish {0}',
                    dayjs(post.meta_publish_on).format('ddd D MMM, h:mm A')
                  )
                "
              />
              <template v-if="!CLOSED_STATUSES.includes(post.status)">
                <!-- waiting on the head: only they move it on, so no Mark published -->
                <template v-if="post.status === HEAD_REVIEW">
                  <template v-if="auth.isDmHead">
                    <button
                      type="button"
                      :class="PRIMARY_BTN"
                      @click="emit('action', post, 'head_approve')"
                    >
                      <LucideCheck class="size-4" aria-hidden="true" />
                      {{ __("Approve") }}
                    </button>
                    <button
                      type="button"
                      :class="OUTLINE_BTN"
                      @click="emit('action', post, 'head_send_back')"
                    >
                      <LucideUndo2
                        class="size-4 text-ink-gray-6"
                        aria-hidden="true"
                      />
                      {{ __("Send back") }}
                    </button>
                  </template>
                </template>
                <!-- a post with the client can't be published until they and the head approve -->
                <button
                  v-else-if="
                    post.status !== 'Client Review' && auth.canEditContent
                  "
                  type="button"
                  :class="PRIMARY_BTN"
                  @click="emit('action', post, 'publish')"
                >
                  <LucideSend class="size-4" aria-hidden="true" />
                  {{ __("Mark published") }}
                </button>
                <button
                  v-if="
                    ['Approved', 'Scheduled'].includes(post.status) &&
                    (auth.canEditContent || auth.isDmHead)
                  "
                  type="button"
                  :class="OUTLINE_BTN"
                  @click="emit('action', post, 'meta')"
                >
                  <LucideShare2
                    class="size-4 text-ink-gray-6"
                    aria-hidden="true"
                  />
                  {{ __("Publish to Meta") }}
                </button>
                <button
                  v-if="auth.canEditContent"
                  type="button"
                  :class="OUTLINE_BTN"
                  @click="emit('action', post, 'postpone')"
                >
                  <LucideCalendarClock
                    class="size-4 text-ink-gray-6"
                    aria-hidden="true"
                  />
                  {{ __("Postpone") }}
                </button>
                <Tooltip v-if="auth.canEditContent" :text="__('Cancel post')">
                  <button
                    type="button"
                    class="grid size-8 place-items-center rounded-full border border-outline-gray-2 bg-surface-base text-ink-gray-6 transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    :aria-label="__('Cancel post')"
                    @click="emit('action', post, 'cancel')"
                  >
                    <LucideBan class="size-4" aria-hidden="true" />
                  </button>
                </Tooltip>
              </template>
              <a
                v-else-if="post.status === 'Published' && post.published_url"
                :href="post.published_url"
                target="_blank"
                rel="noopener"
                class="inline-flex items-center gap-1 rounded text-sm text-success hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              >
                <LucideExternalLink class="size-3.5" aria-hidden="true" />{{
                  __("View post")
                }}
              </a>
            </footer>
          </article>

          <div v-if="auth.canEditContent">
            <Button
              size="sm"
              variant="ghost"
              :label="__('Add entry for this day')"
              @click="emit('add', day.date)"
            >
              <template #prefix
                ><LucidePlus class="size-3.5" aria-hidden="true"
              /></template>
            </Button>
          </div>
        </div>
      </section>
    </template>
    <TodayMarker v-if="plan.todayMarker && !plan.next" />

    <TaskDetailDialog
      v-model:task="dialogTask"
      :action="dialogAction"
      :mine="dialogMine"
      @changed="emit('changed')"
    />
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { useToday } from "@/composables/today";
import { __ } from "@/translation";
import TaskDetailDialog from "@/pages/tasky/components/TaskDetailDialog.vue";
import { createReusableTemplate } from "@vueuse/core";
import { Button, createResource, dayjs, Tooltip } from "frappe-ui";
import {
  type Component,
  computed,
  markRaw,
  nextTick,
  onBeforeUnmount,
  ref,
  useId,
  watch,
} from "vue";
import LucideBan from "~icons/lucide/ban";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClock from "~icons/lucide/clock";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideHistory from "~icons/lucide/history";
import LucideListChecks from "~icons/lucide/list-checks";
import LucidePlus from "~icons/lucide/plus";
import LucideSend from "~icons/lucide/send";
import LucideShare2 from "~icons/lucide/share-2";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucidePencil from "~icons/lucide/pencil";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import { useAuthStore } from "@/stores/auth";
import LucideCheck from "~icons/lucide/check";
import LucideUndo2 from "~icons/lucide/undo-2";
import {
  CLOSED_STATUSES,
  type ContentPost,
  HEAD_REVIEW,
  type EntryAction,
  htmlToText,
  isMissed,
  needsApprovalSoon,
  platformsOf,
  type RolePerson,
  TEAM_ROLES,
  type TeamRole,
  copyOf,
} from "../constants";
import {
  boxStep,
  type ContentTask,
  type ContentTasksData,
  dueText,
  partsText,
  useContentTaskSteps,
  waitingText,
} from "../contentTasks";
import { planDays, prefersMotion, revealIfLow } from "../dayFocus";
import ChannelIcon from "./ChannelIcon.vue";
import PostTypeIcon from "./PostTypeIcon.vue";
import RoleBox from "./RoleBox.vue";
import SpecialDayBadge from "./SpecialDayBadge.vue";
import ClientApprovalChip from "./ClientApprovalChip.vue";
import StatusPill from "./StatusPill.vue";

const auth = useAuthStore();

const PERIOD_TEXT = {
  day: {
    progress: __("Day progress"),
    sub: __("this day"),
    empty: __("Nothing planned for this day."),
  },
  week: {
    progress: __("Week progress"),
    sub: __("this week"),
    empty: __("Nothing planned for this week."),
  },
  month: {
    progress: __("Month progress"),
    sub: __("this month"),
    empty: __("Nothing planned for this month yet."),
  },
};

const PRIMARY_BTN =
  "inline-flex h-8 items-center gap-1.5 rounded-[10px] bg-brand px-3 text-sm font-semibold text-brand-on shadow-sm transition-colors hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2";
const OUTLINE_BTN =
  "inline-flex h-8 items-center gap-1.5 rounded-[10px] border border-outline-gray-2 bg-surface-base px-3 text-sm font-medium text-ink-gray-8 transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4";

// circumference of the progress ring (r = 15)
const RING = 2 * Math.PI * 15;

// past this many posts the bar's segments get too thin to read
const MAX_SEGMENTS = 40;

const props = defineProps<{
  posts: ContentPost[];
  month: string;
  period?: "day" | "week" | "month";
  // set in Day view, so an empty day offers to add an entry on it
  day?: string;
  loading?: boolean;
  filtersCustomer?: string;
  /** The period's role tasks: each card's parts line and the viewer's step in a role box. */
  taskData?: ContentTasksData | null;
}>();
const emit = defineEmits<{
  (e: "open", name: string): void;
  (e: "add", date?: string): void;
  (e: "action", post: ContentPost, action: EntryAction, role?: TeamRole): void;
  /** A task opened from a role box changed: reload the posts. */
  (e: "changed"): void;
}>();

const [DefineTodayMarker, TodayMarker] = createReusableTemplate();
const comingUpId = useId();

// everyone on each post's roles, with their task's status; reloaded with the posts
const team = createResource({
  url: "helpdesk.api.content_board.get_team_task_status",
  makeParams: () => ({ posts: props.posts.map((p) => p.name) }),
});
watch(
  () => props.posts,
  () => props.posts.length && team.reload(),
  { immediate: true }
);

/** Everyone on a role, the main person first; just the main person until the team loads. */
function peopleOf(post: ContentPost, role: TeamRole): RolePerson[] {
  const people = team.data?.[post.name]?.[role];
  if (people) return people;
  return post[role] ? [{ user: post[role]!, full_name: post[role]! }] : [];
}

type FilterKey = "all" | "missed" | "upcoming" | "published" | "cancelled";
const filter = ref<FilterKey>("all");
const showEarlier = ref(false);
watch(
  () => props.month,
  () => {
    filter.value = "all";
    showEarlier.value = false;
  }
);

const today = useToday();
// re-read the clock whenever posts reload, so a post that just passed its time shows as missed
const now = computed(() => {
  void props.posts;
  return new Date();
});

const active = computed(() =>
  props.posts.filter((p) => p.status !== "Cancelled")
);
const published = computed(() =>
  props.posts.filter((p) => p.status === "Published")
);
// same rule as the delivery report: late when it went out after its planned day
const late = computed(() =>
  published.value.filter(
    (p) =>
      p.published_on &&
      dayjs(p.published_on).format("YYYY-MM-DD") >
        dayjs(p.publish_on).format("YYYY-MM-DD")
  )
);
const missed = computed(() =>
  props.posts.filter((p) => isMissed(p, now.value))
);
const upcoming = computed(() =>
  props.posts.filter(
    (p) => !CLOSED_STATUSES.includes(p.status) && !isMissed(p, now.value)
  )
);
const cancelled = computed(() =>
  props.posts.filter((p) => p.status === "Cancelled")
);

const MATCHERS: Record<FilterKey, (p: ContentPost) => boolean> = {
  all: () => true,
  missed: (p) => isMissed(p, now.value),
  upcoming: (p) =>
    !CLOSED_STATUSES.includes(p.status) && !isMissed(p, now.value),
  published: (p) => p.status === "Published",
  cancelled: (p) => p.status === "Cancelled",
};

const filterChips = computed(() =>
  (
    [
      { key: "all", label: __("All"), count: props.posts.length },
      { key: "missed", label: __("Missed"), count: missed.value.length },
      { key: "upcoming", label: __("Upcoming"), count: upcoming.value.length },
      {
        key: "published",
        label: __("Published"),
        count: published.value.length,
      },
      {
        key: "cancelled",
        label: __("Cancelled"),
        count: cancelled.value.length,
      },
    ] as { key: FilterKey; label: string; count: number }[]
  ).filter((c) => c.key === "all" || c.key === filter.value || c.count)
);

const buckets = computed(() =>
  [
    {
      key: "on-time",
      label: __("Published on time"),
      count: published.value.length - late.value.length,
      swatch: "bg-success",
    },
    {
      key: "late",
      label: __("Published late"),
      count: late.value.length,
      swatch: "bg-warning",
    },
    {
      key: "missed",
      label: __("Missed"),
      count: missed.value.length,
      swatch: "bg-danger",
    },
    {
      key: "upcoming",
      label: __("Upcoming"),
      count: upcoming.value.length,
      swatch: "bg-info",
    },
  ].filter((b) => b.count)
);
// one swatch per post, in the buckets' order
const segments = computed(() =>
  buckets.value.flatMap((b) => Array<string>(b.count).fill(b.swatch))
);
const barLabel = computed(() =>
  buckets.value.map((b) => `${b.count} ${b.label}`).join(", ")
);

interface Tile {
  key: string;
  label: string;
  value: string;
  sub: string;
  // Postponed above 0 tints the whole tile
  warn?: boolean;
  iconClass?: string;
  icon?: Component;
  ring?: number;
}

const tiles = computed<Tile[]>(() => {
  const publishedCount = published.value.length;
  const onTime = publishedCount - late.value.length;
  const onTimePct = publishedCount
    ? Math.round((onTime / publishedCount) * 100)
    : null;
  const postponedPosts = props.posts.filter(
    (p) => (p.times_postponed || 0) > 0
  );
  const postponements = postponedPosts.reduce(
    (n, p) => n + (p.times_postponed || 0),
    0
  );
  const next = upcoming.value
    .filter((p) => dayjs(p.publish_on).isAfter(dayjs()))
    .sort((a, b) => (a.publish_on! < b.publish_on! ? -1 : 1))[0];
  const planned = active.value.length;
  const progress = planned ? Math.round((publishedCount / planned) * 100) : 0;
  const periodSub = PERIOD_TEXT[props.period || "month"].sub;
  return [
    {
      key: "progress",
      label: PERIOD_TEXT[props.period || "month"].progress,
      value: planned ? `${progress}%` : "—",
      sub: __("{0} of {1} published", String(publishedCount), String(planned)),
      ring: progress,
    },
    {
      key: "on-time",
      label: __("On-time rate"),
      value: onTimePct == null ? "—" : `${onTimePct}%`,
      sub: __(
        "{0} of {1} on the planned day",
        String(onTime),
        String(publishedCount)
      ),
      iconClass: "bg-info-soft text-info",
      icon: markRaw(LucideClock),
    },
    {
      key: "postponed",
      label: __("Postponed"),
      value: String(postponedPosts.length),
      sub:
        postponements > postponedPosts.length
          ? `${periodSub} · ${__("{0} moves", String(postponements))}`
          : periodSub,
      warn: postponedPosts.length > 0,
      iconClass: postponedPosts.length
        ? "bg-surface-base text-warning"
        : "bg-surface-gray-2 text-ink-gray-6",
      icon: markRaw(LucideCalendarClock),
    },
    {
      key: "next",
      label: __("Next post"),
      value: next ? dayjs(next.publish_on).format("ddd D MMM") : "—",
      sub: next
        ? `${dayjs(next.publish_on).format("h:mm A")} · ${copyOf(
            next
          )} · ${platformsOf(next).join(", ")}`
        : __("Nothing scheduled"),
      iconClass: "bg-brand-soft text-brand",
      icon: markRaw(LucideSend),
    },
  ];
});

/** The card's tint: what needs chasing first, then how it went. */
function entryTone(post: ContentPost) {
  if (isMissed(post, now.value) || needsApprovalSoon(post, now.value))
    return "danger";
  if (post.status === "Published") return "success";
  if (post.status === "Cancelled") return "neutral";
  return "info";
}

const dateOf = (post: ContentPost) =>
  dayjs(post.publish_on).format("YYYY-MM-DD");

const days = computed(() => {
  const byDay = new Map<
    string,
    { date: string; total: number; posts: ContentPost[] }
  >();
  for (const post of props.posts) {
    if (!post.publish_on) continue;
    const date = dayjs(post.publish_on).format("YYYY-MM-DD");
    if (!byDay.has(date)) byDay.set(date, { date, total: 0, posts: [] });
    const day = byDay.get(date)!;
    day.total++;
    if (MATCHERS[filter.value](post)) day.posts.push(post);
  }
  return [...byDay.values()]
    .filter((d) => d.posts.length)
    .sort((a, b) => (a.date < b.date ? -1 : 1))
    .map((d) => ({
      ...d,
      posts: d.posts.sort((a, b) => (a.publish_on! < b.publish_on! ? -1 : 1)),
      needsAction: d.posts.some((p) => isMissed(p, now.value)),
      // each special day once, so the day heading names them
      specialDays: [
        ...new Set(d.posts.map((p) => p.special_day).filter(Boolean)),
      ] as string[],
    }));
});

// the period on screen is "<period>:<first day>" (the month prop)
const todayInPeriod = computed(() => {
  const start = dayjs(props.month.split(":")[1]);
  return (
    today.value >= start.format("YYYY-MM-DD") &&
    today.value <= start.endOf(props.period || "month").format("YYYY-MM-DD")
  );
});
// Day view is a single day, so it neither folds nor marks anything
const plan = computed(() =>
  planDays(days.value, today.value, {
    collapsePast: filter.value === "all" && props.period !== "day",
    markToday:
      props.period !== "day" &&
      todayInPeriod.value &&
      (filter.value === "all" || filter.value === "upcoming"),
  })
);
const listedDays = computed(() =>
  showEarlier.value ? days.value : plan.value.shown
);
const earlierCount = computed(() =>
  plan.value.earlier.reduce((n, d) => n + d.total, 0)
);

// open on today (or the marker, or the next day) once per period, not after every reload
let openedOn = "";
watch(
  () => [props.month, props.loading, plan.value.target] as const,
  async ([month, loading, target]) => {
    if (loading || !target || openedOn === month) return;
    openedOn = month;
    await nextTick();
    revealIfLow(document.getElementById(`day-${target}`));
  },
  { immediate: true }
);

const comingUp = computed(() =>
  [...upcoming.value]
    .sort((a, b) => (a.publish_on! < b.publish_on! ? -1 : 1))
    .slice(0, 7)
);

// a Coming up chip scrolls to its entry and outlines it for a moment
const flashed = ref("");
let flashTimer: ReturnType<typeof setTimeout> | undefined;
async function jumpTo(post: ContentPost) {
  if (!MATCHERS[filter.value](post)) filter.value = "all";
  await nextTick();
  document.getElementById(`post-${post.name}`)?.scrollIntoView({
    block: "center",
    behavior: prefersMotion() ? "smooth" : "auto",
  });
  document.getElementById(`entry-${post.name}`)?.focus({ preventScroll: true });
  flashed.value = post.name;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => (flashed.value = ""), 2000);
}
onBeforeUnmount(() => clearTimeout(flashTimer));

// a role's task opens here; the assignee gets their own steps (complete, hold, ...)
const {
  busy: stepBusy,
  dialogTask,
  dialogAction,
  dialogMine,
  open: openTaskDialog,
  run: runStep,
} = useContentTaskSteps(() => emit("changed"));
function showTask(post: ContentPost, role: TeamRole, task: string) {
  openTaskDialog(
    { name: task },
    peopleOf(post, role).some((p) => p.user === auth.userId)
  );
}

// the role's task as the Tasks view has it: there only when the viewer may read it
const tasksByName = computed(
  () =>
    new Map<string, ContentTask>(
      (props.taskData?.tasks ?? []).map((t) => [t.name, t])
    )
);
function roleTaskName(post: ContentPost, role: TeamRole) {
  return peopleOf(post, role).find((p) => p.task)?.task;
}
function roleTask(post: ContentPost, role: TeamRole) {
  const name = roleTaskName(post, role);
  return name ? tasksByName.value.get(name) : undefined;
}

/** "3 of 4 parts done · waiting on Writer (Ajmal) · due tomorrow", for posts still open. */
const progressLines = computed(() => {
  const lines: Record<
    string,
    { parts: string; waiting: string; due: string; late: boolean }
  > = {};
  for (const [name, post] of Object.entries(props.taskData?.posts ?? {})) {
    const progress = post.progress;
    if (!progress.parts || CLOSED_STATUSES.includes(post.status)) continue;
    const waiting = progress.waiting_on;
    const due =
      waiting?.kind === "part"
        ? dueText(waiting.due)
        : { text: "", late: false };
    lines[name] = {
      parts: partsText(progress),
      waiting: waiting ? waitingText(waiting) : "",
      due: due.text,
      late: due.late,
    };
  }
  return lines;
});

function captionOf(post: ContentPost) {
  return htmlToText(post.caption);
}

function statusIcon(post: ContentPost): Component {
  if (post.status === "Published") return LucideSend;
  if (post.status === "Cancelled") return LucideBan;
  if (isMissed(post, now.value)) return LucideCircleAlert;
  return LucideClock;
}

function statusLine(post: ContentPost) {
  const when = dayjs(post.publish_on).format("ddd D MMM, h:mm A");
  if (post.status === "Published") {
    return post.published_on
      ? __("Published {0}", dayjs(post.published_on).format("D MMM, h:mm A"))
      : __("Published");
  }
  if (post.status === "Cancelled") return __("Cancelled");
  if (isMissed(post, now.value)) return __("Not published. Was due {0}.", when);
  if (post.status === HEAD_REVIEW)
    return __(
      "Client approved · waiting for the Digital Marketing Head. Goes live {0}.",
      when
    );
  const postponed = post.times_postponed
    ? " · " +
      (post.times_postponed === 1
        ? __("postponed once")
        : __("postponed {0} times", String(post.times_postponed)))
    : "";
  return __("Goes live {0}", when) + postponed;
}
</script>

<style scoped>
/* Cards take a light wash of their tone; the footer and border carry it a step stronger. */
.entry {
  --tone: var(--outline-gray-3);
  --tone-soft: var(--surface-gray-2);
  background-color: color-mix(
    in srgb,
    var(--tone-soft) 55%,
    var(--surface-base)
  );
  border-color: color-mix(in srgb, var(--tone) 30%, var(--outline-gray-2));
}
.entry-info {
  --tone: var(--info);
  --tone-soft: var(--info-soft);
}
.entry-danger {
  --tone: var(--danger);
  --tone-soft: var(--danger-soft);
}
.entry-success {
  --tone: var(--success);
  --tone-soft: var(--success-soft);
}
.entry-footer {
  background-color: var(--tone-soft);
  border-color: color-mix(in srgb, var(--tone) 20%, var(--outline-gray-2));
}
.stat-warning {
  border-color: color-mix(in srgb, var(--warning) 35%, var(--outline-gray-2));
}
.action-banner,
.action-banner-btn {
  border-color: color-mix(in srgb, var(--danger) 30%, var(--outline-gray-2));
}
</style>

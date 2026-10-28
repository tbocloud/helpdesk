// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// The Copilot button on the ticket page: start a run, see what it found, rate it, cancel it.
function setupForm({ doc, call, toast, $dialog }) {
  var actions = [];

  actions.push({
    label: "Copilot",
    theme: "blue",
    variant: "subtle",
    onClick: async function () {
      try {
        var info = await call("helpdesk.api.copilot.get_run", {
          ticket: doc.name,
        });
        if (!info || !info.run) {
          showCopilotStartDialog(doc, call, toast, $dialog);
        } else {
          showCopilotRunDialog(info, doc, call, toast, $dialog);
        }
      } catch (error) {
        toast.error("Failed to load Copilot");
        console.error("Copilot error:", error);
      }
    },
  });

  return { actions: actions };
}

function copilotEscape(text) {
  return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[c];
  });
}

async function startCopilot(doc, call, toast, _ref) {
  try {
    await call("helpdesk.api.copilot.start_run", { ticket: doc.name });
    toast.success("Copilot run queued. A worker will pick it up.");
    _ref.close();
  } catch (error) {
    toast.error("Failed to start Copilot");
    console.error("Copilot start error:", error);
  }
}

function showCopilotStartDialog(doc, call, toast, $dialog) {
  $dialog({
    title: "Copilot - Ticket #" + doc.name,
    message:
      "Copilot has not looked at this ticket yet. Start a run? A worker investigates and reports back here; the customer sees the progress on their own ticket.",
    actions: [
      {
        label: "Start Copilot",
        variant: "solid",
        onClick: function (_ref) {
          startCopilot(doc, call, toast, _ref);
        },
      },
      {
        label: "Cancel",
        onClick: function (_ref) {
          _ref.close();
        },
      },
    ],
  });
}

function showCopilotRunDialog(info, doc, call, toast, $dialog) {
  var rows = [
    ["Run", info.run + " (" + info.kind + ")"],
    ["State", info.state],
    [
      "Customer sees",
      info.shadow ? "Nothing (shadow mode)" : info.stage || "-",
    ],
    ["Copilot level", info.level || "-"],
    [
      "Root cause",
      info.root_cause
        ? info.root_cause +
          " (" +
          Math.round((info.confidence || 0) * 100) +
          "% sure)"
        : "-",
    ],
    ["Worker", info.worker_id || "-"],
    ["Task", info.task || "-"],
    ["Handed over to", info.handed_over_to || "-"],
  ];
  if (info.base_commit) {
    rows.push([
      "Code read at",
      (info.base_app || "app") + " @ " + String(info.base_commit).slice(0, 12),
    ]);
  }
  if (info.model_used) {
    rows.push([
      "Model",
      info.model_used +
        " (" +
        (info.tokens_in || 0) +
        " tokens in, " +
        (info.tokens_out || 0) +
        " out)",
    ]);
  }
  var html =
    '<div style="padding:8px"><table style="width:100%;font-size:13px">';
  for (var i = 0; i < rows.length; i++) {
    html +=
      '<tr><td style="color:#6b7280;padding:2px 8px 2px 0;white-space:nowrap">' +
      copilotEscape(rows[i][0]) +
      "</td><td>" +
      copilotEscape(rows[i][1]) +
      "</td></tr>";
  }
  html += "</table>";
  if (info.suspicious && info.suspicious.length) {
    html +=
      '<div style="margin-top:8px;padding:6px 8px;border-radius:6px;background:#fef3c7;color:#92400e">' +
      "<b>Text that tries to instruct the AI</b>" +
      "<div>Copilot is told to ignore it. Read it before you send anything to the customer.</div><ul>";
    for (var s = 0; s < info.suspicious.length; s++) {
      html +=
        "<li>" +
        copilotEscape(info.suspicious[s].source) +
        ": " +
        copilotEscape(info.suspicious[s].text) +
        "</li>";
    }
    html += "</ul></div>";
  }
  if (info.summary) {
    html +=
      '<div style="margin-top:8px"><b>Diagnosis</b><div>' +
      copilotEscape(info.summary) +
      "</div></div>";
  }
  if (info.review && info.review.verdict) {
    html +=
      '<div style="margin-top:8px"><b>Team rating:</b> ' +
      copilotEscape(info.review.verdict) +
      (info.review.verdict !== "Right" && info.review.root_cause
        ? " (real cause: " + copilotEscape(info.review.root_cause) + ")"
        : "") +
      " by " +
      copilotEscape(info.review.by_name || info.review.by || "") +
      (info.review.at ? ", " + copilotEscape(info.review.at) : "") +
      (info.review.note
        ? '<div style="white-space:pre-line;color:#4b5563">' +
          copilotEscape(info.review.note) +
          "</div>"
        : "") +
      "</div>";
  }
  if (info.customer_message) {
    html +=
      '<div style="margin-top:8px"><b>Offered to the customer</b> (in the suggested reply)<div style="white-space:pre-line">' +
      copilotEscape(info.customer_message) +
      "</div></div>";
  }
  if (info.failure_reason) {
    html +=
      '<div style="margin-top:8px;color:#b91c1c"><b>Failed:</b> ' +
      copilotEscape(info.failure_reason) +
      "</div>";
  }
  if (info.evidence && info.evidence.length) {
    html +=
      '<div style="margin-top:8px"><b>Evidence</b><ul style="margin:4px 0 0 16px">';
    for (var j = 0; j < info.evidence.length; j++) {
      var e = info.evidence[j];
      html +=
        "<li>" +
        copilotEscape(e.type || "") +
        (e.ref ? " " + copilotEscape(e.ref) : "") +
        (e.note ? ": " + copilotEscape(e.note) : "") +
        "</li>";
    }
    html += "</ul></div>";
  }
  if (info.fix) {
    html += copilotFixSummary(info.fix);
  }
  if (info.build) {
    html += copilotBuildSummary(info.build);
  }
  if (info.known_issue) {
    html += copilotKnownIssueHtml(info.known_issue, info.raised_by_copilot);
  }
  if (info.events && info.events.length) {
    html +=
      '<div style="margin-top:8px"><b>Latest events</b><ul style="margin:4px 0 0 16px;color:#6b7280">';
    var shown = info.events.slice(0, 8);
    for (var k = 0; k < shown.length; k++) {
      var ev = shown[k];
      html +=
        "<li>" +
        copilotEscape(ev.creation) +
        " · " +
        copilotEscape(ev.event_type) +
        " · " +
        copilotEscape(ev.actor) +
        (ev.note ? " · " + copilotEscape(ev.note) : "") +
        "</li>";
    }
    html += "</ul></div>";
  }
  html += "</div>";

  var actions = [];
  if (info.can_review) {
    actions.push({
      label:
        info.review && info.review.verdict ? "Change rating" : "Rate diagnosis",
      variant: "subtle",
      onClick: function (_ref) {
        _ref.close();
        showCopilotReviewDialog(info, doc, call, toast, $dialog);
      },
    });
  }
  var fix = info.fix || {};
  if (fix.can_create_task) {
    actions.push({
      label: "Create fix task",
      variant: "subtle",
      onClick: async function (_ref) {
        try {
          await call("helpdesk.api.copilot.create_fix_task", {
            ticket: doc.name,
          });
          toast.success("Fix task created for the developer.");
          _ref.close();
        } catch (error) {
          toast.error(copilotError(error, "Failed to create the fix task"));
          console.error("Copilot fix task error:", error);
        }
      },
    });
  }
  if (fix.can_request_fix) {
    actions.push({
      label: "Let Copilot fix it",
      variant: "subtle",
      onClick: async function (_ref) {
        try {
          await call("helpdesk.api.copilot.request_copilot_fix", {
            ticket: doc.name,
          });
          toast.success(
            "Copilot will try to fix it on a sandbox copy of the site."
          );
          _ref.close();
        } catch (error) {
          toast.error(copilotError(error, "Failed to ask Copilot to fix it"));
        }
      },
    });
  }
  if (fix.approval && fix.approval.status === "Pending") {
    var correction = fix.change_set && fix.approval.change_set;
    actions.push({
      label: correction ? "Review correction" : "Review fix",
      variant: "solid",
      onClick: function (_ref) {
        _ref.close();
        if (correction) {
          showCopilotCorrectionReview(info, doc, call, toast, $dialog);
        } else {
          showCopilotFixReview(info, doc, call, toast, $dialog);
        }
      },
    });
  }
  if (fix.can_refresh) {
    actions.push({
      label: "Refresh fix",
      onClick: async function (_ref) {
        try {
          var result = await call("helpdesk.api.copilot.refresh_fix", {
            ticket: doc.name,
          });
          toast.success("GitHub: " + ((result && result.refresh) || "read"));
          _ref.close();
        } catch (error) {
          toast.error(copilotError(error, "Failed to read the pull request"));
        }
      },
    });
  }
  if (fix.can_deploy) {
    actions.push({
      label: "Deploy",
      variant: "solid",
      onClick: function (_ref) {
        _ref.close();
        showCopilotDeploy(fix, doc, call, toast, $dialog);
      },
    });
  }
  if (fix.deploy && fix.deploy.can_cancel) {
    actions.push({
      label: "Cancel deploy",
      onClick: async function (_ref) {
        try {
          await call("helpdesk.api.copilot.cancel_deploy", {
            ticket: doc.name,
          });
          toast.success("The deploy is cancelled.");
          _ref.close();
        } catch (error) {
          toast.error(copilotError(error, "Failed to cancel the deploy"));
        }
      },
    });
  }
  if (fix.can_undo_change) {
    actions.push({
      label: "Undo the change",
      theme: "red",
      onClick: function (_ref) {
        _ref.close();
        showCopilotUndoChange(doc, call, toast, $dialog);
      },
    });
  }
  if (fix.can_undo) {
    actions.push({
      label: "Undo the fix",
      theme: "red",
      onClick: function (_ref) {
        _ref.close();
        showCopilotUndo(doc, call, toast, $dialog);
      },
    });
  }
  if (fix.can_mark_deployed) {
    actions.push({
      label: "Mark deployed",
      variant: "solid",
      onClick: function (_ref) {
        _ref.close();
        showCopilotMarkDeployed(doc, call, toast, $dialog);
      },
    });
  }
  if (info.can_cancel) {
    actions.push({
      label: "Cancel run",
      onClick: async function (_ref) {
        try {
          await call("helpdesk.api.copilot.cancel_run", { ticket: doc.name });
          toast.success("Copilot run cancelled.");
          _ref.close();
        } catch (error) {
          toast.error("Failed to cancel the run");
        }
      },
    });
  }
  if (info.build && info.build.can_build) {
    actions.push({
      label: "Build with Copilot",
      variant: "solid",
      onClick: async function (_ref) {
        try {
          await call("helpdesk.api.copilot.build_customization", {
            ticket: doc.name,
          });
          toast.success(
            "Copilot will build the approved change on a sandbox copy, then open the pull request for the one approval."
          );
          _ref.close();
        } catch (error) {
          toast.error(copilotError(error, "Failed to start the build"));
        }
      },
    });
  }
  if (info.known_issue && info.known_issue.can_draft_kb) {
    actions.push({
      label: "Draft a KB article",
      onClick: async function (_ref) {
        try {
          var made = await call(
            "helpdesk.api.copilot.draft_known_issue_article",
            { ticket: doc.name }
          );
          toast.success(
            "Draft " + made.article + " is ready for review; nothing is published."
          );
          _ref.close();
        } catch (error) {
          toast.error(copilotError(error, "Failed to draft the article"));
        }
      },
    });
  }
  if (info.can_prepare_correction) {
    actions.push({
      label: "Let Copilot prepare the correction",
      onClick: async function (_ref) {
        try {
          await call("helpdesk.api.copilot.prepare_correction", {
            ticket: doc.name,
          });
          toast.success(
            "Copilot will prepare the correction; a senior approves it before anything changes."
          );
          _ref.close();
        } catch (error) {
          toast.error(copilotError(error, "Failed to ask Copilot"));
        }
      },
    });
  }
  if (info.can_start) {
    actions.push({
      label: "Start again",
      variant: "solid",
      onClick: function (_ref) {
        startCopilot(doc, call, toast, _ref);
      },
    });
  }
  actions.push({
    label: "Close",
    onClick: function (_ref) {
      _ref.close();
    },
  });

  $dialog({
    title: "Copilot - Ticket #" + doc.name,
    html: html,
    actions: actions,
  });
}

// Rating a diagnosis: Right, Partly or Wrong; Wrong needs the root cause the agent found.
function showCopilotReviewDialog(info, doc, call, toast, $dialog) {
  var review = info.review || {};
  var options = '<option value="">-</option>';
  for (var i = 0; i < (info.categories || []).length; i++) {
    var c = info.categories[i];
    options +=
      '<option value="' +
      copilotEscape(c) +
      '"' +
      (review.root_cause === c && review.verdict !== "Right"
        ? " selected"
        : "") +
      ">" +
      copilotEscape(c) +
      "</option>";
  }
  var field =
    "width:100%;padding:6px;border:1px solid #d1d5db;border-radius:4px;font-size:13px";
  var html =
    '<div style="padding:8px;font-size:13px">' +
    "<div>Copilot said <b>" +
    copilotEscape(info.root_cause) +
    "</b> (" +
    Math.round((info.confidence || 0) * 100) +
    "% sure).</div>" +
    (info.summary
      ? '<div style="margin-top:4px;color:#4b5563">' +
        copilotEscape(info.summary) +
        "</div>"
      : "") +
    '<div style="margin-top:12px"><label for="copilot-review-cause">The root cause you found (needed for Wrong)</label>' +
    '<select id="copilot-review-cause" style="' +
    field +
    '">' +
    options +
    "</select></div>" +
    '<div style="margin-top:8px"><label for="copilot-review-note">Note (optional)</label>' +
    '<textarea id="copilot-review-note" rows="3" style="' +
    field +
    '" placeholder="What Copilot missed or got right">' +
    copilotEscape(review.note || "") +
    "</textarea></div></div>";

  function save(verdict, _ref) {
    var causeEl = document.getElementById("copilot-review-cause");
    var noteEl = document.getElementById("copilot-review-note");
    var cause = causeEl ? causeEl.value : "";
    if (verdict === "Wrong" && !cause) {
      toast.error("Choose the root cause you found.");
      return;
    }
    call("helpdesk.api.copilot.review_diagnosis", {
      ticket: doc.name,
      verdict: verdict,
      root_cause: verdict === "Right" ? "" : cause,
      note: noteEl ? noteEl.value : "",
    })
      .then(function () {
        toast.success("Rating saved: " + verdict);
        _ref.close();
      })
      .catch(function (error) {
        toast.error("Failed to save the rating");
        console.error("Copilot review error:", error);
      });
  }

  $dialog({
    title: "Rate Copilot's diagnosis - Ticket #" + doc.name,
    html: html,
    actions: [
      {
        label: "Right",
        variant: "solid",
        onClick: function (_ref) {
          save("Right", _ref);
        },
      },
      {
        label: "Partly",
        onClick: function (_ref) {
          save("Partly", _ref);
        },
      },
      {
        label: "Wrong",
        theme: "red",
        onClick: function (_ref) {
          save("Wrong", _ref);
        },
      },
      {
        label: "Cancel",
        onClick: function (_ref) {
          _ref.close();
        },
      },
    ],
  });
}

// The fix: its task, its pull request and its approval, inside the run dialog.
function copilotFixSummary(fix) {
  var rows = [];
  if (fix.task) {
    rows.push(["Fix task", fix.task.name + " (" + fix.task.status + ")"]);
  }
  if (fix.pull_request) {
    var pr = fix.pull_request;
    rows.push([
      "Pull request",
      pr.repo +
        "#" +
        pr.number +
        " · " +
        pr.state +
        (pr.ci_state && pr.ci_state !== "None" ? " · CI " + pr.ci_state : ""),
    ]);
  }
  var c = fix.copilot;
  if (c && c.status) {
    var said = {
      Queued: "waiting for a worker",
      Working: "working on it",
      Opened: "opened its pull request",
      Failed: "could not fix it; over to the developer",
    };
    rows.push([
      "Copilot's fix",
      (said[c.status] || c.status) +
        " (attempt " +
        Math.max(c.attempts, 1) +
        " of " +
        c.max_attempts +
        ")",
    ]);
  }
  var a = fix.approval;
  if (a) {
    rows.push([
      "Approval",
      a.status + (a.assigned_name ? " · " + a.assigned_name : ""),
    ]);
    rows.push([
      "Risk",
      a.risk_level + (a.sensitive ? " · needs a senior approver" : ""),
    ]);
    if (a.decided_by) {
      rows.push([
        "Decided",
        a.decided_by + (a.decided_at ? ", " + a.decided_at : ""),
      ]);
    }
    if (a.deploy_date) {
      rows.push(["Planned deploy", a.deploy_date]);
    }
  }
  var cs = fix.change_set;
  if (cs) {
    var done =
      cs.status === "Applied" || cs.status === "Stopped"
        ? " · " +
          cs.applied +
          " applied, " +
          cs.skipped +
          " left as changed since, " +
          cs.refused +
          " refused"
        : " · " + (cs.ready || 0) + " of " + (cs.total || 0) + " ready";
    rows.push(["Correction", cs.name + " · " + cs.status + done]);
  }
  if (fix.merge_commit) {
    rows.push(["Merge commit", String(fix.merge_commit).slice(0, 12)]);
  }
  if (fix.reverts) {
    rows.push(["Undoes", "the fix of " + fix.reverts]);
  }
  if (fix.revert_run) {
    rows.push(["Undone by", fix.revert_run]);
  }
  var d = fix.deploy;
  if (d) {
    rows.push([
      "Deploy",
      d.status +
        (d.scheduled_for && d.status !== "Succeeded"
          ? " · " + d.when + ", " + d.scheduled_for
          : ""),
    ]);
    if (d.sites && d.sites.length) {
      rows.push([
        "Sites",
        d.sites
          .map(function (s) {
            return s.site + (s.status ? " (" + s.status + ")" : "");
          })
          .join(", "),
      ]);
    }
    if (d.other_sites && d.other_sites.length) {
      rows.push(["Not moved", d.other_sites.join(", ")]);
    }
    for (var k = 0; k < (d.check || []).length; k++) {
      var c = d.check[k];
      rows.push([
        k === 0 ? "Check after" : "",
        (c.result === "pass" ? "✓ " : c.result === "fail" ? "✗ " : "– ") +
          c.check +
          (c.detail ? " (" + c.detail + ")" : ""),
      ]);
    }
  }
  if (fix.deployed_at) {
    rows.push(["Deployed", fix.deployed_at]);
  }
  if (!rows.length) {
    return "";
  }
  var html =
    '<div style="margin-top:8px"><b>Fix</b><table style="width:100%;font-size:13px">';
  for (var i = 0; i < rows.length; i++) {
    html +=
      '<tr><td style="color:#6b7280;padding:2px 8px 2px 0;white-space:nowrap">' +
      copilotEscape(rows[i][0]) +
      "</td><td>" +
      copilotEscape(rows[i][1]) +
      "</td></tr>";
  }
  html += "</table>";
  if (d && d.error && d.status !== "Succeeded") {
    html +=
      '<div style="color:#b91c1c">Deploy: ' + copilotEscape(d.error) + "</div>";
  }
  if (a && a.merge_error) {
    html +=
      '<div style="color:#b91c1c">Cannot merge yet: ' +
      copilotEscape(a.merge_error) +
      "</div>";
  }
  return html + "</div>";
}

// A customization: the scope the customer approved, and whether Copilot can build it.
// What Copilot remembers about this error (Phase 9): where it was seen, the fix, which sites have it.
function copilotKnownIssueHtml(issue, source) {
  var html =
    '<div style="margin-top:8px"><b>Known issue ' +
    copilotEscape(issue.name) +
    "</b> " +
    '<span style="color:#6b7280">' +
    copilotEscape(issue.status) +
    (issue.came_back ? ", came back " + issue.came_back + "x after a fix" : "") +
    "</span>";
  if (source === "Error watch") {
    html +=
      '<div style="color:#6b7280">Raised by Copilot\'s error watch: the customer hears nothing from Copilot until a person replies.</div>';
  }
  html +=
    "<div>" +
    copilotEscape(issue.title) +
    '</div><div style="color:#6b7280;font-size:12px"><code>' +
    copilotEscape(issue.signature) +
    "</code></div>" +
    '<div style="color:#6b7280">First seen ' +
    copilotEscape(issue.first_seen) +
    ", last seen " +
    copilotEscape(issue.last_seen) +
    "</div>";
  if (issue.fix) {
    html +=
      "<div>Fixed by " +
      (issue.fix.pull_request
        ? '<a href="' +
          copilotEscape(issue.fix.pull_request) +
          '" target="_blank">' +
          copilotEscape(issue.fix.title || issue.fix.pull_request) +
          "</a>"
        : copilotEscape(issue.fix.title || "-")) +
      " (" +
      copilotEscape(issue.fix.merge_commit) +
      ", " +
      copilotEscape(issue.fix.fixed_at) +
      ")</div>";
  }
  if (issue.sites && issue.sites.length) {
    html +=
      '<table style="width:100%;font-size:12px;margin-top:4px"><tr style="color:#6b7280"><td>Site</td><td>Customer</td><td>Times</td><td>Last seen</td><td>Ticket</td><td>Has the fix</td></tr>';
    for (var i = 0; i < issue.sites.length; i++) {
      var row = issue.sites[i];
      html +=
        "<tr><td>" +
        copilotEscape(row.site) +
        "</td><td>" +
        copilotEscape(row.customer || "-") +
        "</td><td>" +
        copilotEscape(row.count) +
        "</td><td>" +
        copilotEscape(row.last_seen) +
        "</td><td>" +
        copilotEscape(row.ticket || "-") +
        "</td><td>" +
        copilotEscape(row.has_fix || "-") +
        "</td></tr>";
    }
    html += "</table>";
  }
  if (issue.kb_article) {
    html += "<div>KB article: " + copilotEscape(issue.kb_article) + "</div>";
  }
  return html + "</div>";
}

function copilotBuildSummary(build) {
  var html =
    '<div style="margin-top:8px"><b>' +
    (build.building ? "Copilot builds the approved change" : "Customization") +
    "</b>" +
    (build.hours
      ? ' <span style="color:#6b7280">(' +
        copilotEscape(build.hours) +
        " hours estimated)</span>"
      : "");
  html += copilotScopeHtml(build.scope, build.checks, null);
  if (!build.building && !build.can_build && build.reason) {
    html +=
      '<div style="color:#6b7280;margin-top:4px">Build with Copilot: ' +
      copilotEscape(build.reason) +
      "</div>";
  }
  return html + "</div>";
}

// The scope and its Done-when checks; with a build's results, each check's test before and after.
function copilotScopeHtml(scope, checks, results) {
  var html = "";
  if (scope) {
    html +=
      '<div style="margin-top:4px;white-space:pre-line">' +
      copilotEscape(scope) +
      "</div>";
  }
  if (!checks || !checks.length) {
    return html;
  }
  var byCheck = {};
  for (var r = 0; r < (results || []).length; r++) {
    byCheck[
      String(results[r].check || "")
        .trim()
        .toLowerCase()
    ] = results[r];
  }
  html +=
    '<div style="margin-top:4px"><b>Done when</b></div><table style="width:100%;font-size:13px">';
  for (var i = 0; i < checks.length; i++) {
    var row = byCheck[String(checks[i]).trim().toLowerCase()];
    var result = "";
    if (results) {
      // fails before and passes after shows the change; holds before and after is a check kept
      var proven = row && row.before === "fail" && row.after === "pass";
      var kept = row && row.before === "pass" && row.after === "pass";
      result = !row
        ? '<span style="color:#b91c1c">no test</span>'
        : row.after === "not_testable"
        ? '<span style="color:#b45309">not testable: ' +
          copilotEscape(row.note) +
          "</span>"
        : '<span style="color:' +
          (proven ? "#047857" : kept ? "#6b7280" : "#b91c1c") +
          '">' +
          copilotEscape(
            proven
              ? "fails before, passes after"
              : kept
              ? "holds before and after"
              : row.before + " before, " + row.after + " after"
          ) +
          "</span>" +
          (row.test
            ? ' <span style="color:#6b7280">' +
              copilotEscape(row.test) +
              "</span>"
            : "");
    }
    html +=
      '<tr><td style="padding:2px 8px 2px 0">• ' +
      copilotEscape(checks[i]) +
      "</td><td>" +
      result +
      "</td></tr>";
  }
  return html + "</table>";
}

// What Copilot tested on its sandbox copy, when it made the fix itself.
function copilotTestedByCopilot(a) {
  var change = a.change;
  if (!change || !change.evidence || !change.evidence.length) {
    return "";
  }
  var marks = {
    pass: ["✓", "#047857"],
    fail: ["✗", "#b91c1c"],
    not_run: ["–", "#6b7280"],
  };
  var html =
    '<div style="margin-top:8px"><b>' +
    copilotEscape(
      "Tested by Copilot" + (change.tested_on ? " on " + change.tested_on : "")
    ) +
    "</b>";
  if (a.evidence_stale) {
    html +=
      '<div style="color:#b45309">These results are for an earlier commit: the pull request changed after Copilot tested it.</div>';
  }
  html += '<table style="width:100%;font-size:13px;margin-top:4px">';
  for (var i = 0; i < change.evidence.length; i++) {
    var row = change.evidence[i];
    var mark = marks[row.result] || marks.not_run;
    html +=
      '<tr><td style="color:' +
      mark[1] +
      ';padding:2px 6px 2px 0;width:1em">' +
      mark[0] +
      '</td><td style="padding:2px 8px 2px 0;white-space:nowrap">' +
      copilotEscape(row.check) +
      '</td><td style="color:#6b7280">' +
      copilotEscape(row.detail) +
      "</td></tr>";
  }
  html += "</table>";
  if (change.people_checks && change.people_checks.length) {
    html +=
      '<div style="margin-top:4px"><b>Worth checking by a person:</b><ul style="margin:2px 0 0 16px">';
    for (var j = 0; j < change.people_checks.length; j++) {
      html += "<li>" + copilotEscape(change.people_checks[j]) + "</li>";
    }
    html += "</ul></div>";
  }
  if (a.copilot_only) {
    html +=
      '<div style="margin-top:4px;color:#6b7280">Copilot wrote every commit, so the customer\'s developer may approve it.</div>';
  }
  return html + "</div>";
}

// Tomorrow in the agent's own time zone (toISOString would give the UTC date).
function copilotTomorrow() {
  var d = new Date();
  d.setDate(d.getDate() + 1);
  var month = String(d.getMonth() + 1).padStart(2, "0");
  var day = String(d.getDate()).padStart(2, "0");
  return d.getFullYear() + "-" + month + "-" + day;
}

// The server's own reason when it gave one (e.g. "already approved by …").
function copilotError(error, fallback) {
  var messages = (error && error.messages) || [];
  return messages.length ? fallback + ": " + messages.join(" ") : fallback;
}

// The one approval: what changes, how risky it is, what the checks say, and the decision.
function showCopilotFixReview(info, doc, call, toast, $dialog) {
  var a = info.fix.approval;
  var pr = info.fix.pull_request || {};
  var field =
    "width:100%;padding:6px;border:1px solid #d1d5db;border-radius:4px;font-size:13px";
  var html = '<div style="padding:8px;font-size:13px">';
  if (a.build) {
    html +=
      '<div><b>What the customer approved</b> <span style="color:#6b7280">(' +
      copilotEscape(a.build.hours) +
      " hours" +
      (a.build.approved_by
        ? ", by " + copilotEscape(a.build.approved_by)
        : "") +
      ")</span>" +
      copilotScopeHtml(
        a.build.scope,
        a.build.checks,
        (a.change && a.change.check_results) || []
      ) +
      "</div>";
  } else {
    html +=
      "<div><b>Cause</b> (" +
      copilotEscape(info.root_cause) +
      "): " +
      copilotEscape(info.summary || "") +
      "</div>";
  }
  html +=
    '<div style="margin-top:8px"><b>Pull request</b> ' +
    copilotEscape((pr.repo || "") + "#" + (pr.number || "")) +
    ": " +
    copilotEscape(pr.title || "") +
    ' <span style="color:#6b7280">at ' +
    copilotEscape(String(a.head_sha || "").slice(0, 12)) +
    "</span></div>";
  if (a.files && a.files.length) {
    html += '<ul style="margin:4px 0 0 16px">';
    var files = a.files.slice(0, 20);
    for (var i = 0; i < files.length; i++) {
      html +=
        "<li>" +
        copilotEscape(files[i].filename) +
        ' <span style="color:#6b7280">+' +
        copilotEscape(files[i].additions) +
        " −" +
        copilotEscape(files[i].deletions) +
        "</span></li>";
    }
    if (a.files.length > 20) {
      html += "<li>… " + copilotEscape(a.files.length - 20) + " more</li>";
    }
    html += "</ul>";
  }
  var riskColor =
    a.risk_level === "high"
      ? "#b91c1c"
      : a.risk_level === "medium"
      ? "#b45309"
      : "#047857";
  html +=
    '<div style="margin-top:8px"><b>Risk:</b> <span style="color:' +
    riskColor +
    '">' +
    copilotEscape(a.risk_level) +
    "</span>" +
    (a.sensitive ? " · needs a senior approver" : "") +
    "</div>";
  if (a.reasons && a.reasons.length) {
    html += '<ul style="margin:4px 0 0 16px;color:#4b5563">';
    for (var j = 0; j < a.reasons.length; j++) {
      html += "<li>" + copilotEscape(a.reasons[j]) + "</li>";
    }
    html += "</ul>";
  }
  var checks = a.checks || {};
  var checkText =
    checks.total === 0
      ? "no checks ran on this commit"
      : checks.green
      ? "all " + checks.total + " passed"
      : (checks.failing && checks.failing.length
          ? "failing: " + checks.failing.join(", ") + ". "
          : "") +
        (checks.pending && checks.pending.length
          ? "running: " + checks.pending.join(", ")
          : "");
  if (checkText && checks.partial) {
    checkText += " (GitHub Actions only: this token cannot read other checks)";
  }
  html +=
    '<div style="margin-top:8px"><b>Checks:</b> ' +
    copilotEscape(checkText || "not read yet") +
    ' <span style="color:#6b7280">(the hub merges only when they pass)</span></div>';
  html += copilotTestedByCopilot(a);
  if (a.kind === "Code + Data" && info.fix.change_set) {
    html +=
      '<div style="margin-top:8px"><b>With a data correction</b>: once the fix is live, Copilot applies it to the records below (' +
      copilotEscape(info.fix.change_set.name) +
      ").</div>";
    html += copilotRecordsHtml(info.fix.change_set);
  }
  if (a.why_not_me) {
    html +=
      '<div style="margin-top:8px;color:#b91c1c">' +
      copilotEscape(a.why_not_me) +
      "</div>";
  }
  html +=
    '<div style="margin-top:12px"><label for="copilot-fix-date">Planned deploy date (the customer is told)</label>' +
    '<input id="copilot-fix-date" type="date" style="' +
    field +
    '" value="' +
    copilotTomorrow() +
    '"></div>' +
    '<div style="margin-top:8px"><label for="copilot-fix-note">Note (needed to reject)</label>' +
    '<textarea id="copilot-fix-note" rows="3" style="' +
    field +
    '" placeholder="What is wrong, or anything the developer should know"></textarea></div></div>';

  // One decision at a time: a second click while the first is sent is ignored.
  var deciding = false;
  function decide(approve, _ref) {
    if (deciding) return;
    var dateEl = document.getElementById("copilot-fix-date");
    var noteEl = document.getElementById("copilot-fix-note");
    var note = noteEl ? noteEl.value : "";
    if (!approve && !note.trim()) {
      toast.error("Please say why the fix is rejected.");
      return;
    }
    deciding = true;
    call("helpdesk.api.copilot.decide_fix", {
      ticket: doc.name,
      approve: approve ? 1 : 0,
      note: note,
      deploy_date: dateEl ? dateEl.value : null,
    })
      .then(function (result) {
        var decision = (result && result.decision) || {};
        if (decision.outcome === "superseded") {
          toast.error(
            decision.message ||
              "The pull request changed; review the new version."
          );
        } else if (decision.outcome === "approved") {
          toast.success(
            decision.merge === "merged"
              ? "Approved and merged."
              : "Approved: the hub merges it when the checks pass."
          );
        } else {
          toast.success("Rejected: the developer gets your reason.");
        }
        _ref.close();
      })
      .catch(function (error) {
        deciding = false;
        toast.error(copilotError(error, "Failed to record the decision"));
        console.error("Copilot fix decision error:", error);
      });
  }

  var actions = [];
  if (!a.why_not_me) {
    actions.push({
      label: "Approve",
      variant: "solid",
      onClick: function (_ref) {
        decide(true, _ref);
      },
    });
    actions.push({
      label: "Reject",
      theme: "red",
      onClick: function (_ref) {
        decide(false, _ref);
      },
    });
  }
  if (a.url) {
    actions.push({
      label: "Open PR",
      onClick: function () {
        window.open(a.url, "_blank", "noopener");
      },
    });
  }
  actions.push({
    label: "Close",
    onClick: function (_ref) {
      _ref.close();
    },
  });
  $dialog({
    title: "Review fix - Ticket #" + doc.name,
    html: html,
    actions: actions,
  });
}

// The records of a correction, old → new, with what the site's check said.
function copilotRecordsHtml(cs) {
  var html =
    '<div style="margin-top:8px"><b>Records</b> (' +
    copilotEscape(cs.ready) +
    " of " +
    copilotEscape(cs.total) +
    " ready; the site checked each one without saving)</div>";
  html += '<ul style="margin:4px 0 0 16px">';
  for (var i = 0; i < cs.records.length; i++) {
    var rec = cs.records[i];
    var parts = [];
    for (var k = 0; k < rec.changes.length; k++) {
      var ch = rec.changes[k];
      parts.push(
        copilotEscape(ch.field) +
          ": " +
          copilotEscape(ch.old || "(empty)") +
          " → " +
          copilotEscape(ch.new)
      );
    }
    html +=
      "<li>" +
      copilotEscape(rec.doctype + " " + rec.name) +
      (rec.action === "create" ? " (new)" : "") +
      ": " +
      parts.join("; ") +
      (rec.check && rec.check !== "ready"
        ? ' <span style="color:#b45309">' +
          copilotEscape(rec.check + (rec.note ? ": " + rec.note : "")) +
          "</span>"
        : "") +
      "</li>";
  }
  html += "</ul>";
  if (cs.more) {
    html +=
      '<div style="color:#4b5563">… ' +
      copilotEscape(cs.more) +
      " more records: download them all.</div>";
  }
  return html;
}

// Undo an applied correction: the reverse change set (the old values), approved by a senior.
function showCopilotUndoChange(doc, call, toast, $dialog) {
  var field =
    "width:100%;padding:6px;border:1px solid #d1d5db;border-radius:4px;font-size:13px";
  $dialog({
    title: "Undo the change - Ticket #" + doc.name,
    html:
      '<div style="padding:8px;font-size:13px"><p>Copilot prepares the reverse of the correction from the values it replaced. The site checks it, a senior approves it, and then it is applied. The customer is not told. Records the correction created are listed for a person to remove.</p>' +
      '<label for="copilot-undo-change-reason">Why undo it (needed)</label>' +
      '<textarea id="copilot-undo-change-reason" rows="3" style="' +
      field +
      '"></textarea></div>',
    actions: [
      {
        label: "Undo the change",
        theme: "red",
        onClick: function (_ref) {
          var reasonEl = document.getElementById("copilot-undo-change-reason");
          var reason = reasonEl ? reasonEl.value.trim() : "";
          if (!reason) {
            toast.error("Please say why the correction is undone.");
            return;
          }
          call("helpdesk.api.copilot.undo_change", {
            ticket: doc.name,
            reason: reason,
          })
            .then(function () {
              toast.success(
                "The reverse correction is being checked; a senior approves it."
              );
              _ref.close();
            })
            .catch(function (error) {
              toast.error(copilotError(error, "Failed to undo the change"));
            });
        },
      },
      {
        label: "Cancel",
        onClick: function (_ref) {
          _ref.close();
        },
      },
    ],
  });
}

// A correction Copilot prepared (settings or data): every record with its old and new value,
// checked by the customer's site; a senior approves and the hub applies it at once.
function showCopilotCorrectionReview(info, doc, call, toast, $dialog) {
  var a = info.fix.approval;
  var cs = info.fix.change_set;
  var field =
    "width:100%;padding:6px;border:1px solid #d1d5db;border-radius:4px;font-size:13px";
  var html = '<div style="padding:8px;font-size:13px">';
  html +=
    "<div><b>Cause</b> (" +
    copilotEscape(info.root_cause) +
    "): " +
    copilotEscape(info.summary || "") +
    "</div>";
  html +=
    '<div style="margin-top:8px"><b>' +
    copilotEscape(cs.kind) +
    "</b> " +
    copilotEscape(cs.name) +
    ": " +
    copilotEscape(cs.summary || "") +
    "</div>";
  if (cs.found_by) {
    html +=
      '<div style="color:#4b5563">How the records were found: ' +
      copilotEscape(cs.found_by) +
      "</div>";
  }
  html +=
    '<div style="margin-top:8px"><b>Risk:</b> ' +
    copilotEscape(cs.risk || "medium") +
    " · a senior approves every correction" +
    (cs.environment ? " · the site is " + copilotEscape(cs.environment) : "") +
    "</div>";
  if (cs.risk_reasons && cs.risk_reasons.length) {
    html += '<ul style="margin:4px 0 0 16px;color:#4b5563">';
    for (var r = 0; r < cs.risk_reasons.length; r++) {
      html += "<li>" + copilotEscape(cs.risk_reasons[r]) + "</li>";
    }
    html += "</ul>";
  }
  html += copilotRecordsHtml(cs);
  if (cs.set_aside && cs.set_aside.length) {
    html +=
      '<div style="margin-top:8px"><b>Left for a person</b> (Copilot does not change these)</div><ul style="margin:4px 0 0 16px;color:#4b5563">';
    for (var s = 0; s < cs.set_aside.length; s++) {
      var aside = cs.set_aside[s];
      html +=
        "<li>" +
        copilotEscape((aside.doctype || "") + " " + (aside.name || "")) +
        (aside.why ? ": " + copilotEscape(aside.why) : "") +
        "</li>";
    }
    html += "</ul>";
  }
  if (cs.customer_note) {
    html +=
      '<div style="margin-top:8px"><b>The customer is told</b> once it is applied: ' +
      copilotEscape(cs.customer_note) +
      "</div>";
  }
  if (a.why_not_me) {
    html +=
      '<div style="margin-top:8px;color:#b91c1c">' +
      copilotEscape(a.why_not_me) +
      "</div>";
  }
  html +=
    '<div style="margin-top:8px"><label for="copilot-correction-note">Note (needed to reject)</label>' +
    '<textarea id="copilot-correction-note" rows="3" style="' +
    field +
    '"></textarea></div></div>';

  // One decision at a time: a second click while the first is sent is ignored.
  var deciding = false;
  function decide(approve, _ref) {
    if (deciding) return;
    var noteEl = document.getElementById("copilot-correction-note");
    var note = noteEl ? noteEl.value : "";
    if (!approve && !note.trim()) {
      toast.error("Please say why the correction is rejected.");
      return;
    }
    deciding = true;
    call("helpdesk.api.copilot.decide_fix", {
      ticket: doc.name,
      approve: approve ? 1 : 0,
      note: note,
    })
      .then(function (result) {
        var decision = (result && result.decision) || {};
        if (decision.outcome === "superseded") {
          toast.error(
            decision.message || "The correction changed; review it again."
          );
        } else if (decision.outcome === "approved") {
          toast.success(
            "Approved: Copilot is applying it on the customer's site."
          );
        } else {
          toast.success("Rejected.");
        }
        _ref.close();
      })
      .catch(function (error) {
        deciding = false;
        toast.error(copilotError(error, "Failed to record the decision"));
      });
  }

  var actions = [];
  if (!a.why_not_me) {
    actions.push({
      label: "Approve and apply",
      variant: "solid",
      onClick: function (_ref) {
        decide(true, _ref);
      },
    });
    actions.push({
      label: "Reject",
      theme: "red",
      onClick: function (_ref) {
        decide(false, _ref);
      },
    });
    actions.push({
      label: "Applied by hand",
      onClick: function (_ref) {
        call("helpdesk.api.copilot.change_set_applied_by_hand", {
          ticket: doc.name,
        })
          .then(function () {
            toast.success("Copilot read the records back from the site.");
            _ref.close();
          })
          .catch(function (error) {
            toast.error(copilotError(error, "Failed to read the records back"));
          });
      },
    });
  }
  actions.push({
    label: "Download all (CSV)",
    onClick: function () {
      window.open(cs.csv_url, "_blank", "noopener");
    },
  });
  actions.push({
    label: "Close",
    onClick: function (_ref) {
      _ref.close();
    },
  });
  $dialog({
    title: "Review correction - Ticket #" + doc.name,
    html: html,
    actions: actions,
  });
}

// Undo a merged fix that went wrong: GitHub's revert pull request, through the same one approval.
function showCopilotUndo(doc, call, toast, $dialog) {
  var field =
    "width:100%;padding:6px;border:1px solid #d1d5db;border-radius:4px;font-size:13px";
  $dialog({
    title: "Undo the fix - Ticket #" + doc.name,
    html:
      '<div style="padding:8px;font-size:13px"><p>TBO Support asks GitHub to revert the merged pull request. The revert goes through the same one approval and then Deploy. The customer is not told; the ticket stays with a person. A database restore, if needed, is a person\'s decision.</p>' +
      '<label for="copilot-undo-reason">Why undo it (needed)</label>' +
      '<textarea id="copilot-undo-reason" rows="3" style="' +
      field +
      '"></textarea></div>',
    actions: [
      {
        label: "Undo the fix",
        theme: "red",
        onClick: function (_ref) {
          var reasonEl = document.getElementById("copilot-undo-reason");
          var reason = reasonEl ? reasonEl.value.trim() : "";
          if (!reason) {
            toast.error("Please say why the fix is undone.");
            return;
          }
          call("helpdesk.api.copilot.undo_fix", {
            ticket: doc.name,
            reason: reason,
          })
            .then(function () {
              toast.success(
                "The revert pull request is open; it waits for the one approval."
              );
              _ref.close();
            })
            .catch(function (error) {
              toast.error(copilotError(error, "Failed to undo the fix"));
            });
        },
      },
      {
        label: "Cancel",
        onClick: function (_ref) {
          _ref.close();
        },
      },
    ],
  });
}

// Deploy through Press: tonight in the deploy window, or now (senior approvers and Agent Managers).
function showCopilotDeploy(fix, doc, call, toast, $dialog) {
  function request(when, _ref) {
    call("helpdesk.api.copilot.request_deploy", {
      ticket: doc.name,
      when: when,
    })
      .then(function (result) {
        var d = (result && result.fix && result.fix.deploy) || {};
        toast.success(
          when === "now"
            ? "Deploying now through Press."
            : "Scheduled for " + (d.scheduled_for || "tonight") + "."
        );
        _ref.close();
      })
      .catch(function (error) {
        toast.error(copilotError(error, "Failed to schedule the deploy"));
      });
  }
  var actions = [
    {
      label: "Deploy tonight",
      variant: "solid",
      onClick: function (_ref) {
        request("tonight", _ref);
      },
    },
  ];
  if (fix.can_deploy_now) {
    actions.push({
      label: "Deploy now",
      theme: "red",
      onClick: function (_ref) {
        request("now", _ref);
      },
    });
  }
  actions.push({
    label: "Cancel",
    onClick: function (_ref) {
      _ref.close();
    },
  });
  $dialog({
    title: "Deploy the fix - Ticket #" + doc.name,
    html:
      '<div style="padding:8px;font-size:13px"><p>TBO Support updates only this customer\'s sites through Press (' +
      (fix.press_backups
        ? "Press takes a backup first"
        : "<b>without a backup</b>: Skip Press's backup is on in the Copilot settings") +
      "), then checks that the site runs the merged fix without new errors, and asks the customer to confirm. Other sites on the bench stay on their current code.</p>" +
      "<p><b>Sites it updates:</b> " +
      copilotEscape(
        (fix.deploy_sites || []).join(", ") ||
          "none: the site card needs its Press site and bench"
      ) +
      "</p>" +
      "<p><b>Tonight</b> waits for the deploy window. <b>Now</b> is for urgent fixes and only for senior approvers and Agent Managers. One deploy runs at a time.</p></div>",
    actions: actions,
  });
}

// After an engineer deployed the merged fix through Press: the customer is asked to confirm.
function showCopilotMarkDeployed(doc, call, toast, $dialog) {
  var field =
    "width:100%;padding:6px;border:1px solid #d1d5db;border-radius:4px;font-size:13px";
  $dialog({
    title: "Mark deployed - Ticket #" + doc.name,
    html:
      '<div style="padding:8px;font-size:13px"><div>Press this once the merged fix is live on the customer\'s site. The customer is then asked to confirm it.</div>' +
      '<div style="margin-top:8px"><label for="copilot-deploy-note">Note for the customer (optional)</label>' +
      '<textarea id="copilot-deploy-note" rows="2" style="' +
      field +
      '"></textarea></div></div>',
    actions: [
      {
        label: "Mark deployed",
        variant: "solid",
        onClick: function (_ref) {
          var noteEl = document.getElementById("copilot-deploy-note");
          call("helpdesk.api.copilot.mark_deployed", {
            ticket: doc.name,
            note: noteEl ? noteEl.value : "",
          })
            .then(function () {
              toast.success(
                "Marked deployed; the customer is asked to confirm."
              );
              _ref.close();
            })
            .catch(function (error) {
              toast.error(copilotError(error, "Failed to mark it deployed"));
            });
        },
      },
      {
        label: "Cancel",
        onClick: function (_ref) {
          _ref.close();
        },
      },
    ],
  });
}

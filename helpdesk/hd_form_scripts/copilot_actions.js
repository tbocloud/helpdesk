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
        var info = await call("helpdesk.api.copilot.get_run", { ticket: doc.name });
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
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
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
    ["Customer sees", info.shadow ? "Nothing (shadow mode)" : info.stage || "-"],
    [
      "Root cause",
      info.root_cause
        ? info.root_cause + " (" + Math.round((info.confidence || 0) * 100) + "% sure)"
        : "-",
    ],
    ["Worker", info.worker_id || "-"],
    ["Task", info.task || "-"],
    ["Handed over to", info.handed_over_to || "-"],
  ];
  if (info.base_commit) {
    rows.push(["Code read at", (info.base_app || "app") + " @ " + String(info.base_commit).slice(0, 12)]);
  }
  if (info.model_used) {
    rows.push([
      "Model",
      info.model_used + " (" + (info.tokens_in || 0) + " tokens in, " + (info.tokens_out || 0) + " out)",
    ]);
  }
  var html = '<div style="padding:8px"><table style="width:100%;font-size:13px">';
  for (var i = 0; i < rows.length; i++) {
    html +=
      '<tr><td style="color:#6b7280;padding:2px 8px 2px 0;white-space:nowrap">' +
      copilotEscape(rows[i][0]) +
      "</td><td>" +
      copilotEscape(rows[i][1]) +
      "</td></tr>";
  }
  html += "</table>";
  if (info.summary) {
    html +=
      '<div style="margin-top:8px"><b>Diagnosis</b><div>' + copilotEscape(info.summary) + "</div></div>";
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
        ? '<div style="white-space:pre-line;color:#4b5563">' + copilotEscape(info.review.note) + "</div>"
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
    html += '<div style="margin-top:8px"><b>Evidence</b><ul style="margin:4px 0 0 16px">';
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
      label: info.review && info.review.verdict ? "Change rating" : "Rate diagnosis",
      variant: "subtle",
      onClick: function (_ref) {
        _ref.close();
        showCopilotReviewDialog(info, doc, call, toast, $dialog);
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
      '<option value="' + copilotEscape(c) + '"' + (review.root_cause === c && review.verdict !== "Right" ? " selected" : "") + ">" +
      copilotEscape(c) +
      "</option>";
  }
  var field = "width:100%;padding:6px;border:1px solid #d1d5db;border-radius:4px;font-size:13px";
  var html =
    '<div style="padding:8px;font-size:13px">' +
    "<div>Copilot said <b>" +
    copilotEscape(info.root_cause) +
    "</b> (" +
    Math.round((info.confidence || 0) * 100) +
    "% sure).</div>" +
    (info.summary ? '<div style="margin-top:4px;color:#4b5563">' + copilotEscape(info.summary) + "</div>" : "") +
    '<div style="margin-top:12px"><label for="copilot-review-cause">The root cause you found (needed for Wrong)</label>' +
    '<select id="copilot-review-cause" style="' + field + '">' + options + "</select></div>" +
    '<div style="margin-top:8px"><label for="copilot-review-note">Note (optional)</label>' +
    '<textarea id="copilot-review-note" rows="3" style="' + field + '" placeholder="What Copilot missed or got right">' +
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
      { label: "Right", variant: "solid", onClick: function (_ref) { save("Right", _ref); } },
      { label: "Partly", onClick: function (_ref) { save("Partly", _ref); } },
      { label: "Wrong", theme: "red", onClick: function (_ref) { save("Wrong", _ref); } },
      { label: "Cancel", onClick: function (_ref) { _ref.close(); } },
    ],
  });
}

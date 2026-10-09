// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// The Copilot button on the ticket page: start a run, see what it found, cancel it.
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
    ["Customer sees", info.stage || "-"],
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

# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The TBO Copilot bot in Microsoft Teams (Phase 6): Bot Framework in and out.

In: `helpdesk.api.copilot_teams.messages` checks the Bot Framework token (signature from the
published keys, issuer, audience = our bot, the service URL) and our tenant, then hands the
activity here. Out: the Bot Framework REST API with the bot's own client-credentials token.
People are HDS Teams User rows, matched to agents by their Microsoft email. The engine is
`assistant.py`; this module only carries messages and draws Adaptive Cards.
"""

import json
import re

import frappe
import jwt
import requests
from frappe import _

OPENID = "https://login.botframework.com/v1/.well-known/openidconfiguration"
ISSUER = "https://api.botframework.com"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
SCOPE = "https://api.botframework.com/.default"
TEAMS_USER = "HDS Teams User"
KEYS_KEY = "copilot-teams:keys"
TOKEN_KEY = "copilot-teams:token"
TIMEOUT = 15
MAX_FILE_BYTES = 50 * 1024 * 1024
FILE_INFO = "application/vnd.microsoft.teams.file.download.info"
CARD = "application/vnd.microsoft.card.adaptive"


class TeamsError(Exception):
    pass


def settings():
    from helpdesk.copilot import settings as copilot_settings

    return copilot_settings.get_settings()


def tenant() -> str:
    return (
        settings().get("teams_tenant_id")
        or frappe.db.get_single_value("HD Settings", "microsoft_tenant_id")
        or ""
    ).strip()


def app_id() -> str:
    return (settings().get("teams_bot_app_id") or "").strip()


def enabled() -> bool:
    s = settings()
    return bool(
        s.get("teams_bot_enabled")
        and app_id()
        and s.get_password("teams_bot_secret", raise_exception=False)
        and tenant()
    )


# --- the incoming token ---------------------------------------------------------------------------


def signing_keys(refresh: bool = False) -> dict:
    """Bot Framework's published signing keys by key id, cached for a day."""
    cached = None if refresh else frappe.cache.get_value(KEYS_KEY)
    if cached:
        return cached
    config = requests.get(OPENID, timeout=TIMEOUT).json()
    jwks = requests.get(config["jwks_uri"], timeout=TIMEOUT).json()
    keys = {
        key["kid"]: json.dumps(key)
        for key in jwks.get("keys", [])
        if key.get("kid") and key.get("kty") == "RSA"
    }
    frappe.cache.set_value(KEYS_KEY, keys, expires_in_sec=24 * 3600)
    return keys


def check_token(header: str | None, service_url: str | None) -> dict:
    """The token's claims, or a PermissionError: signed by Bot Framework, for our bot, from this service URL."""
    if not header or not header.startswith("Bearer "):
        raise frappe.PermissionError("no Bot Framework token")
    token = header[len("Bearer ") :].strip()
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        keys = signing_keys()
        if kid not in keys:
            keys = signing_keys(refresh=True)  # Microsoft rotates its keys
        if kid not in keys:
            raise frappe.PermissionError("unknown signing key")
        key = jwt.algorithms.RSAAlgorithm.from_jwk(keys[kid])
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=app_id(),
            issuer=ISSUER,
            leeway=300,
        )
    except jwt.PyJWTError as e:
        raise frappe.PermissionError(f"bad Bot Framework token: {e}") from e
    claimed = (
        (claims.get("serviceurl") or claims.get("serviceUrl") or "").rstrip("/").lower()
    )
    if not service_url or claimed != service_url.rstrip("/").lower():
        raise frappe.PermissionError("the token is for another service URL")
    return claims


REFUSED_KEY = "copilot_teams_refused:"
REFUSALS_PER_HOUR = 20
ENDPOINT = "helpdesk.api.copilot_teams.messages"
# the bot's own user: no roles, no password; requests Bot Framework signed run as it
BOT_USER = "teams.bot@tbo-copilot.internal"


def ensure_bot_user() -> str:
    """The bot's own user, made on migrate (and when it is missing): a website user without roles."""
    if not frappe.db.exists("User", BOT_USER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": BOT_USER,
                "first_name": "TBO Copilot Teams bot",
                "user_type": "Website User",
                "send_welcome_email": 0,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
    return BOT_USER


def authenticate():
    """auth_hooks: lets Bot Framework's own token through Frappe's sign-in, for the bot's endpoint only.

    Frappe takes any "Authorization: Bearer …" for its own credentials (an OAuth token or an
    API key) and refuses the request when no user results, before the endpoint runs, so no
    message from Teams ever reached it. For a POST to the bot's endpoint with a token Bot
    Framework signed for our bot and this service URL, the request goes on as the bot's own
    user, which has no roles; the endpoint then checks the token again, the tenant, and acts
    only as the person it finds in TBO Support. Anything else is left to Frappe, which
    refuses it as before.
    """
    if frappe.session.user not in ("", "Guest"):
        return
    request = getattr(frappe.local, "request", None)
    if (
        not request
        or request.method != "POST"
        or request.path.rstrip("/") != f"/api/method/{ENDPOINT}"
    ):
        return
    header = frappe.get_request_header("Authorization") or ""
    if not header.startswith("Bearer ") or not enabled():
        return
    activity = request.get_json(silent=True) or {}
    try:
        check_token(header, activity.get("serviceUrl"))
    except frappe.PermissionError as e:
        frappe.clear_last_message()
        note_refusal(str(e), activity, header, keep=True)
        return  # Frappe answers 401
    frappe.set_user(ensure_bot_user())


def note_refusal(
    reason: str, activity: dict, header: str | None = None, keep: bool = False
):
    """A call from Teams the bot refused, written down once an hour per reason and sender, so a
    setup that never connects says why, and one person's refusal (or a test's) never hides
    another's: the IDs Teams sent next to ours, never the token itself. The sender is not
    proven yet, so at most REFUSALS_PER_HOUR notes are written an hour.

    A call without a Bot Framework token is ignored (anyone on the internet can send one).
    """
    if not (header or "").startswith("Bearer ") and "tenant" not in reason:
        return
    kind = reason.split(":")[0].strip()[:60]
    sender = activity.get("from") or {}
    who = str(sender.get("aadObjectId") or sender.get("id") or "")[:80]
    cache = frappe.cache()
    marker = cache.make_key(f"{REFUSED_KEY}{reason[:120]}|{who}")
    if cache.get(marker):  # the site's own key (make_key) - nosemgrep
        return  # the same refusal from the same sender is written down once an hour
    counter = cache.make_key(REFUSED_KEY + "count")
    cache.set(counter, 0, ex=3600, nx=True)  # nosemgrep
    if cache.incr(counter) > REFUSALS_PER_HOUR:
        return
    claims = {}
    if (header or "").startswith("Bearer "):
        try:
            unverified = jwt.decode(
                header[len("Bearer ") :].strip(), options={"verify_signature": False}
            )
            claims = {key: unverified.get(key) for key in ("iss", "aud", "serviceurl")}
        except jwt.PyJWTError:
            claims = {"token": "not readable"}
    details = {
        "reason": reason[:300],
        "activity": activity.get("type"),
        "channel": activity.get("channelId"),
        "service_url": activity.get("serviceUrl"),
        "their_tenant": ((activity.get("channelData") or {}).get("tenant") or {}).get(
            "id"
        ),
        "our_tenant": tenant(),
        "to_bot": (activity.get("recipient") or {}).get("id"),
        "our_bot": app_id(),
        "from": {key: sender.get(key) for key in ("id", "aadObjectId", "name")},
        "token_says": claims,
    }
    frappe.log_error(
        title=f"Copilot Teams bot refused a call: {kind}",
        message=json.dumps(details, indent=1, default=str),
    )
    if keep:
        # refused at sign-in, Frappe rolls the request back: the note is saved first
        frappe.db.commit()  # nothing else of this request is written - nosemgrep
    frappe.cache().set(marker, 1, ex=3600)  # the site's own key (make_key) - nosemgrep


def from_our_tenant(activity: dict) -> bool:
    return ((activity.get("channelData") or {}).get("tenant") or {}).get(
        "id"
    ) == tenant()


# --- calling Bot Framework ------------------------------------------------------------------------


# the bot's key comes from its tenant (a Single Tenant bot) or from Bot Framework's own
# tenant (a Multi Tenant bot); the one Bot Framework accepted is remembered
AUTHORITY_KEY = "copilot-teams:token-authority"
BOT_FRAMEWORK_TENANT = "botframework.com"


def authorities() -> list[str]:
    """Where to ask for the bot's key, the one that worked last first."""
    both = list(dict.fromkeys([tenant() or BOT_FRAMEWORK_TENANT, BOT_FRAMEWORK_TENANT]))
    # kept with an expiry, so read past the request's own copy
    remembered = frappe.cache.get_value(AUTHORITY_KEY, expires=True)
    if remembered in both:
        both.remove(remembered)
        both.insert(0, remembered)
    return both


def bot_token(authority: str | None = None) -> str:
    authority = authority or authorities()[0]
    key = f"{TOKEN_KEY}:{authority}"
    cached = frappe.cache.get_value(key, expires=True)
    if cached:
        return cached
    response = requests.post(
        TOKEN_URL.format(tenant=authority),
        data={
            "grant_type": "client_credentials",
            "client_id": app_id(),
            "client_secret": settings().get_password("teams_bot_secret"),
            "scope": SCOPE,
        },
        timeout=TIMEOUT,
    )
    data = response.json() if response.content else {}
    if response.status_code >= 300 or not data.get("access_token"):
        # Microsoft's first sentence carries its code (AADSTS…); the rest is trace IDs
        said = (data.get("error_description") or "").split(". ")[0][:200]
        raise TeamsError(
            _("The Teams bot could not sign in: {0}").format(
                said or data.get("error") or response.status_code
            )
        )
    frappe.cache.set_value(
        key,
        data["access_token"],
        expires_in_sec=max(int(data.get("expires_in") or 3600) - 300, 60),
    )
    return data["access_token"]


def key_says(token: str) -> str:
    """Who issued the bot's key and for which app, read from the key itself (not secret)."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return "not readable"
    return "tenant {0}, app {1}".format(
        claims.get("tid"), claims.get("appid") or claims.get("azp")
    )


def call(method: str, service_url: str, path: str, body: dict | None = None) -> dict:
    """One Bot Framework call with the bot's key: its tenant's first; when Bot Framework refuses
    it (a bot registered as Multi Tenant), once more with Bot Framework's own. When none works,
    the error says for each where it came from: Microsoft would not issue it (with its AADSTS
    code), or Bot Framework refused it (with who issued it)."""
    response, tried = None, []
    for authority in authorities():
        try:
            token = bot_token(authority)
        except TeamsError as e:
            tried.append(f"{authority}: Microsoft gave no key ({e})")
            continue
        response = requests.request(
            method,
            service_url.rstrip("/") + path,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        if response.status_code != 401:
            frappe.cache.set_value(
                AUTHORITY_KEY, authority, expires_in_sec=7 * 24 * 3600
            )
            break
        # a refused key is not used again: the next call asks Microsoft for a new one
        frappe.cache.delete_value(f"{TOKEN_KEY}:{authority}")
        tried.append(
            f"{authority}: Bot Framework refused its key (issued by {key_says(token)})"
        )
    if response is None:
        raise TeamsError(
            "The Teams bot has no key Bot Framework accepts: " + "; ".join(tried)
        )
    if response.status_code >= 300:
        hint = (
            " ("
            + "; ".join(tried)
            + ". Check the Azure Bot's Microsoft App Type and App Tenant ID against"
            " the Tenant ID in Teams bot settings)"
            if response.status_code == 401
            else ""
        )
        raise TeamsError(
            f"Bot Framework {method} {path}: {response.status_code} {response.text[:300]}{hint}"
        )
    return response.json() if response.content else {}


def activity_for(reply: dict) -> dict:
    if (
        not any(reply.get(k) for k in ("actions", "facts", "links", "inputs", "title"))
        and len(reply.get("lines") or []) == 1
    ):
        return {"type": "message", "text": reply["lines"][0]}
    return {
        "type": "message",
        "attachments": [{"contentType": CARD, "content": adaptive(reply)}],
    }


def person(user: str):
    name = frappe.db.get_value(
        TEAMS_USER,
        {
            "user": user,
            "disabled": 0,
            "conversation_id": ["is", "set"],
            "service_url": ["is", "set"],
        },
        "name",
    )
    return frappe.get_doc(TEAMS_USER, name) if name else None


def reachable(user: str) -> bool:
    """The bot can start a message to this person: it is set up and knows their personal chat."""
    return bool(enabled() and person(user))


def send_card(user: str, reply: dict) -> str | None:
    """A card into the person's personal chat; returns the Teams message id."""
    who = person(user)
    if not who:
        return None
    result = call(
        "POST",
        who.service_url,
        f"/v3/conversations/{who.conversation_id}/activities",
        activity_for(reply),
    )
    return result.get("id")


def update_card(user: str, activity_id: str, reply: dict):
    """Replaces a card the bot sent earlier (a decision made elsewhere, say)."""
    who = person(user)
    if who and activity_id:
        call(
            "PUT",
            who.service_url,
            f"/v3/conversations/{who.conversation_id}/activities/{activity_id}",
            {**activity_for(reply), "id": activity_id},
        )


def reply_in(activity: dict, reply: dict) -> str | None:
    """An answer in the conversation the activity came from; the Teams message id. A recorded
    reply keeps the id, so a later decision can update its card."""
    conversation = (activity.get("conversation") or {}).get("id")
    result = call(
        "POST",
        activity["serviceUrl"],
        f"/v3/conversations/{conversation}/activities",
        {**activity_for(reply), "replyToId": activity.get("id")},
    )
    if reply.get("message") and result.get("id"):
        frappe.db.set_value(
            "HDS Copilot Chat Message",
            reply["message"],
            "teams_activity",
            result["id"],
            update_modified=False,
        )
    return result.get("id")


# --- who is who ------------------------------------------------------------------------------------


def remember(activity: dict) -> str | None:
    """The agent behind an activity, keeping their personal chat for later messages; None when unknown."""
    sender = activity.get("from") or {}
    aad = sender.get("aadObjectId")
    conversation = activity.get("conversation") or {}
    personal = conversation.get("conversationType") in (None, "personal")
    if not aad:
        return None
    name = frappe.db.get_value(TEAMS_USER, {"aad_object_id": aad})
    doc = frappe.get_doc(TEAMS_USER, name) if name else None
    if not doc:
        email = member_email(activity, sender.get("id"))
        user = (
            frappe.db.get_value("User", {"email": email, "enabled": 1})
            if email
            else None
        )
        doc = frappe.get_doc(
            {
                "doctype": TEAMS_USER,
                "aad_object_id": aad,
                "teams_id": sender.get("id"),
                "email": email,
                "user": user,
            }
        ).insert(ignore_permissions=True)
    updates = {"last_seen": frappe.utils.now_datetime()}
    if (
        personal
        and conversation.get("id")
        and (
            doc.conversation_id != conversation["id"]
            or doc.service_url != activity.get("serviceUrl")
        )
    ):
        updates.update(
            {
                "conversation_id": conversation["id"],
                "service_url": activity.get("serviceUrl"),
            }
        )
    doc.db_set(updates, update_modified=False)
    return None if doc.disabled else doc.user


def member_email(activity: dict, member_id: str | None) -> str | None:
    """The person's Microsoft email, read from the conversation's member list."""
    if not member_id:
        return None
    try:
        member = call(
            "GET",
            activity["serviceUrl"],
            f"/v3/conversations/{activity['conversation']['id']}/members/{member_id}",
        )
    except TeamsError:
        frappe.log_error(title="Copilot Teams bot could not read a member's email")
        return None
    return (
        member.get("email") or member.get("userPrincipalName") or ""
    ).lower() or None


# --- files sent to the bot ---------------------------------------------------------------------------


def save_files(activity: dict, chat) -> list[str]:
    """Images and files sent with a message, saved privately on the person's chat; their File names."""
    saved = []
    for attachment in activity.get("attachments") or []:
        kind = attachment.get("contentType") or ""
        if kind == FILE_INFO:
            url = (attachment.get("content") or {}).get("downloadUrl")
            headers = {}  # a pre-authorised link
        elif kind.startswith("image/") and attachment.get("contentUrl"):
            url = attachment["contentUrl"]
            headers = {"Authorization": f"Bearer {bot_token()}"}
        else:
            continue  # the message's own HTML, cards, links
        if not url:
            continue
        response = requests.get(url, headers=headers, timeout=60, stream=True)
        if response.status_code >= 300:
            continue
        content = response.raw.read(MAX_FILE_BYTES + 1, decode_content=True)
        if len(content) > MAX_FILE_BYTES:
            continue
        name = attachment.get("name") or f"teams-image.{kind.split('/')[-1] or 'png'}"
        saved.append(
            frappe.get_doc(
                {
                    "doctype": "File",
                    "file_name": name[:140],
                    "content": content,
                    "is_private": 1,
                    "attached_to_doctype": "HDS Copilot Chat",
                    "attached_to_name": chat.name,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
    return saved


# --- activities -------------------------------------------------------------------------------------


UNKNOWN = "I don't know you in TBO Support yet. Ask your manager to add you as an agent with this Microsoft email."

# --- joining a Teams account to its agent, by a one-time link the person opens signed in -----------
# Bot Framework may not say who wrote (its member lookup can be refused), and an admin pairing
# accounts by hand can pair the wrong ones; the person links their own account instead.
LINK_KEY = "copilot-teams:link:"
LINK_MINUTES = 30
LINK_CODE = re.compile(r"^[0-9a-f]{32}$")


def unknown_card(activity: dict) -> dict:
    """For someone the bot does not know yet: a one-time link that joins this Teams account to theirs."""
    from helpdesk.copilot import assistant

    aad = (activity.get("from") or {}).get("aadObjectId")
    name = frappe.db.get_value(TEAMS_USER, {"aad_object_id": aad}) if aad else None
    if not name or frappe.db.get_value(TEAMS_USER, name, "disabled"):
        return assistant.text_card(UNKNOWN)
    code = frappe.generate_hash(length=32)
    frappe.cache.set_value(LINK_KEY + code, name, expires_in_sec=LINK_MINUTES * 60)
    return assistant.card(
        _("I don't know you in TBO Support yet"),
        [
            _(
                "Open this link while you are signed in to TBO Support as yourself: it joins this Teams account to your agent account. It works once, for {0} minutes."
            ).format(LINK_MINUTES),
            _("Not an agent yet? Ask your manager to add you first."),
        ],
        links=[
            (
                _("Link my Teams account"),
                frappe.utils.get_url(
                    f"/api/method/helpdesk.api.copilot_teams.link?code={code}"
                ),
            )
        ],
    )


def link_target(code: str | None):
    """The Teams record a one-time link stands for; None when the code is unknown, used or expired."""
    if not code or not LINK_CODE.match(code):
        return None
    name = frappe.cache.get_value(LINK_KEY + code, expires=True)
    return (
        frappe.get_doc(TEAMS_USER, name)
        if name and frappe.db.exists(TEAMS_USER, name)
        else None
    )


def why_not_link(record, user: str) -> str | None:
    """Why `user` may not take this Teams account, or None when they may."""
    from helpdesk.copilot import assistant

    if not assistant.is_agent(user):
        return _(
            "Only TBO Support agents can link a Teams account. Ask your manager to add you as an agent first."
        )
    if record.disabled:
        return _("This Teams account is switched off in TBO Support.")
    if record.user and record.user != user:
        return _(
            "This Teams account is already linked to someone else in TBO Support. Ask a System Manager."
        )
    if frappe.db.exists(
        TEAMS_USER, {"user": user, "name": ["!=", record.name], "disabled": 0}
    ):
        return _(
            "Your TBO Support account is already linked to another Teams account. Ask a System Manager."
        )
    email = (frappe.db.get_value("User", user, "email") or "").lower()
    if record.email and record.email.lower() != email:
        return _("This Teams account's Microsoft email is not your TBO Support email.")
    return None


def link(code: str, user: str):
    """Joins the Teams account behind a one-time link to `user`; the code is used up."""
    from helpdesk.copilot import assistant

    record = link_target(code)
    if not record:
        frappe.throw(
            _(
                "This link is no longer valid. Write to TBO Copilot in Teams for a new one."
            )
        )
    if reason := why_not_link(record, user):
        frappe.throw(reason, frappe.PermissionError)
    frappe.cache.delete_value(LINK_KEY + code)
    record.db_set("user", user)
    record.add_comment(
        "Info",
        _("{0} linked this Teams account with a one-time link from the bot.").format(
            frappe.utils.get_fullname(user)
        ),
    )
    try:
        assistant.send(user, assistant.help_card())
    except Exception:
        frappe.log_error(title=f"Copilot could not greet {user} in Teams")
    return record


def handle_activity(activity: dict) -> dict | None:
    """One activity from Teams; the body of the answer for a card's button, else None."""
    from helpdesk.copilot import assistant

    if not from_our_tenant(activity):
        raise frappe.PermissionError("another tenant")
    kind = activity.get("type")
    if kind == "conversationUpdate":
        # the app was installed for the person: keep their chat so reminders can reach them
        bot = (activity.get("recipient") or {}).get("id")
        if any(m.get("id") == bot for m in activity.get("membersAdded") or []):
            remember(activity)
        return None
    if kind == "message":
        frappe.enqueue(
            "helpdesk.copilot.teams.answer_message",
            queue="short",
            activity=activity,
            enqueue_after_commit=True,
            now=frappe.flags.in_test,
        )
        return None
    if kind == "invoke" and activity.get("name") == "adaptiveCard/action":
        user = remember(activity)
        if not user:
            return invoke_answer(unknown_card(activity))
        action = (activity.get("value") or {}).get("action") or {}
        data = dict(action.get("data") or {})
        inputs = {"reason": data.pop("reason", "")}
        result = assistant.press(user, "Teams", action.get("verb") or "", data, inputs)
        pressed = activity.get("replyToId")
        if pressed and result.get("card"):
            # the stored copy of the pressed card follows what Teams now shows
            for name in frappe.get_all(
                assistant.MESSAGE, filters={"teams_activity": pressed}, pluck="name"
            ):
                frappe.db.set_value(
                    assistant.MESSAGE,
                    name,
                    "card",
                    json.dumps(result["card"], ensure_ascii=False),
                    update_modified=False,
                )
        for reply in result.get("replies") or []:
            reply_in(activity, reply)
        return invoke_answer(result.get("card"))
    return None


def answer_message(activity: dict):
    """Background: a person's message read and answered in the same chat."""
    from helpdesk.copilot import assistant

    user = remember(activity)
    if not user:
        reply_in(activity, unknown_card(activity))
        return
    chat = assistant.chat_for(user, "Teams")
    files = save_files(activity, chat)
    text = frappe.utils.strip_html_tags(activity.get("text") or "").strip()
    try:
        replies = assistant.receive(user, "Teams", text, files)
    except frappe.ValidationError as e:
        frappe.clear_last_message()
        replies = [assistant.text_card(str(e), "warning")]
    for reply in replies:
        reply_in(activity, reply)


def invoke_answer(reply: dict | None) -> dict:
    if not reply:
        return {
            "statusCode": 200,
            "type": "application/vnd.microsoft.activity.message",
            "value": "OK",
        }
    return {"statusCode": 200, "type": CARD, "value": adaptive(reply)}


# --- Adaptive Cards ------------------------------------------------------------------------------------


TONES = {"good": "Good", "warning": "Warning", "default": "Default"}
STYLES = {"positive": "positive", "destructive": "destructive"}


def adaptive(reply: dict) -> dict:
    """An engine reply as an Adaptive Card 1.5 with Universal Actions (Action.Execute)."""
    body = []
    if reply.get("title"):
        body.append(
            {
                "type": "TextBlock",
                "text": reply["title"],
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
                "color": TONES.get(reply.get("tone"), "Default"),
            }
        )
    for line in reply.get("lines") or []:
        body.append(
            {"type": "TextBlock", "text": line, "wrap": True, "spacing": "Small"}
        )
    if reply.get("facts"):
        body.append(
            {
                "type": "FactSet",
                "facts": [{"title": k, "value": v} for k, v in reply["facts"]],
            }
        )
    for field in reply.get("inputs") or []:
        body.append(
            {
                "type": "Input.Text",
                "id": field["id"],
                "label": field.get("label"),
                "isMultiline": bool(field.get("multiline")),
            }
        )
    actions = [
        {
            "type": "Action.Execute",
            "title": a["label"],
            "verb": a["verb"],
            "data": a.get("data") or {},
            **({"style": STYLES[a["style"]]} if a.get("style") in STYLES else {}),
        }
        for a in reply.get("actions") or []
    ] + [
        {"type": "Action.OpenUrl", "title": label, "url": url}
        for label, url in reply.get("links") or []
    ]
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": body or [{"type": "TextBlock", "text": " "}],
        "actions": actions,
    }


# --- the Teams app for the admin -------------------------------------------------------------------------


def manifest() -> dict:
    """The "TBO Copilot" Teams app: a personal bot that takes files, for this site's Azure Bot."""
    from urllib.parse import urlparse

    site = frappe.utils.get_url()
    return {
        "$schema": "https://developer.microsoft.com/en-us/json-schemas/teams/v1.17/MicrosoftTeams.schema.json",
        "manifestVersion": "1.17",
        "version": "1.0.0",
        "id": app_id(),
        "developer": {
            "name": "Team Back Office",
            "websiteUrl": site,
            "privacyUrl": site,
            "termsOfUseUrl": site,
        },
        "name": {
            "short": "TBO Copilot",
            "full": "TBO Copilot, the support team's AI engineer",
        },
        "description": {
            "short": "Approve Copilot's fixes, ask about tasks and give it new work.",
            "full": "TBO Copilot tells you when a fix is ready, merged or deployed. Approve or reject it from the card, ask what changed and why, ask for a change, or send new work with a screenshot or a video. It acts with your TBO Support permissions, and only after you confirm.",
        },
        "icons": {"color": "color.png", "outline": "outline.png"},
        "accentColor": "#2563EB",
        "bots": [
            {
                "botId": app_id(),
                "scopes": ["personal"],
                "supportsFiles": True,
                "isNotificationOnly": False,
                "commandLists": [
                    {
                        "scopes": ["personal"],
                        "commands": [
                            {"title": "help", "description": "What TBO Copilot can do"},
                            {
                                "title": "what is waiting for me",
                                "description": "Your approvals and fix tasks",
                            },
                        ],
                    }
                ],
            }
        ],
        "permissions": ["identity", "messageTeamMembers"],
        "validDomains": [urlparse(site).hostname],
    }


def app_package() -> bytes:
    import io
    import os
    import zipfile

    folder = os.path.join(os.path.dirname(__file__), "teams_app")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", json.dumps(manifest(), indent=2))
        for icon in ("color.png", "outline.png"):
            package.write(os.path.join(folder, icon), icon)
    return buffer.getvalue()

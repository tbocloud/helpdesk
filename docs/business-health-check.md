# Business Health Check

The TBO website's **Business Health Check** (github.com/tbocloud/Business-Diagnostic) is a guided check-up for business owners. When a client finishes it, the website creates one **Business Health Check** record here with their basic details and **a link to their report**. If the client later leaves a phone number or email ("Call me back"), the website updates the same record.

## The DocType

`Business Health Check`, module Helpdesk. Records are named `BHC-00001`, `BHC-00002`, …

| Field           | Type                  | Notes                                                                                  |
| --------------- | --------------------- | -------------------------------------------------------------------------------------- |
| `business_name` | Data                  | Title. `Unnamed business` when the client left it blank                                |
| `contact_name`  | Data                  |                                                                                        |
| `phone`         | Data (Phone)          | Empty until the client presses "Call me back"                                          |
| `email`         | Data (Email)          | Empty until the client presses "Call me back"                                          |
| `report_link`   | Data (URL), mandatory | `https://<website>/results/#id=123&k=<key>`. The **Open Report** button opens it       |
| `lead`          | Data, read-only       | The ERPNext Lead made with **Create Lead**. The **Open Lead** button opens it in Leads |

The report link carries a secret key, so it only opens that one client's report. A wrong or missing key opens nothing. Text values are trimmed on save.

**Permissions:**

| Role                 | Can                                       |
| -------------------- | ----------------------------------------- |
| System Manager       | everything                                |
| Agent Manager        | read, write, report, export               |
| Agent                | read, report                              |
| **Health Check API** | create, read, write: for the website only |

## Create Lead

A record without a lead shows a **Create Lead** button. It makes an ERPNext **Lead** on the ERP site through Leads (Settings → CRM), as the person who pressed it, just like **New lead** on the Leads page. Only people who can use Leads can press it.

| Lead field     | From                                                                    |
| -------------- | ----------------------------------------------------------------------- |
| `lead_name`    | `contact_name`; the business name when there is no contact name         |
| `company_name` | `business_name` (left empty for `Unnamed business`)                     |
| `mobile_no`    | `phone`                                                                 |
| `email_id`     | `email`                                                                 |
| a note         | `Business Health Check BHC-00001: <report link>` on the lead's timeline |

- **Already a lead?** When another lead has the same phone or email, the ERP site refuses and the form asks **Create a new lead anyway?**. Nothing is made unless the person confirms.
- The lead's name is saved in `lead`, and the button becomes **Open Lead**. One check makes one lead.
- If the note can't be added, the lead is still made, and the form says to add the link by hand.

## Connecting the website (one-time)

1. **Migrate.** `bench --site <site> migrate` creates the DocType, and the patch `setup_health_check_api_role` creates the **Health Check API** role. On a brand-new site, where patches are skipped, run `bench --site <site> execute helpdesk.patches.v16_0_2.setup_health_check_api_role.execute`.
2. **API user.** Create a user (e.g. `health-check-api@<domain>`) with **only** the Health Check API role.
3. **API key.** Open that user → **Settings → API Access → Generate Keys**. Give the site URL, API Key and API Secret to the website team privately.

The website team then sets `CRM_URL`, `CRM_API_KEY`, `CRM_API_SECRET` and `SITE_URL` in the website's `api/config.php`, and runs `php api/cron/check-crm.php`. That checks the URL, the key, the permissions and the five fields the website sends.

## What the website sends

```http
POST /api/resource/Business Health Check
Authorization: token <api_key>:<api_secret>

{"business_name": "Green Leaf Organics", "contact_name": "Ravi Menon", "phone": null, "email": null,
 "report_link": "https://<website>/results/#id=28&k=990e70c5805054b8af6a9f6d"}
```

When the client leaves contact details:

```http
PUT /api/resource/Business Health Check/BHC-00001
Authorization: token <api_key>:<api_secret>

{"phone": "+91 98950 22334", "email": "ravi@greenleaf.in", ...}
```

The website tries once when the client finishes and again on "Call me back". If this site is unreachable, its retry job re-sends every 15 minutes.

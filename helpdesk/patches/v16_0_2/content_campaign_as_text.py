import frappe


def execute():
    """Campaign on a content post is free text now; swap the old campaign IDs for their names."""
    post = frappe.qb.DocType("HD Content Post")
    campaign = frappe.qb.DocType("HD Content Campaign")
    (
        frappe.qb.update(post)
        .join(campaign)
        .on(post.campaign == campaign.name)
        .set(post.campaign, campaign.campaign_name)
        .run()
    )

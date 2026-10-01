import frappe


def execute():
    """Existing posts go out on just their channel."""
    Post = frappe.qb.DocType("HD Content Post")
    (
        frappe.qb.update(Post)
        .set(Post.platforms, Post.channel)
        .where(Post.platforms.isnull() | (Post.platforms == ""))
        .run()
    )

# Copyright (c) 2026, Frappe Technologies and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api import project_files as api
from helpdesk.test_utils import (
    get_reminder_messages,
    hold_commits,
    make_project,
    make_project_file,
    make_project_folder,
    make_tasky_user,
    run_as_user,
)

PM = ("pm.folders@project-folders.example", "Sammish Thundiyil")
DEV_A = ("dev.a.folders@project-folders.example", "Sanika Menon")
DEV_B = ("dev.b.folders@project-folders.example", "Arjun Das")
ADMIN = ("admin.folders@project-folders.example", "Lakshmi Varma")
OUTSIDER = ("outsider.folders@project-folders.example", "Kiran Rao")
PROJECT_NAME = "Project Folders - GrowthX"


class TestProjectFolders(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        make_tasky_user(*PM, roles=("Project Manager",))
        make_tasky_user(*ADMIN, roles=("Agent Manager",))
        for user in (DEV_A, DEV_B, OUTSIDER):
            make_tasky_user(*user)
        self.project = make_project(
            PROJECT_NAME,
            members=[
                (PM[0], "Project Manager"),
                (DEV_A[0], "Developer"),
                (DEV_B[0], "Developer"),
            ],
            owner=PM[0],
        ).name

    def list_as(self, user, **kwargs):
        return run_as_user(
            user[0], lambda: api.list_project_files(self.project, **kwargs)
        )

    def folder_of(self, file):
        return frappe.db.get_value("HD Project File", {"file": file}, "folder")

    def parent_of(self, folder):
        return frappe.db.get_value("HD Project Folder", folder, "parent_folder")

    def record_of(self, file):
        return frappe.db.get_value("HD Project File", {"file": file}, "name")

    def test_folder_names_are_trimmed_and_unique_within_their_parent(self):
        prompts = make_project_folder(self.project, "  Prompts   v2 ", user=PM[0])
        self.assertEqual(
            frappe.db.get_value("HD Project Folder", prompts, "folder_name"),
            "Prompts v2",
        )
        with self.assertRaises(frappe.ValidationError):
            make_project_folder(self.project, "prompts V2", user=DEV_A[0])
        with self.assertRaises(frappe.ValidationError):
            make_project_folder(self.project, "   ", user=PM[0])
        with self.assertRaises(frappe.ValidationError):
            make_project_folder(self.project, "a/b", user=PM[0])

        # the same name is fine in another folder or another project
        make_project_folder(self.project, "Prompts v2", parent_folder=prompts)
        other = make_project(
            "Project Folders - Other", members=[(PM[0], "Project Manager")], owner=PM[0]
        ).name
        make_project_folder(other, "Prompts v2", user=PM[0])

        briefs = make_project_folder(self.project, "Briefs", user=PM[0])
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM[0],
                lambda: api.update_project_folder(self.project, briefs, "Prompts v2"),
            )
        run_as_user(
            PM[0],
            lambda: api.update_project_folder(
                self.project, briefs, "Client briefs", "Signed briefs only"
            ),
        )
        listed = {f["name"]: f for f in self.list_as(DEV_B)["folders"]}
        self.assertEqual(listed[briefs]["folder_name"], "Client briefs")
        self.assertEqual(listed[briefs]["description"], "Signed briefs only")

    def test_folders_nest_up_to_the_depth_limit(self):
        parent = None
        chain = []
        for level in range(1, 6):
            parent = make_project_folder(
                self.project, f"Level {level}", parent_folder=parent
            )
            chain.append(parent)
        with self.assertRaises(frappe.ValidationError):
            make_project_folder(self.project, "Level 6", parent_folder=parent)

        listed = self.list_as(PM, folder=chain[-1])
        self.assertEqual(
            [p["folder_name"] for p in listed["folder"]["path"]],
            [f"Level {n}" for n in range(1, 6)],
        )
        self.assertEqual(listed["folder"]["depth"], 5)

        # a two-level folder can't go under level 4
        top = make_project_folder(self.project, "Archive")
        make_project_folder(self.project, "2025", parent_folder=top)
        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM[0], lambda: api.move_project_folder(self.project, top, chain[3])
            )
        run_as_user(PM[0], lambda: api.move_project_folder(self.project, top, chain[2]))
        self.assertEqual(self.parent_of(top), chain[2])

    def test_a_folder_cannot_move_into_itself_or_below_itself(self):
        clients = make_project_folder(self.project, "Clients", user=PM[0])
        acme = make_project_folder(self.project, "Acme", parent_folder=clients)
        prompts = make_project_folder(self.project, "Prompts", parent_folder=acme)

        for target in (clients, acme, prompts):
            with self.assertRaises(frappe.ValidationError):
                run_as_user(
                    PM[0],
                    lambda: api.move_project_folder(self.project, clients, target),
                )
        self.assertIsNone(self.parent_of(clients))

        file = make_project_file(self.project, user=PM[0], folder=prompts)
        run_as_user(PM[0], lambda: api.move_project_folder(self.project, prompts, None))
        self.assertIsNone(self.parent_of(prompts))
        # the folder takes its files along
        self.assertEqual(self.folder_of(file), prompts)

    def test_folder_assignees_are_notified_once(self):
        folder = make_project_folder(
            self.project, "Prompts", for_users=[DEV_A[0], PM[0]], user=PM[0]
        )
        messages = get_reminder_messages(DEV_A[0], folder)
        self.assertEqual(len(messages), 1)
        self.assertIn("Sammish Thundiyil shared folder 'Prompts'", messages[0])
        self.assertIn(PROJECT_NAME, messages[0])
        # the person sharing isn't told about their own folder
        self.assertEqual(get_reminder_messages(PM[0], folder), [])
        link = frappe.db.get_value(
            "HD Notification", {"user_to": DEV_A[0], "reference_name": folder}, "link"
        )
        self.assertEqual(link, f"/projects/{self.project}/files?folder={folder}")

        run_as_user(
            PM[0],
            lambda: api.set_project_folder_for(
                self.project, folder, [PM[0], DEV_A[0], DEV_B[0]]
            ),
        )
        self.assertEqual(len(get_reminder_messages(DEV_A[0], folder)), 1)
        self.assertEqual(len(get_reminder_messages(DEV_B[0], folder)), 1)

        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                PM[0],
                lambda: api.set_project_folder_for(self.project, folder, [OUTSIDER[0]]),
            )

    def test_an_upload_notifies_each_person_once_across_ancestors(self):
        clients = make_project_folder(
            self.project, "Clients", for_users=[DEV_B[0]], user=PM[0]
        )
        acme = make_project_folder(
            self.project,
            "Acme",
            for_users=[DEV_B[0], DEV_A[0]],
            user=PM[0],
            parent_folder=clients,
        )
        files = [
            make_project_file(self.project, n, b"x", user=DEV_A[0], folder=f)
            for n, f in (
                ("one.md", acme),
                ("two.md", acme),
                ("three.md", acme),
                ("brief.md", clients),
            )
        ]
        run_as_user(DEV_A[0], lambda: api.notify_folder_upload(self.project, files))

        first = self.record_of(files[0])
        messages = get_reminder_messages(DEV_B[0], first)
        self.assertEqual(len(messages), 1)
        self.assertIn("added 4 files to folder 'Clients'", messages[0])
        self.assertEqual(
            frappe.db.count("HD Notification", {"user_to": DEV_B[0]}), 3
        )  # shared Clients, shared Acme, the upload
        # the uploader isn't told about their own upload
        self.assertEqual(get_reminder_messages(DEV_A[0], first), [])
        # announcing the same batch again doesn't repeat it
        run_as_user(DEV_A[0], lambda: api.notify_folder_upload(self.project, files))
        self.assertEqual(len(get_reminder_messages(DEV_B[0], first)), 1)

        # PM (not on either list) uploads one file deep down: Sanika hears via Acme
        deep = make_project_file(self.project, "deep.md", b"d", user=PM[0], folder=acme)
        run_as_user(PM[0], lambda: api.notify_folder_upload(self.project, [deep]))
        message = get_reminder_messages(DEV_A[0], self.record_of(deep))
        self.assertEqual(len(message), 1)
        self.assertIn("added deep.md to folder 'Acme'", message[0])

        # someone else's files can't be announced
        other = make_project_file(
            self.project, "four.md", b"x", user=PM[0], folder=acme
        )
        run_as_user(DEV_A[0], lambda: api.notify_folder_upload(self.project, [other]))
        self.assertEqual(get_reminder_messages(DEV_B[0], self.record_of(other)), [])

    def test_people_the_file_is_for_are_not_told_twice(self):
        folder = make_project_folder(
            self.project, "Prompts", for_users=[DEV_B[0]], user=PM[0]
        )
        file = make_project_file(
            self.project, for_users=[DEV_B[0]], user=PM[0], folder=folder
        )
        run_as_user(PM[0], lambda: api.notify_folder_upload(self.project, [file]))
        messages = get_reminder_messages(DEV_B[0], self.record_of(file))
        self.assertEqual(len(messages), 1)
        self.assertIn("shared master-prompt.md with you", messages[0])

    def test_folder_upload_recreates_the_structure(self):
        current = make_project_folder(self.project, "Handover", user=DEV_A[0])
        clients = make_project_folder(
            self.project, "Clients", user=PM[0], parent_folder=current
        )
        made = run_as_user(
            DEV_A[0],
            lambda: api.create_folder_paths(
                self.project,
                ["Clients/Acme", "Clients/Acme/Prompts", "Notes", "clients/acme"],
                current,
            ),
        )
        acme = made["Clients/Acme"]
        self.assertEqual(self.parent_of(acme), clients)
        self.assertEqual(made["clients/acme"], acme)
        self.assertEqual(self.parent_of(made["Clients/Acme/Prompts"]), acme)
        self.assertEqual(self.parent_of(made["Notes"]), current)
        self.assertEqual(
            frappe.db.count("HD Project Folder", {"project": self.project}), 5
        )

        # running it again makes nothing new
        again = run_as_user(
            DEV_A[0],
            lambda: api.create_folder_paths(
                self.project, ["Clients/Acme/Prompts"], current
            ),
        )
        self.assertEqual(again["Clients/Acme/Prompts"], made["Clients/Acme/Prompts"])
        self.assertEqual(
            frappe.db.count("HD Project Folder", {"project": self.project}), 5
        )

        with self.assertRaises(frappe.ValidationError):
            run_as_user(
                DEV_A[0],
                lambda: api.create_folder_paths(
                    self.project, [f"Bulk/{n}" for n in range(201)]
                ),
            )
        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                OUTSIDER[0],
                lambda: api.create_folder_paths(self.project, ["Mine"]),
            )

    def test_move_file_between_folders_and_to_the_top_level(self):
        prompts = make_project_folder(
            self.project, "Prompts", for_users=[DEV_B[0]], user=PM[0]
        )
        briefs = make_project_folder(self.project, "Briefs", user=PM[0])
        file = make_project_file(self.project, user=DEV_A[0])

        with self.assertRaises(frappe.PermissionError):
            run_as_user(
                DEV_B[0], lambda: api.move_project_file(self.project, file, prompts)
            )
        run_as_user(
            DEV_A[0], lambda: api.move_project_file(self.project, file, prompts)
        )
        self.assertEqual(self.folder_of(file), prompts)
        self.assertEqual(len(get_reminder_messages(DEV_B[0], self.record_of(file))), 1)

        run_as_user(PM[0], lambda: api.move_project_file(self.project, file, briefs))
        run_as_user(PM[0], lambda: api.move_project_file(self.project, file, None))
        self.assertIsNone(self.folder_of(file))

        other = make_project(
            "Project Folders - Elsewhere",
            members=[(PM[0], "Project Manager")],
            owner=PM[0],
        ).name
        stray = make_project_folder(other, "Stray", user=PM[0])
        with self.assertRaises(frappe.PermissionError):
            run_as_user(PM[0], lambda: api.move_project_file(self.project, file, stray))
        with self.assertRaises(frappe.PermissionError):
            make_project_file(self.project, user=PM[0], folder=stray)
        with self.assertRaises(frappe.PermissionError):
            make_project_folder(self.project, "Inside", parent_folder=stray)

    def test_deleting_a_folder_moves_its_contents_up(self):
        clients = make_project_folder(self.project, "Clients", user=DEV_A[0])
        acme = make_project_folder(
            self.project, "Acme", user=DEV_A[0], parent_folder=clients
        )
        inner = make_project_folder(self.project, "Prompts", parent_folder=acme)
        files = [
            make_project_file(self.project, n, b"x", user=DEV_A[0], folder=acme)
            for n in ("a.md", "b.md")
        ]
        listed = {f["name"]: f for f in self.list_as(PM)["folders"]}
        self.assertEqual(listed[acme]["file_count"], 2)
        self.assertEqual(listed[acme]["folder_count"], 1)

        with self.assertRaises(frappe.PermissionError):
            run_as_user(DEV_B[0], lambda: api.delete_project_folder(self.project, acme))
        run_as_user(DEV_A[0], lambda: api.delete_project_folder(self.project, acme))

        self.assertFalse(frappe.db.exists("HD Project Folder", acme))
        self.assertEqual(self.parent_of(inner), clients)
        for file in files:
            self.assertEqual(self.folder_of(file), clients)

        # a subfolder whose name is taken one level up stops the delete
        make_project_folder(self.project, "Prompts")
        with self.assertRaises(frappe.ValidationError):
            run_as_user(PM[0], lambda: api.delete_project_folder(self.project, clients))
        self.assertTrue(frappe.db.exists("HD Project Folder", clients))

    def test_permission_matrix(self):
        folder = make_project_folder(self.project, "Prompts", user=DEV_A[0])
        target = make_project_folder(self.project, "Archive", user=PM[0])

        # outsiders can't see or touch folders
        for call in (
            lambda: api.list_project_files(self.project, folder=folder),
            lambda: api.create_project_folder(self.project, "Mine"),
            lambda: api.update_project_folder(self.project, folder, "Renamed"),
            lambda: api.move_project_folder(self.project, folder, target),
            lambda: api.set_project_folder_for(self.project, folder, []),
            lambda: api.delete_project_folder(self.project, folder),
            lambda: api.notify_folder_upload(self.project, []),
        ):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(OUTSIDER[0], call)
        with self.assertRaises(frappe.PermissionError):
            make_project_file(self.project, user=OUTSIDER[0], folder=folder)

        # another member reads, makes folders and uploads, but can't change this one
        listed = self.list_as(DEV_B, folder=folder)
        self.assertEqual(listed["folder"]["folder_name"], "Prompts")
        self.assertFalse(listed["folder"]["can_change"])
        make_project_folder(
            self.project, "Designs", user=DEV_B[0], parent_folder=folder
        )
        make_project_file(self.project, user=DEV_B[0], folder=folder)
        for call in (
            lambda: api.update_project_folder(self.project, folder, "Renamed"),
            lambda: api.move_project_folder(self.project, folder, target),
            lambda: api.set_project_folder_for(self.project, folder, [DEV_B[0]]),
            lambda: api.delete_project_folder(self.project, folder),
        ):
            with self.assertRaises(frappe.PermissionError):
                run_as_user(DEV_B[0], call)

        # the creator, the project's manager and an admin can
        self.assertTrue(self.list_as(DEV_A, folder=folder)["folder"]["can_change"])
        run_as_user(
            DEV_A[0], lambda: api.update_project_folder(self.project, folder, "Ours")
        )
        run_as_user(
            PM[0], lambda: api.move_project_folder(self.project, folder, target)
        )
        run_as_user(
            PM[0],
            lambda: api.set_project_folder_for(self.project, folder, [DEV_B[0]]),
        )
        self.assertTrue(self.list_as(ADMIN, folder=folder)["folder"]["can_change"])
        run_as_user(ADMIN[0], lambda: api.delete_project_folder(self.project, folder))
        self.assertFalse(frappe.db.exists("HD Project Folder", folder))

    def test_for_me_includes_files_in_folders_for_me_and_below(self):
        shared = make_project_folder(
            self.project, "Prompts", for_users=[DEV_A[0]], user=PM[0]
        )
        below = make_project_folder(self.project, "Drafts", parent_folder=shared)
        in_shared = make_project_file(self.project, "in-shared.md", b"s", folder=shared)
        in_below = make_project_file(self.project, "in-below.md", b"b", folder=below)
        for_a = make_project_file(
            self.project, "for-a.md", b"a", for_users=[DEV_A[0]], user=PM[0]
        )
        make_project_file(self.project, "for-nobody.md", b"n", user=PM[0])

        listed = self.list_as(DEV_A, for_me=True)
        mine = {f["name"]: f for f in listed["files"]}
        self.assertEqual(set(mine), {in_shared, in_below, for_a})
        self.assertTrue(mine[in_below]["shared_via_folder"])
        self.assertFalse(mine[in_below]["is_for_me"])
        self.assertEqual(
            [p["folder_name"] for p in mine[in_below]["folder_path"]],
            ["Prompts", "Drafts"],
        )
        self.assertTrue(mine[for_a]["is_for_me"])
        self.assertFalse(mine[for_a]["shared_via_folder"])
        folders = {f["name"]: f for f in listed["folders"]}
        self.assertTrue(folders[shared]["is_for_me"])
        self.assertFalse(folders[below]["is_for_me"])
        self.assertTrue(folders[below]["for_me_via_parent"])

        self.assertEqual(self.list_as(DEV_B, for_me=True)["files"], [])
        root = self.list_as(DEV_B)
        self.assertEqual(len(root["files"]), 2)
        self.assertEqual(root["total"], 4)
        self.assertEqual(
            [f["name"] for f in self.list_as(DEV_B, folder=shared)["files"]],
            [in_shared],
        )

    def test_deleting_the_project_deletes_its_folders(self):
        top = make_project_folder(self.project, "Prompts", user=PM[0])
        inner = make_project_folder(self.project, "Prompts", parent_folder=top)
        make_project_folder(self.project, "Prompts", parent_folder=inner)
        make_project_file(self.project, user=PM[0], folder=inner)
        frappe.delete_doc("Project", self.project, ignore_permissions=True, force=True)
        self.assertEqual(
            frappe.db.count("HD Project Folder", {"project": self.project}), 0
        )

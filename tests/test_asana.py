from unittest.mock import MagicMock, patch

from ntimporters.asana import importer


def test_list_endpoints_carry_fields_no_per_record_gets():
    sdk = MagicMock()
    sdk.WorkspacesApi().get_workspaces.return_value = [{"gid": "w"}]
    sdk.UsersApi().get_users.return_value = []
    sdk.UsersApi().get_user.return_value = {"gid": "me"}
    sdk.ProjectsApi().get_projects_for_workspace.return_value = [{"gid": "p", "name": "P"}]
    sdk.SectionsApi().get_sections_for_project.return_value = [{"gid": "s", "name": "S"}]
    sdk.TagsApi().get_tags_for_workspace.return_value = []
    task = {"gid": "t", "name": "T", "memberships": [{"section": {"gid": "s"}}], "num_subtasks": 0}
    loose = [{"gid": "l1", "name": "L1", "projects": [{"gid": "p"}]}, {"gid": "l2", "name": "L2"}]
    sdk.TasksApi().get_tasks_for_project.return_value = [task]
    sdk.TasksApi().get_tasks.return_value = loose
    sdk.StoriesApi().get_stories_for_task.return_value = []
    sdk.AttachmentsApi().get_attachments_for_object.return_value = []
    nz = MagicMock()
    nz.project.return_value = "np"
    nz.section.return_value = "ns"
    nz.task.return_value = ("nt", True)
    with patch.object(importer, "asana", sdk):
        importer._import_data(nz, MagicMock())

    for api, method in (
        ("ProjectsApi", "get_project"),
        ("SectionsApi", "get_section"),
        ("TagsApi", "get_tag"),
        ("TasksApi", "get_task"),
        ("TasksApi", "get_subtasks_for_task"),
    ):
        getattr(getattr(sdk, api)(), method).assert_not_called()
    sdk.TasksApi().get_tasks_for_project.assert_called_once_with(
        "p", {"opt_fields": importer.TASK_FIELDS}
    )
    assert [(call.args[1], call.kwargs.get("section_id")) for call in nz.task.call_args_list] == [
        ("T", "ns"),
        ("L2", None),
    ]

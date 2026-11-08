from qsone.projects import ProjectIn, Projects
from qsone.records import audit, files
from qsone.records.mapping import facts
from tests.samples import sample_pdf


def test_create_without_name_and_folder(data_dir):
    projects = Projects(data_dir)
    try:
        body = ProjectIn.model_validate({})
        loose = projects.create(body.name, "engineer")
        assert loose["name_pair"]["en"].startswith("Project ")
        folder = projects.create(None, "engineer", folder="Sample tender")
        assert folder["name"] == "Sample tender"
    finally:
        projects.close_all()


def test_tender_name_source_and_engineer_override(rec):
    f = files.add_file(
        rec, "sample.pdf", sample_pdf([["Project name: Sample hospital"]]), actor="engineer"
    )
    with rec.write("engineer") as c:
        rec.set_meta(c, "name_origin", "folder")
    proposal = dict(
        name={"en": "Project name", "ar": "اسم المشروع"},
        value="Sample hospital",
        file_id=f.id,
        locator={"page": 1},
        state="found",
        evidence="Project name: Sample hospital",
    )
    facts.accept(rec, [proposal], picture_fallback=False)
    assert rec.meta()["name"] == "Sample hospital"
    import json

    source = json.loads(rec.meta()["name_source"])
    assert source["file_id"] == f.id and source["locator"] == {"page": 1}
    with rec.read() as c:
        assert audit.history(c, "name")[-1]["actor"] == "one"
    from qsone.records.naming import rename

    rename(rec, "My sample project", actor="engineer")
    facts.accept(rec, [proposal], picture_fallback=False)
    assert rec.meta()["name"] == "My sample project"
    assert rec.meta()["name_origin"] == "engineer"


def test_corrected_tender_name_is_kept_as_engineer_name(rec):
    f = files.add_file(
        rec, "sample.pdf", sample_pdf([["Project name: Sample hospital"]]), actor="engineer"
    )
    with rec.write("engineer") as c:
        rec.set_meta(c, "name_origin", "folder")
    ids = facts.accept(
        rec,
        [
            dict(
                name={"en": "Project name", "ar": "اسم المشروع"},
                value="Sample hospital",
                file_id=f.id,
                locator={"page": 1},
                state="found",
                evidence="Project name: Sample hospital",
            )
        ],
        picture_fallback=False,
    )
    facts.update(rec, ids[0], value="Engineer sample")
    assert rec.meta()["name"] == "Engineer sample"
    assert rec.meta()["name_origin"] == "engineer"


def test_reopening_an_open_project_returns_latest_name(data_dir):
    from qsone.records.naming import rename

    projects = Projects(data_dir)
    try:
        made = projects.create(None, "engineer", folder="Folder sample")
        rename(projects.get(made["id"]), "Engineer sample", actor="engineer")
        assert projects.open(made["id"])["name"] == "Engineer sample"
    finally:
        projects.close_all()

"""The pre-contract CLI scenarios use local sample files and scripted tools only."""

from tests.bench import fake, samples


def test_precontract_sample_scripts(tmp_path):
    required = {
        "pricing",
        "letter",
        "pack",
        "estimate",
        "conditions",
        "oldoffice",
        "pdfboq",
        "scanned",
        "market",
        "revise",
        "summary",
    }
    assert required <= set(fake.SCENARIOS)
    samples.write(tmp_path)
    for name in (
        "sample-boq.pdf",
        "sample-boq.xls",
        "sample-conditions.pdf",
        "sample-market.csv",
        "sample-scan.pdf",
        "sample-estimate.xlsx",
    ):
        assert (tmp_path / name).stat().st_size > 0


def test_all_scripted_precontract_walks(running, tmp_path):  # noqa: F811
    from tests.test_cli import CORE, cli

    session, _ = running
    result = cli(
        session,
        "walk",
        "--all",
        CORE / "tests/walks",
        "--scripted-only",
        "--report",
        tmp_path / "walks.json",
    )
    assert result["status"] == "PASS"
    assert len(result["walks"]) == 12
    assert all(w["status"] == "PASS" for w in result["walks"])
    assert all(s["status"] == "PASS" for w in result["walks"] for s in w["steps"])


from tests.test_cli import running  # noqa: E402,F401,F811 -- reuse the isolated started-core fixture

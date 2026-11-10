use crate::digest::{digest, push};
use crate::emit::emit;
use crate::{read, read_with, run};
use acadrust::entities::{
    AttributeDefinition, Dimension, DimensionAligned, Insert, MText, MultiLeader, Table, Text,
    Tolerance,
};
use acadrust::tables::BlockRecord;
use acadrust::types::Vector3;
use acadrust::{CadDocument, DwgWriter, EntityType};
use serde_json::json;

const PLAN: &[u8] = include_bytes!("../../core/tests/fixtures/drawings/test-plan.dwg");

#[test]
fn paper_grid_lines_are_positioned() {
    let doc = CadDocument::new();
    let mut line = acadrust::entities::Line::new();
    line.end = Vector3::new(10.0, 20.0, 0.0);
    let mut out = digest(&doc, "dxf");
    emit(
        &doc,
        &EntityType::Line(line),
        "Layout1",
        None,
        "",
        &mut out,
        0,
    );
    assert_eq!(out["segments"][0]["end"], json!([10.0, 20.0]));
}

#[test]
fn geometry_budget_never_starves_text_or_caps_the_reading() {
    let mut out =
        json!({"hatches":[],"closed":[],"texts":[],"totals":{},"byte_counts":{},"output_bytes":0});
    for _ in 0..20 {
        push(&mut out, "hatches", json!({"loops":"x".repeat(100000)}));
    }
    for _ in 0..200 {
        push(&mut out, "closed", json!({"vertices":"x".repeat(100000)}));
    }
    for _ in 0..300 {
        push(&mut out, "texts", json!({"text":"a".repeat(100000)}));
    }
    assert_eq!(out["texts"].as_array().unwrap().len(), 300);
    assert_eq!(out["limited_geometry"], true);
    assert!(out["limited"].is_null());
}

#[test]
fn styles_and_table_cells_are_evidence() {
    let mut doc = CadDocument::new();
    let mut style = acadrust::tables::TextStyle::new("SampleArabic");
    style.font_file = "arabic.shx".into();
    doc.text_styles.add(style).unwrap();
    let mut t = Text::new();
    t.value = "synthetic".into();
    t.style = "SampleArabic".into();
    doc.add_entity(EntityType::Text(t)).unwrap();
    let mut table = Table::new(Vector3::new(10.0, 20.0, 0.0), 1, 1);
    table.set_cell_text(0, 0, "SAMPLE CELL");
    doc.add_entity(EntityType::Table(Box::new(table))).unwrap();
    let out = digest(&doc, "dxf");
    assert_eq!(out["texts"][0]["font_file"], "arabic.shx");
    assert_eq!(out["texts"][0]["raw_text"], "synthetic");
    assert!(out["texts"]
        .as_array()
        .unwrap()
        .iter()
        .any(|r| r["text"] == "SAMPLE CELL" && r["table_cell"] == json!([0, 0])));
    assert_eq!(out["tables"][0]["rows"], 1);
}

#[test]
fn curved_closed_outline_is_preserved() {
    use acadrust::entities::{LwPolyline, LwVertex};
    use acadrust::types::Vector2;
    let mut doc = CadDocument::new();
    let mut p = LwPolyline::new();
    p.add_vertex(LwVertex::with_bulge(Vector2::new(0.0, 0.0), 1.0));
    p.add_vertex(LwVertex::new(Vector2::new(2.0, 0.0)));
    p.close();
    doc.add_entity(EntityType::LwPolyline(p)).unwrap();
    let out = digest(&doc, "dxf");
    assert_eq!(out["closed"].as_array().unwrap().len(), 1);
    assert!((out["closed"][0]["area"].as_f64().unwrap() - std::f64::consts::PI / 2.0).abs() < 1e-8);
}

#[test]
fn binary_dxf_is_read_from_bytes() {
    let doc = acadrust::io::dxf::DxfReader::from_reader(std::io::Cursor::new(
        include_bytes!("../../core/tests/fixtures/drawings/title.dxf").to_vec(),
    ))
    .unwrap()
    .read()
    .unwrap();
    let data = acadrust::io::dxf::DxfWriter::new_binary(&doc)
        .write_to_vec()
        .unwrap();
    let (out, _) = read("binary.dxf", data).unwrap();
    assert_eq!(out["inserts"][0]["attributes"][0]["value"], "A-101");
}

#[test]
fn output_has_a_byte_budget() {
    let mut out = json!({"texts":[],"totals":{},"byte_counts":{},"output_bytes":0});
    for _ in 0..10000 {
        push(&mut out, "texts", json!({"text":"a".repeat(8192)}));
    }
    assert!(serde_json::to_vec(&out).unwrap().len() < 57 * 1024 * 1024);
    assert_eq!(out["totals"]["texts"], 10000);
    assert_eq!(out["limited"], true);
}

#[test]
fn title_layout_and_attributes() {
    for bytes in [
        include_bytes!("../../core/tests/fixtures/drawings/title.dxf").as_slice(),
        include_bytes!("../../core/tests/fixtures/drawings/arabic.dxf").as_slice(),
    ] {
        let (out, _) = read("sample.dxf", bytes.to_vec()).unwrap();
        assert!(out["inserts"]
            .as_array()
            .unwrap()
            .iter()
            .any(|i| !i["attributes"].as_array().unwrap().is_empty()));
        assert!(!out["closed"].as_array().unwrap().is_empty());
        assert!(out["layouts"]
            .as_array()
            .unwrap()
            .iter()
            .any(|l| l["name"] == "Layout1"));
    }
}

#[test]
fn damaged_is_reported() {
    let data = include_bytes!("../../core/tests/fixtures/drawings/damaged.dxf").to_vec();
    let (out, code) = run("damaged.dxf", data);
    if code == 1 {
        assert_eq!(out["reason"], "damaged");
    } else {
        assert_eq!(code, 2);
        assert!(!out["problems"].as_array().unwrap().is_empty());
    }
}

#[test]
fn sample_dwg() {
    let (out, _) = read("test-plan.dwg", PLAN.to_vec()).unwrap();
    let inserts = out["inserts"].as_array().unwrap();
    for (name, count) in [("DOOR", 3), ("WINDOW", 5), ("COLUMN", 6)] {
        assert_eq!(inserts.iter().filter(|v| v["block"] == name).count(), count);
    }
    let texts = out["texts"].as_array().unwrap();
    assert!(texts
        .iter()
        .any(|v| v["text"].as_str().unwrap().contains("LIVING")));
    assert!(out["stats"]["decoded"].as_u64().unwrap() > 0);
    assert!(out["layers"][0]["entities"].is_u64());
}

#[test]
fn unreadable_says_why() {
    let zeros = |head: &[u8]| [head, &[0u8; 64][..]].concat();
    for (name, data, reason, version) in [
        ("a.dwg", zeros(b"AC1032"), "damaged", "AC1032"),
        ("a.dwg", zeros(b"AC1006"), "unsupported-version", "AC1006"),
        ("a.dwg", b"%PDF-1.7 sample".to_vec(), "not-a-dwg", ""),
        ("a.dwg", vec![b'A'], "not-a-dwg", ""),
        (
            "a.dwg",
            PLAN[..PLAN.len() / 2].to_vec(),
            "damaged",
            "AC1032",
        ),
    ] {
        let (out, code) = run(name, data);
        assert_eq!(
            (code, out["reason"].as_str(), out["file_version"].as_str()),
            (1, Some(reason), Some(version)),
            "{out}"
        );
    }
}

#[test]
fn too_large_is_named() {
    let message = read_with("test-plan.dwg", PLAN.to_vec(), 1024).unwrap_err();
    assert_eq!(
        crate::reason("test-plan.dwg", "AC1032", &message),
        "too-large",
        "{message}"
    );
}

fn sample_document() -> CadDocument {
    let mut doc = CadDocument::new();
    let mut t = Text::new();
    t.value = "5%%c12 @ 200 c\\c {hl,".into(); // sample only
    doc.add_entity(EntityType::Text(t)).unwrap();
    let mut m = MText::new();
    m.value = "{\\fArial;غرفة نوم}\\Pمساحة 12.50 م2 - عينة".into();
    doc.add_entity(EntityType::MText(Box::new(m))).unwrap();
    let mut table = Table::new(Vector3::new(0.0, 0.0, 0.0), 2, 2);
    table.set_cell_text(0, 0, "البند - عينة");
    table.set_cell_text(1, 1, "12.50");
    doc.add_entity(EntityType::Table(Box::new(table))).unwrap();
    let dim = DimensionAligned::new(Vector3::new(0.0, 0.0, 0.0), Vector3::new(4.0, 3.0, 0.0));
    let mut dim = Dimension::Aligned(dim);
    dim.base_mut().text = "<> م".into();
    doc.add_entity(EntityType::Dimension(Box::new(dim)))
        .unwrap();
    let leader = MultiLeader::with_text("عمود C1 - عينة", Vector3::new(5.0, 5.0, 0.0), vec![]);
    doc.add_entity(EntityType::MultiLeader(Box::new(leader)))
        .unwrap();
    let tolerance = Tolerance::with_text(Vector3::new(1.0, 1.0, 0.0), "{\\Fgdt;j}%%v0.05");
    doc.add_entity(EntityType::Tolerance(tolerance)).unwrap();
    let mut record = BlockRecord::new("SAMPLE_TAG");
    record.handle = doc.allocate_handle();
    let owner = record.handle;
    doc.block_records.add(record).unwrap();
    let mut constant =
        AttributeDefinition::new("ROOM".into(), "".into(), "R-01".into()).with_constant();
    constant.common.owner_handle = owner;
    doc.add_entity(EntityType::AttributeDefinition(constant))
        .unwrap();
    doc.add_entity(EntityType::Insert(Insert::new(
        "SAMPLE_TAG",
        Vector3::new(9.0, 9.0, 0.0),
    )))
    .unwrap();
    doc
}

#[test]
fn dwg_reads_texts_tables_dimensions_leaders_and_constants() {
    let data = DwgWriter::write_to_vec(&sample_document()).unwrap();
    let (out, _) = read("sample.dwg", data).unwrap();
    let texts = out["texts"].as_array().unwrap();
    let kind = |k: &str| texts.iter().filter(|r| r["kind"] == k).collect::<Vec<_>>();
    assert_eq!(kind("TEXT")[0]["text"], "5Ø12 @ 200 c\\c {hl,");
    assert!(kind("MTEXT")[0]["text"]
        .as_str()
        .unwrap()
        .contains("غرفة نوم"));
    assert_eq!(kind("MLEADER")[0]["text"], "عمود C1 - عينة");
    assert_eq!(kind("TOLERANCE").len(), 1);
    assert_eq!(kind("CONSTANT_ATTRIBUTE")[0]["text"], "R-01");
    let cells: Vec<_> = kind("TABLE")
        .iter()
        .map(|r| r["table_cell"].clone())
        .collect();
    assert_eq!(cells, vec![json!([0, 0]), json!([1, 1])]);
    assert_eq!(
        (
            out["tables"][0]["rows"].as_u64(),
            out["tables"][0]["columns"].as_u64()
        ),
        (Some(2), Some(2))
    );
    let dim = &out["dimensions"][0];
    assert!((dim["measured"].as_f64().unwrap() - 5.0).abs() < 1e-9);
    assert_eq!(dim["text"], "<> م");
    let block = out["blocks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|b| b["name"] == "SAMPLE_TAG")
        .unwrap();
    assert_eq!(block["attdefs"][0]["constant"], true);
}

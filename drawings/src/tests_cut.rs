//! What the reader cuts is counted, never dropped in silence: long texts, attributes past 256,
//! table rows past 4096 and columns past 1024.

use crate::digest::digest;
use crate::emit::emit;
use acadrust::entities::{AttributeEntity, Insert, MText, Table, Text};
use acadrust::types::Vector3;
use acadrust::{CadDocument, EntityType};

fn not_kept(out: &serde_json::Value) -> u64 {
    out["totals"]["texts"].as_u64().unwrap_or(0) - out["texts"].as_array().unwrap().len() as u64
}

#[test]
fn a_long_text_cut_short_is_counted() {
    let mut doc = CadDocument::new();
    let mut m = MText::new();
    m.value = format!("{}FINAL CLAUSE 99 - sample", "a".repeat(9000));
    doc.add_entity(EntityType::MText(Box::new(m))).unwrap();
    let mut t = Text::new();
    t.value = "short - sample".into();
    doc.add_entity(EntityType::Text(t)).unwrap();
    let out = digest(&doc, "dxf");
    assert_eq!(out["cut_texts"], 1);
    assert_eq!(out["limited"], true);
}

#[test]
fn attributes_past_256_are_texts_not_kept() {
    let doc = CadDocument::new();
    let mut insert = Insert::new("SAMPLE_TAGS", Vector3::new(0.0, 0.0, 0.0));
    for n in 0..300 {
        insert
            .attributes
            .push(AttributeEntity::new(format!("T{n}"), format!("V{n}")));
    }
    let mut out = digest(&doc, "dxf");
    emit(
        &doc,
        &EntityType::Insert(insert),
        "Model",
        None,
        "",
        &mut out,
        0,
    );
    assert_eq!(not_kept(&out), 44);
    assert_eq!(out["limited"], true);
}

#[test]
fn table_rows_and_columns_past_the_limit_are_texts_not_kept() {
    let doc = CadDocument::new();
    let mut tall = Table::new(Vector3::new(0.0, 0.0, 0.0), 4100, 1);
    for r in 4095..4100 {
        tall.set_cell_text(r, 0, "D7 - sample");
    }
    let mut wide = Table::new(Vector3::new(0.0, 0.0, 0.0), 1, 1030);
    wide.set_cell_text(0, 1027, "4 - sample");
    let mut out = digest(&doc, "dxf");
    for t in [tall, wide] {
        emit(
            &doc,
            &EntityType::Table(Box::new(t)),
            "Model",
            None,
            "",
            &mut out,
            0,
        );
    }
    assert_eq!(out["texts"].as_array().unwrap().len(), 1);
    assert_eq!(not_kept(&out), 5);
    assert_eq!(out["limited"], true);
}

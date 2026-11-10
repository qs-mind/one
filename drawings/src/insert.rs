//! A placed block (INSERT): its row, its attributes as texts, and the entities of its block,
//! placed where the insert puts them, eight blocks deep at most.

use crate::digest::{push, skip_texts, LIMIT};
use crate::emit::emit;
use crate::text::{long, place, raw, single, text_style};
use acadrust::{CadDocument, EntityType};
use serde_json::{json, Value};

#[allow(clippy::too_many_arguments)]
pub fn insert(
    doc: &CadDocument,
    i: &acadrust::entities::Insert,
    c: &acadrust::entities::EntityCommon,
    layout: &str,
    block: Option<&str>,
    context: &str,
    out: &mut Value,
    depth: usize,
    mut row: Value,
) {
    let past = i
        .attributes
        .iter()
        .skip(256)
        .filter(|a| !a.value.is_empty());
    skip_texts(out, past.count() as u64);
    if depth >= 8 {
        out["traversal_limited"] = json!(true);
        out["limited"] = json!(true);
    }
    let parent = doc
        .dynamic_definition_for_insert(c.handle)
        .and_then(|h| doc.block_records.iter().find(|b| b.handle == h))
        .map(|b| b.name.as_str())
        .unwrap_or(&i.block_name);
    row["block"] = json!(parent);
    row["effective_name"] = json!(parent);
    row["instance"] = json!(format!("{}:{:X}", layout, c.handle.value()));
    if block.is_some() {
        row["container"] = json!(block);
    }
    place(&mut row, i.insert_point.x, i.insert_point.y);
    row["scale"] = json!([i.x_scale(), i.y_scale(), i.z_scale()]);
    row["rotation"] = json!(i.rotation);
    row["attributes"] = json!(i.attributes.iter().take(256).map(|a| json!({"tag":a.tag,"value":single(&a.value),"handle":format!("{:X}",a.common.handle.value()),"x":a.insertion_point.x,"y":a.insertion_point.y})).collect::<Vec<_>>());
    for a in i.attributes.iter().take(256) {
        if !a.value.is_empty() {
            long(out, &a.value);
            let mut attr = row.clone();
            attr.as_object_mut().unwrap().remove("attributes");
            attr["kind"] = json!("ATTRIBUTE");
            attr["text"] = json!(single(&a.value));
            attr["raw_text"] = json!(raw(&a.value));
            attr["handle"] = json!(format!("{:X}", a.common.handle.value()));
            place(&mut attr, a.insertion_point.x, a.insertion_point.y);
            attr["height"] = json!(a.height);
            text_style(doc, &a.text_style, &mut attr);
            push(out, "texts", attr);
        }
    }
    let base = doc.block_records.iter().find(|b| b.name == i.block_name);
    let placed = |child: &EntityType| {
        let mut placed = child.clone();
        if let Some(b) = base {
            placed
                .as_entity_mut()
                .apply_transform(&acadrust::types::Transform::from_translation(-b.base_point));
        }
        placed.as_entity_mut().apply_transform(&i.get_transform());
        placed
    };
    if depth == 0 {
        let mut bounds = [
            f64::INFINITY,
            f64::INFINITY,
            f64::NEG_INFINITY,
            f64::NEG_INFINITY,
        ];
        for child in doc.entities_in_block(&i.block_name).take(LIMIT) {
            let b = placed(child).as_entity().bounding_box();
            if [b.min.x, b.min.y, b.max.x, b.max.y]
                .iter()
                .all(|v| v.is_finite())
            {
                bounds[0] = bounds[0].min(b.min.x);
                bounds[1] = bounds[1].min(b.min.y);
                bounds[2] = bounds[2].max(b.max.x);
                bounds[3] = bounds[3].max(b.max.y);
            }
        }
        if bounds.iter().all(|v| v.is_finite()) {
            row["bounds"] = json!(bounds);
        }
    }
    push(out, "inserts", row);
    if depth < 8 && out["totals"]["texts"].as_u64().unwrap_or(0) < 100_000 {
        for child in doc.entities_in_block(&i.block_name).take(LIMIT) {
            let ctx = format!("{}/{}:{:X}", context, parent, c.handle.value());
            emit(
                doc,
                &placed(child),
                layout,
                Some(parent),
                &ctx,
                out,
                depth + 1,
            );
        }
    }
}

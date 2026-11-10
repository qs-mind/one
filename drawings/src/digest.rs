//! A read document as one JSON object: header facts, tables of the drawing and each placed
//! entity (`emit`). Output budgets keep text first: take-off geometry (outlines, hatches,
//! segments) only fills what is left below 16 MiB and never marks the reading as capped.

use crate::emit::emit;
use acadrust::objects::ObjectType;
use acadrust::{CadDocument, EntityType};
use serde_json::{json, Value};
use std::collections::HashMap;

pub const LIMIT: usize = 100_000;
const MIB: u64 = 1024 * 1024;
const GEOMETRY: [&str; 3] = ["closed", "hatches", "segments"];
// Kinds whose content ONE does not read as text; named in the read report.
const NOT_READ: [&str; 6] = [
    "ACAD_PROXY_ENTITY",
    "3DSOLID",
    "REGION",
    "BODY",
    "SURFACE",
    "MESH",
];

pub fn push(out: &mut Value, key: &str, value: Value) {
    let n = out["totals"][key].as_u64().unwrap_or(0) + 1;
    out["totals"][key] = json!(n);
    let bytes = serde_json::to_vec(&value).map(|v| v.len()).unwrap_or(0) as u64;
    let used = out["output_bytes"].as_u64().unwrap_or(0);
    let (budget, total) = match key {
        "texts" | "embedded" => (40 * MIB, 56 * MIB),
        "hatches" => (MIB, 16 * MIB),
        "closed" | "segments" => (12 * MIB, 16 * MIB),
        _ => (8 * MIB, 56 * MIB),
    };
    let key_used = out["byte_counts"][key].as_u64().unwrap_or(0);
    if out[key].as_array().unwrap().len() < LIMIT
        && key_used + bytes < budget
        && used + bytes < total
    {
        out[key].as_array_mut().unwrap().push(value);
        out["output_bytes"] = json!(used + bytes);
        out["byte_counts"][key] = json!(key_used + bytes);
    } else {
        limit(out, key);
    }
}

/// A row of `key` was not kept: geometry for take-off only, or content the reading lost.
pub fn limit(out: &mut Value, key: &str) {
    let flag = if GEOMETRY.contains(&key) {
        "limited_geometry"
    } else {
        "limited"
    };
    out[flag] = json!(true);
}

/// `n` texts the reader does not emit at all (past a per-entity limit): counted as not kept.
pub fn skip_texts(out: &mut Value, n: u64) {
    if n > 0 {
        out["totals"]["texts"] = json!(out["totals"]["texts"].as_u64().unwrap_or(0) + n);
        out["limited"] = json!(true);
    }
}

// Circular arcs are sampled only for containment; segment integrals retain their area.
pub fn outline(out: &mut Value, mut row: Value, points: Vec<(f64, f64, f64)>) {
    if points.len() < 2 || points.len() > 4096 {
        limit(out, "closed");
        return;
    }
    let mut vertices = Vec::new();
    let mut twice_area = 0.0;
    for (i, &(x, y, bulge)) in points.iter().enumerate() {
        let (xx, yy, _) = points[(i + 1) % points.len()];
        twice_area += x * yy - xx * y;
        vertices.push([x, y]);
        if bulge.abs() > 1e-12 {
            let chord = (xx - x).hypot(yy - y);
            if chord == 0.0 {
                continue;
            }
            let theta = 4.0 * bulge.atan();
            let radius = chord * (1.0 + bulge * bulge) / (4.0 * bulge.abs());
            let cx = (x + xx) / 2.0 - (yy - y) * (1.0 - bulge * bulge) / (4.0 * bulge);
            let cy = (y + yy) / 2.0 + (xx - x) * (1.0 - bulge * bulge) / (4.0 * bulge);
            let start = (y - cy).atan2(x - cx);
            let segments = (theta.abs() / 0.05).ceil() as usize;
            for n in 1..segments {
                let a = start + theta * n as f64 / segments as f64;
                vertices.push([cx + radius * a.cos(), cy + radius * a.sin()]);
            }
            twice_area += radius * radius * (theta - theta.sin());
        }
        if vertices.len() > 4096 {
            limit(out, "closed");
            return;
        }
    }
    row["vertices"] = json!(vertices);
    row["area"] = json!(twice_area.abs() / 2.0);
    push(out, "closed", row);
}

fn text(value: &str) -> String {
    value.chars().take(8192).collect()
}

fn summary(doc: &CadDocument) -> Value {
    let s = &doc.summary_info;
    json!({"title":text(&s.title),"subject":text(&s.subject),"author":text(&s.author),
        "keywords":text(&s.keywords),"comments":text(&s.comments),
        "revision_number":s.revision_number,"last_saved_by":text(&s.last_saved_by),
        "hyperlink_base":text(&s.hyperlink_base),
        "custom_properties":s.custom_properties.iter().take(128)
            .map(|(k,v)|(k.chars().take(256).collect::<String>(),text(v))).collect::<Vec<_>>()})
}

pub fn digest(doc: &CadDocument, format: &str) -> Value {
    let h = &doc.header;
    let mut out = json!({"format":format,"version":format!("{:?}",doc.version),
        "units":h.insertion_units,"code_page":h.code_page,"measurement":h.measurement,
        "linear_unit_format":h.linear_unit_format,
        "extents":[h.model_space_extents_min.x,h.model_space_extents_min.y,h.model_space_extents_max.x,h.model_space_extents_max.y],
        "paper_extents":[h.paper_space_extents_min.x,h.paper_space_extents_min.y,h.paper_space_extents_max.x,h.paper_space_extents_max.y],
        "summary_info":summary(doc),"styles":[],"embedded":[],"segments":[],"omitted":{},
        "traversal_limited":false,"entity_kinds":{},"unread_kinds":{},"layers":[],"layouts":[],
        "texts":[],"inserts":[],"dimensions":[],"hatches":[],"closed":[],"xrefs":[],"blocks":[],
        "tables":[],"references":[],"problems":[],"totals":{},"byte_counts":{},"output_bytes":0,
        "limited":false,"limited_geometry":false,"cut_texts":0,"work":0});
    for style in doc.text_styles.iter().take(LIMIT) {
        push(
            &mut out,
            "styles",
            json!({"name":style.name,"font_file":style.font_file,"big_font_file":style.big_font_file,"true_type_font":style.true_type_font}),
        );
    }
    let mut per_layer: HashMap<String, u64> = HashMap::new();
    for entity in doc.entities() {
        let kind = entity.as_entity().entity_type();
        let count = out["entity_kinds"][kind].as_u64().unwrap_or(0);
        out["entity_kinds"][kind] = json!(count + 1);
        let unread = match entity {
            EntityType::Unknown(u) => Some(u.dxf_name.as_str()),
            _ if NOT_READ.contains(&kind) => Some(kind),
            _ => None,
        };
        if let Some(name) = unread {
            let n = out["unread_kinds"][name].as_u64().unwrap_or(0);
            out["unread_kinds"][name] = json!(n + 1);
        }
        *per_layer
            .entry(entity.common().layer.to_uppercase())
            .or_insert(0) += 1;
    }
    for l in doc.layers.iter().take(LIMIT) {
        let entities = per_layer.get(&l.name.to_uppercase()).copied().unwrap_or(0);
        push(
            &mut out,
            "layers",
            json!({"name":l.name,"on":!l.flags.off,"frozen":l.flags.frozen,"locked":l.flags.locked,"plot":l.is_plottable,"entities":entities}),
        );
    }
    // Block definitions with their attribute definitions: constant values live only here.
    for b in doc
        .block_records
        .iter()
        .filter(|b| !b.is_layout())
        .take(LIMIT)
    {
        let attdefs: Vec<_> = doc
            .entities_in_block(&b.name)
            .filter_map(|e| match e {
                EntityType::AttributeDefinition(a) => Some(json!({"tag":a.tag,"prompt":text(&a.prompt),
                    "default":text(&a.default_value),"constant":a.flags.constant,"invisible":a.flags.invisible})),
                _ => None,
            })
            .take(256)
            .collect();
        push(
            &mut out,
            "blocks",
            json!({"name":b.name,"entities":b.entity_handles.len(),"xref":b.flags.is_xref,"anonymous":b.name.starts_with('*'),"attdefs":attdefs}),
        );
    }
    let layouts: Vec<_> = doc
        .objects
        .values()
        .filter_map(|o| match o {
            ObjectType::Layout(l) => Some(l),
            _ => None,
        })
        .take(1024)
        .collect();
    for l in &layouts {
        let viewports: Vec<_> = doc.entities().filter(|e| e.common().owner_handle == l.block_record).filter_map(|e| if let EntityType::Viewport(v)=e {Some(json!({"scale":if v.view_height != 0.0 {Some(v.height/v.view_height)} else {None},"center":[v.center.x,v.center.y],"size":[v.width,v.height]}))}else{None}).take(LIMIT).collect();
        push(
            &mut out,
            "layouts",
            json!({"name":l.name,"tab_order":l.tab_order,"paper_size":[l.paper_width,l.paper_height],"viewports":viewports}),
        );
    }
    for b in doc
        .block_records
        .iter()
        .filter(|b| b.flags.is_xref)
        .take(LIMIT)
    {
        push(
            &mut out,
            "xrefs",
            json!({"name":b.name,"path":b.xref_path,"overlay":b.flags.is_xref_overlay}),
        );
    }
    for e in doc.entities() {
        let c = e.common();
        let layout = layouts
            .iter()
            .find(|l| l.block_record == c.owner_handle)
            .map(|l| l.name.as_str());
        // Block definitions are traversed at their insert, never counted as placed objects.
        if layout.is_none()
            && doc
                .block_records
                .iter()
                .any(|b| b.handle == c.owner_handle && !b.is_layout())
        {
            continue;
        }
        emit(doc, e, layout.unwrap_or("Model"), None, "", &mut out, 0);
    }
    out
}

#[cfg(test)]
mod tests {
    #[test]
    fn curved_closed_outline_is_preserved() {
        use acadrust::entities::{LwPolyline, LwVertex};
        use acadrust::types::Vector2;
        let mut doc = acadrust::CadDocument::new();
        let mut p = LwPolyline::new();
        p.add_vertex(LwVertex::with_bulge(Vector2::new(0.0, 0.0), 1.0));
        p.add_vertex(LwVertex::new(Vector2::new(2.0, 0.0)));
        p.close();
        doc.add_entity(acadrust::EntityType::LwPolyline(p)).unwrap();
        let out = super::digest(&doc, "dxf");
        assert_eq!(out["closed"].as_array().unwrap().len(), 1);
        assert!(
            (out["closed"][0]["area"].as_f64().unwrap() - std::f64::consts::PI / 2.0).abs() < 1e-8
        );
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
        let (out, _) = super::read("binary.dxf", data).unwrap();
        assert_eq!(out["inserts"][0]["attributes"][0]["value"], "A-101");
    }
    #[test]
    fn output_has_a_byte_budget() {
        let mut out = serde_json::json!({"texts":[],"totals":{},"output_bytes":0});
        for _ in 0..10000 {
            super::push(
                &mut out,
                "texts",
                serde_json::json!({"text":"a".repeat(8192)}),
            );
        }
        assert!(serde_json::to_vec(&out).unwrap().len() < 32 * 1024 * 1024);
        assert_eq!(out["totals"]["texts"], 10000);
    }
    #[test]
    fn title_layout_and_attributes() {
        for bytes in [
            include_bytes!("../../core/tests/fixtures/drawings/title.dxf").as_slice(),
            include_bytes!("../../core/tests/fixtures/drawings/arabic.dxf").as_slice(),
        ] {
            let (out, _) = super::read("sample.dxf", bytes.to_vec()).unwrap();
            assert!(out["inserts"]
                .as_array()
                .unwrap()
                .iter()
                .any(|i| !i["attributes"].as_array().unwrap().is_empty()));
            assert!(out["closed"].as_array().unwrap().len() >= 1);
            assert!(out["layouts"]
                .as_array()
                .unwrap()
                .iter()
                .any(|l| l["name"] == "Layout1"));
        }
    }
    #[test]
    fn damaged_is_reported() {
        match super::read(
            "damaged.dxf",
            include_bytes!("../../core/tests/fixtures/drawings/damaged.dxf").to_vec(),
        ) {
            Ok((out, code)) => {
                assert_eq!(code, 2);
                assert!(!out["problems"].as_array().unwrap().is_empty());
            }
            Err(e) => assert!(!e.is_empty()),
        }
    }
    #[test]
    fn sample_dwg() {
        let (out, _) = super::read(
            "test-plan.dwg",
            include_bytes!("../../core/tests/fixtures/drawings/test-plan.dwg").to_vec(),
        )
        .unwrap();
        let inserts = out["inserts"].as_array().unwrap();
        for (name, count) in [("DOOR", 3), ("WINDOW", 5), ("COLUMN", 6)] {
            assert_eq!(inserts.iter().filter(|v| v["block"] == name).count(), count);
        }
        assert!(out["texts"]
            .as_array()
            .unwrap()
            .iter()
            .any(|v| v["text"].as_str().unwrap().contains("LIVING")));
    }
}

use acadrust::io::{
    dwg::{DwgReadOptions, DwgReader},
    dxf::{DxfReader, DxfReaderConfiguration},
};
use acadrust::objects::ObjectType;
use acadrust::{CadDocument, EntityType};
use serde_json::{json, Value};
use std::io::{Cursor, Read};
const LIMIT: usize = 20_000;
const INPUT_LIMIT: u64 = 64 * 1024 * 1024;
fn push(out: &mut Value, key: &str, value: Value) {
    let n = out["totals"][key].as_u64().unwrap_or(0) + 1;
    out["totals"][key] = json!(n);
    let bytes = serde_json::to_vec(&value).map(|v| v.len()).unwrap_or(0) as u64;
    let used = out["output_bytes"].as_u64().unwrap_or(0);
    if out[key].as_array().unwrap().len() < LIMIT && used + bytes < 24 * 1024 * 1024 {
        out[key].as_array_mut().unwrap().push(value);
        out["output_bytes"] = json!(used + bytes);
    } else {
        out["limited"] = json!(true);
    }
}
// Circular arcs are sampled only for containment; segment integrals retain their area.
fn outline(out: &mut Value, mut row: Value, points: Vec<(f64, f64, f64)>) {
    if points.len() < 2 || points.len() > 4096 {
        out["limited"] = json!(true);
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
            out["limited"] = json!(true);
            return;
        }
    }
    row["vertices"] = json!(vertices);
    row["area"] = json!(twice_area.abs() / 2.0);
    push(out, "closed", row);
}
fn digest(doc: &CadDocument, format: &str) -> Value {
    let mut out = json!({"format":format,"version":format!("{:?}",doc.version),"units":doc.header.insertion_units,
        "summary_info":{"title":doc.summary_info.title.chars().take(8192).collect::<String>(),"subject":doc.summary_info.subject.chars().take(8192).collect::<String>(),"author":doc.summary_info.author.chars().take(8192).collect::<String>(),"keywords":doc.summary_info.keywords.chars().take(8192).collect::<String>(),"comments":doc.summary_info.comments.chars().take(8192).collect::<String>(),"revision_number":doc.summary_info.revision_number,
            "last_saved_by":doc.summary_info.last_saved_by.chars().take(8192).collect::<String>(),
            "hyperlink_base":doc.summary_info.hyperlink_base.chars().take(8192).collect::<String>(),
            "custom_properties":doc.summary_info.custom_properties.iter().take(128).map(|(k,v)|(k.chars().take(256).collect::<String>(),v.chars().take(8192).collect::<String>())).collect::<Vec<_>>()},"layers":[],"layouts":[],"texts":[],"inserts":[],"dimensions":[],"hatches":[],"closed":[],"xrefs":[],"problems":[],"totals":{},"output_bytes":0,"limited":false,"work":0});
    for l in doc.layers.iter().take(LIMIT) {
        push(
            &mut out,
            "layers",
            json!({"name":l.name,"on":!l.flags.off,"frozen":l.flags.frozen}),
        );
    }
    let layouts: Vec<_> = doc
        .objects
        .values()
        .filter_map(|o| {
            if let ObjectType::Layout(l) = o {
                Some(l)
            } else {
                None
            }
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
        let layout = layout.unwrap_or("Model");
        emit(doc, e, layout, None, &mut out, 0);
    }
    out
}
fn emit(
    doc: &CadDocument,
    e: &EntityType,
    layout: &str,
    block: Option<&str>,
    out: &mut Value,
    depth: usize,
) {
    let work = out["work"].as_u64().unwrap_or(0);
    if work >= 200_000 {
        out["limited"] = json!(true);
        return;
    }
    out["work"] = json!(work + 1);
    let c = e.common();
    let mut row =
        json!({"layer":c.layer,"layout":layout,"handle":format!("{:X}",c.handle.value())});
    if let Some(b) = block {
        row["block"] = json!(b);
    }
    match e {
        EntityType::Text(t) => {
            if t.value.chars().count() > 8192 {
                out["limited"] = json!(true);
            }
            row["text"] = json!(
                acadrust::entities::mtext_format::parse_mtext(&t.value, true)
                    .to_plain_text()
                    .chars()
                    .take(8192)
                    .collect::<String>()
            );
            row["x"] = json!(t.insertion_point.x);
            row["y"] = json!(t.insertion_point.y);
            row["height"] = json!(t.height);
            row["rotation"] = json!(t.rotation);
            push(out, "texts", row);
        }
        EntityType::MText(t) => {
            if t.value.chars().count() > 8192 {
                out["limited"] = json!(true);
            }
            row["text"] = json!(
                acadrust::entities::mtext_format::parse_mtext(&t.value, true)
                    .to_plain_text()
                    .chars()
                    .take(8192)
                    .collect::<String>()
            );
            row["x"] = json!(t.insertion_point.x);
            row["y"] = json!(t.insertion_point.y);
            row["height"] = json!(t.height);
            row["rotation"] = json!(t.rotation);
            push(out, "texts", row);
        }
        EntityType::Insert(i) => {
            if i.attributes.len() > 256
                || i.attributes.iter().any(|a| a.value.chars().count() > 8192)
            {
                out["limited"] = json!(true);
            }
            if depth >= 8 {
                out["limited"] = json!(true);
            }
            let parent = doc
                .dynamic_definition_for_insert(c.handle)
                .and_then(|h| doc.block_records.iter().find(|b| b.handle == h))
                .map(|b| b.name.as_str())
                .unwrap_or(&i.block_name);
            row["block"] = json!(parent);
            row["x"] = json!(i.insert_point.x);
            row["y"] = json!(i.insert_point.y);
            row["scale"] = json!([i.x_scale(), i.y_scale(), i.z_scale()]);
            row["rotation"] = json!(i.rotation);
            row["attributes"]=json!(i.attributes.iter().take(256).map(|a|json!({"tag":a.tag,"value":a.value.chars().take(8192).collect::<String>(),"handle":format!("{:X}",a.common.handle.value()),"x":a.insertion_point.x,"y":a.insertion_point.y})).collect::<Vec<_>>());
            push(out, "inserts", row);
            if depth < 8 && out["totals"]["texts"].as_u64().unwrap_or(0) < 100_000 {
                for child in doc.entities_in_block(&i.block_name).take(LIMIT) {
                    let mut placed = child.clone();
                    if let Some(b) = doc.block_records.iter().find(|b| b.name == i.block_name) {
                        placed.as_entity_mut().apply_transform(
                            &acadrust::types::Transform::from_translation(-b.base_point),
                        );
                    }
                    placed.as_entity_mut().apply_transform(&i.get_transform());
                    emit(doc, &placed, layout, Some(parent), out, depth + 1);
                }
            }
        }
        EntityType::LwPolyline(p) if p.is_closed => {
            if p.normal.x.abs() > 1e-8 || p.normal.y.abs() > 1e-8 || p.normal.z < 0.0 {
                out["limited"] = json!(true);
                return;
            }
            outline(
                out,
                row,
                p.vertices
                    .iter()
                    .take(4097)
                    .map(|v| (v.location.x, v.location.y, v.bulge))
                    .collect(),
            );
        }
        EntityType::Polyline2D(p) if p.is_closed() => {
            if p.normal.x.abs() > 1e-8 || p.normal.y.abs() > 1e-8 || p.normal.z < 0.0 {
                out["limited"] = json!(true);
                return;
            }
            outline(
                out,
                row,
                p.vertices
                    .iter()
                    .take(4097)
                    .map(|v| (v.location.x, v.location.y, v.bulge))
                    .collect(),
            );
        }
        EntityType::Polyline(p) if p.is_closed() => {
            if let Some(v) = p.vertices.first() {
                if p.vertices
                    .iter()
                    .any(|q| (q.location.z - v.location.z).abs() > 1e-8)
                {
                    out["limited"] = json!(true);
                    return;
                }
            }
            outline(
                out,
                row,
                p.vertices
                    .iter()
                    .take(4097)
                    .map(|v| (v.location.x, v.location.y, 0.0))
                    .collect(),
            );
        }
        EntityType::Polyline3D(p) if p.is_closed() => {
            if let Some(v) = p.vertices.first() {
                if p.vertices
                    .iter()
                    .any(|q| (q.position.z - v.position.z).abs() > 1e-8)
                {
                    out["limited"] = json!(true);
                    return;
                }
            }
            outline(
                out,
                row,
                p.vertices
                    .iter()
                    .take(4097)
                    .map(|v| (v.position.x, v.position.y, 0.0))
                    .collect(),
            );
        }
        EntityType::Circle(p) => {
            if p.normal.x.abs() > 1e-8 || p.normal.y.abs() > 1e-8 || p.normal.z < 0.0 {
                out["limited"] = json!(true);
                return;
            }
            row["vertices"] = json!((0..128)
                .map(|n| {
                    let a = n as f64 * std::f64::consts::TAU / 128.0;
                    [
                        p.center.x + p.radius * a.cos(),
                        p.center.y + p.radius * a.sin(),
                    ]
                })
                .collect::<Vec<_>>());
            row["area"] = json!(std::f64::consts::PI * p.radius * p.radius);
            push(out, "closed", row);
        }
        EntityType::Dimension(d) => {
            row["kind"] = json!(format!("{:?}", d.base().dimension_type));
            row["measured"] = json!(d.measurement());
            row["text"] = json!(d.base().text);
            push(out, "dimensions", row);
        }
        EntityType::Hatch(h) => {
            row["pattern"] = json!(h.pattern.name);
            row["loop_count"] = json!(h.paths.len());
            row["loops"] = json!(h.paths.iter().take(64).collect::<Vec<_>>());
            if h.paths.len() > 64 {
                out["limited"] = json!(true);
            }
            push(out, "hatches", row);
        }
        _ => {}
    }
}
fn read(name: &str, data: Vec<u8>) -> Result<(Value, i32), String> {
    let dwg = name.to_lowercase().ends_with(".dwg");
    let result = if dwg {
        DwgReader::from_stream_with_options(
            Cursor::new(data),
            DwgReadOptions::failsafe().with_max_decompressed_bytes(128 * 1024 * 1024),
        )
        .read_with_stats()
    } else {
        DxfReader::from_reader(Cursor::new(data))
            .map(|r| {
                r.with_configuration(DxfReaderConfiguration {
                    failsafe: true,
                    ..Default::default()
                })
            })
            .and_then(|r| r.read_with_stats())
    };
    let result = result.map_err(|e| e.to_string())?;
    let mut out = digest(&result.document, if dwg { "dwg" } else { "dxf" });
    out["problems"] = json!(result.stats.diagnostics);
    let capped = out["limited"] == true
        || out["totals"]
            .as_object()
            .unwrap()
            .values()
            .any(|v| v.as_u64().unwrap_or(0) > LIMIT as u64);
    if capped {
        out["problems"].as_array_mut().unwrap().push(json!({"code":"output-limit","message":"Output capped; totals include omitted entities"}));
    }
    let code = if result.stats.recovered() || capped {
        2
    } else {
        0
    };
    out.as_object_mut().unwrap().remove("work");
    out.as_object_mut().unwrap().remove("output_bytes");
    Ok((out, code))
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let name = args
        .windows(2)
        .find(|a| a[0] == "--name")
        .map(|a| a[1].as_str())
        .unwrap_or("");
    let mut data = Vec::new();
    let result = std::io::stdin()
        .take(INPUT_LIMIT + 1)
        .read_to_end(&mut data)
        .map_err(|e| e.to_string())
        .and_then(|_| {
            if data.len() as u64 > INPUT_LIMIT {
                Err("Input exceeds reader limit".into())
            } else {
                std::panic::catch_unwind(|| read(name, data))
                    .unwrap_or_else(|_| Err("Reader could not recover drawing".into()))
            }
        });
    let (out, code) = result.unwrap_or_else(|e| (json!({"problems":[e]}), 1));
    println!("{}", out);
    std::process::exit(code);
}

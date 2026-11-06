#[cfg(test)]
mod tests {
    #[test]
    fn paper_grid_lines_are_positioned() {
        let doc = acadrust::CadDocument::new();
        let mut line = acadrust::entities::Line::new();
        line.end = acadrust::types::Vector3::new(10.0, 20.0, 0.0);
        let mut out = super::digest(&doc, "dxf");
        super::emit(
            &doc,
            &acadrust::EntityType::Line(line),
            "Layout1",
            None,
            "",
            &mut out,
            0,
        );
        assert_eq!(out["segments"][0]["end"], serde_json::json!([10.0, 20.0]));
    }
    #[test]
    fn hatch_budget_does_not_starve_text() {
        let mut out = serde_json::json!({"hatches":[],"texts":[],"totals":{},"byte_counts":{},"output_bytes":0});
        for _ in 0..20 {
            super::push(
                &mut out,
                "hatches",
                serde_json::json!({"loops":"x".repeat(100000)}),
            );
        }
        super::push(&mut out, "texts", serde_json::json!({"text":"SAMPLE"}));
        assert_eq!(out["texts"][0]["text"], "SAMPLE");
        assert_eq!(out["limited"], true);
    }
    #[test]
    fn styles_and_table_cells_are_evidence() {
        let mut doc = acadrust::CadDocument::new();
        let mut style = acadrust::tables::TextStyle::new("SampleArabic");
        style.font_file = "arabic.shx".into();
        doc.text_styles.add(style).unwrap();
        let mut t = acadrust::entities::Text::new();
        t.value = "synthetic".into();
        t.style = "SampleArabic".into();
        doc.add_entity(acadrust::EntityType::Text(t)).unwrap();
        let mut table =
            acadrust::entities::Table::new(acadrust::types::Vector3::new(10.0, 20.0, 0.0), 1, 1);
        table.set_cell_text(0, 0, "SAMPLE CELL");
        doc.add_entity(acadrust::EntityType::Table(Box::new(table)))
            .unwrap();
        let out = super::digest(&doc, "dxf");
        assert_eq!(out["texts"][0]["font_file"], "arabic.shx");
        assert_eq!(out["texts"][0]["raw_text"], "synthetic");
        assert!(out["texts"]
            .as_array()
            .unwrap()
            .iter()
            .any(|r| r["text"] == "SAMPLE CELL" && r["table_cell"] == serde_json::json!([0, 0])));
    }
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
        let mut out = serde_json::json!({"texts":[],"totals":{},"byte_counts":{},"output_bytes":0});
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
const LIMIT: usize = 100_000;
const INPUT_LIMIT: u64 = 64 * 1024 * 1024;
fn push(out: &mut Value, key: &str, value: Value) {
    let n = out["totals"][key].as_u64().unwrap_or(0) + 1;
    out["totals"][key] = json!(n);
    let bytes = serde_json::to_vec(&value).map(|v| v.len()).unwrap_or(0) as u64;
    let used = out["output_bytes"].as_u64().unwrap_or(0);
    let budget = match key {
        "hatches" => 1024 * 1024,
        "closed" => 16 * 1024 * 1024,
        "embedded" => 40 * 1024 * 1024,
        _ => 8 * 1024 * 1024,
    };
    let key_used = out["byte_counts"][key].as_u64().unwrap_or(0);
    if out[key].as_array().unwrap().len() < LIMIT
        && key_used + bytes < budget
        && used + bytes < 56 * 1024 * 1024
    {
        out[key].as_array_mut().unwrap().push(value);
        out["output_bytes"] = json!(used + bytes);
        out["byte_counts"][key] = json!(key_used + bytes);
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
    let mut out = json!({"format":format,"version":format!("{:?}",doc.version),"units":doc.header.insertion_units,"extents":[doc.header.model_space_extents_min.x,doc.header.model_space_extents_min.y,doc.header.model_space_extents_max.x,doc.header.model_space_extents_max.y],
        "summary_info":{"title":doc.summary_info.title.chars().take(8192).collect::<String>(),"subject":doc.summary_info.subject.chars().take(8192).collect::<String>(),"author":doc.summary_info.author.chars().take(8192).collect::<String>(),"keywords":doc.summary_info.keywords.chars().take(8192).collect::<String>(),"comments":doc.summary_info.comments.chars().take(8192).collect::<String>(),"revision_number":doc.summary_info.revision_number,
            "last_saved_by":doc.summary_info.last_saved_by.chars().take(8192).collect::<String>(),
            "hyperlink_base":doc.summary_info.hyperlink_base.chars().take(8192).collect::<String>(),
            "custom_properties":doc.summary_info.custom_properties.iter().take(128).map(|(k,v)|(k.chars().take(256).collect::<String>(),v.chars().take(8192).collect::<String>())).collect::<Vec<_>>()},"styles":[],"embedded":[],"segments":[],"omitted":{},"traversal_limited":false,"entity_kinds":{},"layers":[],"layouts":[],"texts":[],"inserts":[],"dimensions":[],"hatches":[],"closed":[],"xrefs":[],"problems":[],"totals":{},"byte_counts":{},"output_bytes":0,"limited":false,"work":0});
    for style in doc.text_styles.iter().take(LIMIT) {
        push(
            &mut out,
            "styles",
            json!({"name":style.name,"font_file":style.font_file,"big_font_file":style.big_font_file,"true_type_font":style.true_type_font}),
        );
    }
    for entity in doc.entities() {
        let kind = entity.as_entity().entity_type();
        let count = out["entity_kinds"][kind].as_u64().unwrap_or(0);
        out["entity_kinds"][kind] = json!(count + 1);
    }
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
        emit(doc, e, layout, None, "", &mut out, 0);
    }
    out
}
fn package_stream(storage: &acadrust::compound_file::CompoundStorage) -> Option<Vec<u8>> {
    for entry in &storage.entries {
        match entry {
            acadrust::compound_file::CompoundEntry::Stream(s) if s.name == "Package" => {
                return Some(s.content.encode())
            }
            acadrust::compound_file::CompoundEntry::Storage(s) => {
                if let Some(data) = package_stream(s) {
                    return Some(data);
                }
            }
            _ => {}
        }
    }
    None
}
fn stream_names(storage: &acadrust::compound_file::CompoundStorage, names: &mut Vec<String>) {
    for entry in &storage.entries {
        match entry {
            acadrust::compound_file::CompoundEntry::Stream(s) => names.push(s.name.clone()),
            acadrust::compound_file::CompoundEntry::Storage(s) => stream_names(s, names),
        }
    }
}
fn text_style(doc: &CadDocument, name: &str, row: &mut Value) {
    row["style"] = json!(name);
    if let Some(style) = doc.text_styles.get(name) {
        row["font_file"] = json!(style.font_file);
        row["big_font_file"] = json!(style.big_font_file);
    }
}
fn emit(
    doc: &CadDocument,
    e: &EntityType,
    layout: &str,
    block: Option<&str>,
    context: &str,
    out: &mut Value,
    depth: usize,
) {
    if !matches!(
        e,
        EntityType::Line(_)
            | EntityType::Text(_)
            | EntityType::MText(_)
            | EntityType::Insert(_)
            | EntityType::Table(_)
            | EntityType::Ole2Frame(_)
            | EntityType::LwPolyline(_)
            | EntityType::Polyline2D(_)
            | EntityType::Polyline(_)
            | EntityType::Polyline3D(_)
            | EntityType::Circle(_)
            | EntityType::Dimension(_)
            | EntityType::Hatch(_)
    ) {
        return;
    }
    let work = out["work"].as_u64().unwrap_or(0);
    if work >= 2_000_000 {
        out["traversal_limited"] = json!(true);
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
    row["context"] = json!(context);
    if let Some(b) = block {
        row["container"] = json!(b);
    }
    match e {
        EntityType::Line(line) => {
            let ancestry = context.to_lowercase();
            if layout != "Model"
                || ["frame", "title", "layout"]
                    .iter()
                    .any(|s| ancestry.contains(s))
            {
                row["start"] = json!([line.start.x, line.start.y]);
                row["end"] = json!([line.end.x, line.end.y]);
                push(out, "segments", row);
            }
        }
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
            row["raw_text"] = json!(t.value.chars().take(8192).collect::<String>());
            text_style(doc, &t.style, &mut row);
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
            row["raw_text"] = json!(t.value.chars().take(8192).collect::<String>());
            text_style(doc, &t.style, &mut row);
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
            row["x"] = json!(i.insert_point.x);
            row["y"] = json!(i.insert_point.y);
            row["scale"] = json!([i.x_scale(), i.y_scale(), i.z_scale()]);
            row["rotation"] = json!(i.rotation);
            row["attributes"]=json!(i.attributes.iter().take(256).map(|a|json!({"tag":a.tag,"value":acadrust::entities::mtext_format::parse_mtext(&a.value, true).to_plain_text().chars().take(8192).collect::<String>(),"handle":format!("{:X}",a.common.handle.value()),"x":a.insertion_point.x,"y":a.insertion_point.y})).collect::<Vec<_>>());
            for a in i.attributes.iter().take(256) {
                if !a.value.is_empty() {
                    let mut attr = row.clone();
                    attr.as_object_mut().unwrap().remove("attributes");
                    attr["text"] = json!(acadrust::entities::mtext_format::parse_mtext(
                        &a.value, true
                    )
                    .to_plain_text()
                    .chars()
                    .take(8192)
                    .collect::<String>());
                    attr["raw_text"] = json!(a.value.chars().take(8192).collect::<String>());
                    attr["handle"] = json!(format!("{:X}", a.common.handle.value()));
                    attr["x"] = json!(a.insertion_point.x);
                    attr["y"] = json!(a.insertion_point.y);
                    attr["height"] = json!(a.height);
                    text_style(doc, &a.text_style, &mut attr);
                    push(out, "texts", attr);
                }
            }
            if depth == 0 {
                let mut bounds = [
                    f64::INFINITY,
                    f64::INFINITY,
                    f64::NEG_INFINITY,
                    f64::NEG_INFINITY,
                ];
                for child in doc.entities_in_block(&i.block_name).take(LIMIT) {
                    let mut placed = child.clone();
                    if let Some(b) = doc.block_records.get(&i.block_name) {
                        placed.as_entity_mut().apply_transform(
                            &acadrust::types::Transform::from_translation(-b.base_point),
                        );
                    }
                    placed.as_entity_mut().apply_transform(&i.get_transform());
                    let b = placed.as_entity().bounding_box();
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
                    let mut placed = child.clone();
                    if let Some(b) = doc.block_records.iter().find(|b| b.name == i.block_name) {
                        placed.as_entity_mut().apply_transform(
                            &acadrust::types::Transform::from_translation(-b.base_point),
                        );
                    }
                    placed.as_entity_mut().apply_transform(&i.get_transform());
                    emit(
                        doc,
                        &placed,
                        layout,
                        Some(parent),
                        &format!("{}/{}:{:X}", context, parent, c.handle.value()),
                        out,
                        depth + 1,
                    );
                }
            }
        }
        EntityType::Ole2Frame(t) => {
            row["x"] = json!(t.upper_left_corner.x);
            row["y"] = json!(t.upper_left_corner.y);
            row["application"] = json!(t.source_application);
            if let Some(file) = &t.storage.compound_file {
                let mut names = Vec::new();
                stream_names(&file.root, &mut names);
                row["streams"] = json!(names);
                if let Some(data) = package_stream(&file.root) {
                    if data.len() <= 8 * 1024 * 1024 {
                        row["package_hex"] = json!(data
                            .iter()
                            .map(|b| format!("{:02x}", b))
                            .collect::<String>());
                    } else {
                        out["limited"] = json!(true);
                    }
                }
                if names
                    .iter()
                    .any(|s| s.eq_ignore_ascii_case("Workbook") || s.eq_ignore_ascii_case("Book"))
                {
                    let data = file.encode();
                    if data.len() <= 8 * 1024 * 1024 {
                        row["compound_hex"] = json!(data
                            .iter()
                            .map(|b| format!("{:02x}", b))
                            .collect::<String>());
                    } else {
                        out["limited"] = json!(true);
                    }
                }
            }
            push(out, "embedded", row);
        }
        EntityType::Table(t) => {
            let mut y = t.insertion_point.y;
            for (ri, r) in t.rows.iter().take(4096).enumerate() {
                let mut x = t.insertion_point.x;
                for (ci, cell) in r.cells.iter().take(1024).enumerate() {
                    for content in &cell.contents {
                        let text = content.value.display();
                        if !text.is_empty() {
                            let mut cell_row = row.clone();
                            cell_row["text"] =
                                json!(acadrust::entities::mtext_format::parse_mtext(text, true)
                                    .to_plain_text()
                                    .chars()
                                    .take(8192)
                                    .collect::<String>());
                            cell_row["raw_text"] =
                                json!(text.chars().take(8192).collect::<String>());
                            cell_row["table_cell"] = json!([ri, ci]);
                            cell_row["x"] = json!(x);
                            cell_row["y"] = json!(y);
                            cell_row["height"] = json!(content.text_height);
                            text_style(doc, &content.text_style_name, &mut cell_row);
                            push(out, "texts", cell_row);
                        }
                    }
                    x += t.columns.get(ci).map(|c| c.width).unwrap_or(0.0);
                }
                y -= r.height;
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
    for key in [
        "texts", "inserts", "closed", "hatches", "embedded", "segments",
    ] {
        let omitted = out["totals"][key]
            .as_u64()
            .unwrap_or(0)
            .saturating_sub(out[key].as_array().unwrap().len() as u64);
        if omitted > 0 {
            out["omitted"][key] = json!(omitted);
        }
    }
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
    out.as_object_mut().unwrap().remove("byte_counts");
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

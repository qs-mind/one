//! One placed entity as JSON rows: texts (with their `kind`), inserts and the entities of their
//! blocks, tables, dimensions with the text the sheet shows, references to other files,
//! embedded workbooks, and take-off geometry.

use crate::digest::{limit, outline, push, skip_texts};
use crate::embed::{hex, package_stream, stream_names};
use crate::insert::insert;
use crate::text::{long, mtext, place, raw, single, text_style};
use acadrust::objects::ObjectType;
use acadrust::{CadDocument, EntityType};
use serde_json::{json, Value};

pub fn emit(
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
            | EntityType::MultiLeader(_)
            | EntityType::Tolerance(_)
            | EntityType::AttributeDefinition(_)
            | EntityType::RasterImage(_)
            | EntityType::Underlay(_)
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
        row["container"] = json!(b);
    }
    row["context"] = json!(context);
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
            long(out, &t.value);
            row["kind"] = json!("TEXT");
            row["text"] = json!(single(&t.value));
            row["raw_text"] = json!(raw(&t.value));
            text_style(doc, &t.style, &mut row);
            place(&mut row, t.insertion_point.x, t.insertion_point.y);
            row["height"] = json!(t.height);
            row["rotation"] = json!(t.rotation);
            push(out, "texts", row);
        }
        EntityType::MText(t) => {
            long(out, &t.value);
            row["kind"] = json!("MTEXT");
            row["text"] = json!(mtext(&t.value));
            row["raw_text"] = json!(raw(&t.value));
            text_style(doc, &t.style, &mut row);
            place(&mut row, t.insertion_point.x, t.insertion_point.y);
            row["height"] = json!(t.height);
            row["rotation"] = json!(t.rotation);
            push(out, "texts", row);
        }
        EntityType::Insert(i) => insert(doc, i, c, layout, block, context, out, depth, row),
        EntityType::Ole2Frame(t) => {
            place(&mut row, t.upper_left_corner.x, t.upper_left_corner.y);
            row["application"] = json!(t.source_application);
            if let Some(file) = &t.storage.compound_file {
                let mut names = Vec::new();
                stream_names(&file.root, &mut names);
                row["streams"] = json!(names);
                if let Some(data) = package_stream(&file.root) {
                    if data.len() <= 8 * 1024 * 1024 {
                        row["package_hex"] = json!(hex(&data));
                    } else {
                        row["too_large"] = json!(true);
                        out["limited"] = json!(true);
                    }
                }
                if names
                    .iter()
                    .any(|s| s.eq_ignore_ascii_case("Workbook") || s.eq_ignore_ascii_case("Book"))
                {
                    let data = file.encode();
                    if data.len() <= 8 * 1024 * 1024 {
                        row["compound_hex"] = json!(hex(&data));
                    } else {
                        row["too_large"] = json!(true);
                        out["limited"] = json!(true);
                    }
                }
            }
            push(out, "embedded", row);
        }
        EntityType::Table(t) => {
            let mut table = row.clone();
            place(&mut table, t.insertion_point.x, t.insertion_point.y);
            table["rows"] = json!(t.rows.len());
            table["columns"] = json!(t.columns.len());
            push(out, "tables", table);
            let filled = |cells: &[acadrust::entities::TableCell]| {
                let texts = cells.iter().flat_map(|c| &c.contents);
                texts.filter(|c| !c.value.display().is_empty()).count() as u64
            };
            let rows_past = t
                .rows
                .iter()
                .skip(4096)
                .map(|r| filled(&r.cells))
                .sum::<u64>();
            let columns_past = t
                .rows
                .iter()
                .take(4096)
                .map(|r| filled(r.cells.get(1024..).unwrap_or(&[])));
            skip_texts(out, rows_past + columns_past.sum::<u64>());
            let mut y = t.insertion_point.y;
            for (ri, r) in t.rows.iter().take(4096).enumerate() {
                let mut x = t.insertion_point.x;
                for (ci, cell) in r.cells.iter().take(1024).enumerate() {
                    for content in &cell.contents {
                        let text = content.value.display();
                        if !text.is_empty() {
                            long(out, text);
                            let mut cell_row = row.clone();
                            cell_row["kind"] = json!("TABLE");
                            cell_row["text"] = json!(mtext(text));
                            cell_row["raw_text"] = json!(raw(text));
                            cell_row["table_cell"] = json!([ri, ci]);
                            place(&mut cell_row, x, y);
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
                limit(out, "closed");
                return;
            }
            let points = p.vertices.iter().take(4097);
            outline(
                out,
                row,
                points
                    .map(|v| (v.location.x, v.location.y, v.bulge))
                    .collect(),
            );
        }
        EntityType::Polyline2D(p) if p.is_closed() => {
            if p.normal.x.abs() > 1e-8 || p.normal.y.abs() > 1e-8 || p.normal.z < 0.0 {
                limit(out, "closed");
                return;
            }
            let points = p.vertices.iter().take(4097);
            outline(
                out,
                row,
                points
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
                    limit(out, "closed");
                    return;
                }
            }
            let points = p.vertices.iter().take(4097);
            outline(
                out,
                row,
                points.map(|v| (v.location.x, v.location.y, 0.0)).collect(),
            );
        }
        EntityType::Polyline3D(p) if p.is_closed() => {
            if let Some(v) = p.vertices.first() {
                if p.vertices
                    .iter()
                    .any(|q| (q.position.z - v.position.z).abs() > 1e-8)
                {
                    limit(out, "closed");
                    return;
                }
            }
            let points = p.vertices.iter().take(4097);
            outline(
                out,
                row,
                points.map(|v| (v.position.x, v.position.y, 0.0)).collect(),
            );
        }
        EntityType::Circle(p) => {
            if p.normal.x.abs() > 1e-8 || p.normal.y.abs() > 1e-8 || p.normal.z < 0.0 {
                limit(out, "closed");
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
            let b = d.base();
            row["kind"] = json!(format!("{:?}", b.dimension_type));
            row["measured"] = json!(d.measurement());
            row["stored"] = json!(b.actual_measurement);
            row["text"] = json!(b.text);
            place(&mut row, b.text_middle_point.x, b.text_middle_point.y);
            row["style"] = json!(b.style_name);
            if let Some(st) = doc.dim_styles.get(&b.style_name) {
                row["dimlfac"] = json!(st.dimlfac);
                row["dimpost"] = json!(st.dimpost);
            }
            // What the sheet shows: the text inside the dimension's own anonymous block.
            let shown: Vec<String> = doc
                .entities_in_block(&b.block_name)
                .filter_map(|c| match c {
                    EntityType::MText(t) => Some(mtext(&t.value)),
                    EntityType::Text(t) => Some(single(&t.value)),
                    _ => None,
                })
                .take(8)
                .collect();
            row["shown"] = json!(shown);
            push(out, "dimensions", row);
        }
        EntityType::Hatch(h) => {
            row["pattern"] = json!(h.pattern.name);
            row["loop_count"] = json!(h.paths.len());
            row["loops"] = json!(h.paths.iter().take(64).collect::<Vec<_>>());
            if h.paths.len() > 64 {
                limit(out, "hatches");
            }
            push(out, "hatches", row);
        }
        EntityType::MultiLeader(m) => {
            let c = &m.context;
            if c.has_text_contents && !c.text_string.is_empty() {
                long(out, &c.text_string);
                row["kind"] = json!("MLEADER");
                row["text"] = json!(mtext(&c.text_string));
                row["raw_text"] = json!(raw(&c.text_string));
                place(&mut row, c.text_location.x, c.text_location.y);
                row["height"] = json!(c.text_height);
                push(out, "texts", row.clone());
            }
            let past = m
                .block_attributes
                .iter()
                .skip(256)
                .filter(|a| !a.text.is_empty());
            skip_texts(out, past.count() as u64);
            for a in m.block_attributes.iter().take(256) {
                if !a.text.is_empty() {
                    long(out, &a.text);
                    let mut r = row.clone();
                    r["kind"] = json!("MLEADER_ATTRIBUTE");
                    r["text"] = json!(single(&a.text));
                    r["raw_text"] = json!(raw(&a.text));
                    place(
                        &mut r,
                        c.block_content_location.x,
                        c.block_content_location.y,
                    );
                    push(out, "texts", r);
                }
            }
        }
        EntityType::Tolerance(t) => {
            long(out, &t.text);
            row["kind"] = json!("TOLERANCE");
            row["text"] = json!(mtext(&t.text));
            row["raw_text"] = json!(raw(&t.text));
            place(&mut row, t.insertion_point.x, t.insertion_point.y);
            push(out, "texts", row);
        }
        EntityType::AttributeDefinition(a) => {
            // In a block only a constant attribute is drawn; alone in a layout its tag is.
            let value = match block {
                Some(_) if a.flags.constant => a.default_value.as_str(),
                Some(_) => "",
                None => a.tag.as_str(),
            };
            if !value.is_empty() {
                long(out, value);
                row["kind"] = json!(if block.is_some() {
                    "CONSTANT_ATTRIBUTE"
                } else {
                    "ATTDEF"
                });
                row["tag"] = json!(a.tag);
                row["text"] = json!(single(value));
                row["raw_text"] = json!(raw(value));
                place(&mut row, a.insertion_point.x, a.insertion_point.y);
                row["height"] = json!(a.height);
                text_style(doc, &a.text_style, &mut row);
                push(out, "texts", row);
            }
        }
        EntityType::RasterImage(i) => {
            row["kind"] = json!("IMAGE");
            place(&mut row, i.insertion_point.x, i.insertion_point.y);
            let def = i.definition_handle.and_then(|h| doc.objects.get(&h));
            if let Some(ObjectType::ImageDefinition(def)) = def {
                row["path"] = json!(raw(&def.file_name));
            }
            push(out, "references", row);
        }
        EntityType::Underlay(u) => {
            row["kind"] = json!(format!("{:?}", u.underlay_type));
            place(&mut row, u.insertion_point.x, u.insertion_point.y);
            if let Some(ObjectType::UnderlayDefinition(def)) = doc.objects.get(&u.definition_handle)
            {
                row["path"] = json!(raw(&def.file_path));
            }
            push(out, "references", row);
        }
        _ => {}
    }
}

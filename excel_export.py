from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence
from xml.sax.saxutils import escape


_INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return _INVALID_XML_CHARS.sub("", text)


def _xml_text(value: Any) -> str:
    return escape(_clean_text(value), {'"': "&quot;"})


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _cell_xml(row_number: int, column_number: int, value: Any, style: int = 0) -> str:
    ref = f"{_column_name(column_number)}{row_number}"
    style_attr = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{style_attr}/>'
    if _is_number(value):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{_xml_text(value)}</t></is></c>'


def _row_xml(row_number: int, values: Sequence[Any], styles: Sequence[int] | None = None) -> str:
    cells = []
    for column_number, value in enumerate(values, start=1):
        style = styles[column_number - 1] if styles and column_number - 1 < len(styles) else 0
        cells.append(_cell_xml(row_number, column_number, value, style))
    return f'<row r="{row_number}">{"".join(cells)}</row>'


def _columns_xml(widths: Sequence[float]) -> str:
    if not widths:
        return ""
    cols = [
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    ]
    return f"<cols>{''.join(cols)}</cols>"


def _merge_xml(ranges: Sequence[str]) -> str:
    if not ranges:
        return ""
    refs = "".join(f'<mergeCell ref="{ref}"/>' for ref in ranges)
    return f'<mergeCells count="{len(ranges)}">{refs}</mergeCells>'


def _worksheet_xml(
    rows: Sequence[Sequence[Any]],
    *,
    row_styles: Dict[int, Sequence[int]] | None = None,
    widths: Sequence[float] | None = None,
    merges: Sequence[str] | None = None,
    freeze_row: int | None = None,
) -> str:
    row_styles = row_styles or {}
    sheet_view = '<sheetView workbookViewId="0"/>'
    if freeze_row:
        top_left = f"A{freeze_row + 1}"
        sheet_view = (
            '<sheetView workbookViewId="0">'
            f'<pane ySplit="{freeze_row}" topLeftCell="{top_left}" activePane="bottomLeft" state="frozen"/>'
            "</sheetView>"
        )
    sheet_rows = [
        _row_xml(row_number, values, row_styles.get(row_number))
        for row_number, values in enumerate(rows, start=1)
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheetViews>{sheet_view}</sheetViews>"
        f"{_columns_xml(widths or [])}"
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        f"{_merge_xml(merges or [])}"
        "</worksheet>"
    )


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="2">
    <numFmt numFmtId="164" formatCode="0.00%"/>
    <numFmt numFmtId="165" formatCode="0.0000"/>
  </numFmts>
  <fonts count="4">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="18"/><color rgb="FFF5C451"/><name val="Calibri"/></font>
    <font><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
  </fonts>
  <fills count="4">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF171717"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF2A2A2A"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left/><right/><top/><bottom style="thin"><color rgb="FFF5C451"/></bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="6">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def _workbook_xml(sheet_names: Sequence[str]) -> str:
    sheets = "".join(
        f'<sheet name="{_xml_text(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets>"
        "</workbook>"
    )


def _workbook_rels_xml(sheet_count: int) -> str:
    rels = [
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    ]
    rels.append(
        f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(rels)}"
        "</Relationships>"
    )


def _content_types_xml(sheet_count: int) -> str:
    sheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f"{sheets}"
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _write_xlsx(output: Path, worksheets: Dict[str, str]) -> None:
    sheet_names = list(worksheets)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(sheet_names)))
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml(sheet_names))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheet_names)))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, xml in enumerate(worksheets.values(), start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", xml)


def _repeat(style: int, count: int) -> List[int]:
    return [style] * count


def export_marks_workbook(
    output_path: str | Path,
    *,
    exam_title: str,
    batch_id: str,
    answer_key: Dict[int, str],
    records: List[Dict[str, Any]],
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    marks_headers = [
        "Class", "Roll", "Student Name", "Section", "Marks Obtained",
        "Total Marks", "Percentage", "Negative Marks", "Bonus Marks",
        "Correct", "Incorrect", "Multiple", "Blank", "Low Confidence",
        "Faulty Bonus", "Dropped Bonus", "Review Required", "Source File",
        "Page", "Alignment Confidence", "Output Folder",
    ]
    marks_rows: List[List[Any]] = [
        [exam_title or "Exam Results"],
        [f"Batch: {batch_id}"],
        [],
        marks_headers,
    ]
    for row in records:
        evaluation = row.get("evaluation") or {}
        counts = evaluation.get("counts") or {}
        marks_rows.append([
            row.get("class_name", ""),
            row.get("roll", ""),
            row.get("name", ""),
            row.get("section", ""),
            row["score"],
            row["total_questions"],
            row["percentage"] / 100.0,
            evaluation.get("total_negative_marks", 0),
            evaluation.get("bonus_marks", 0),
            counts.get("CORRECT", 0),
            counts.get("INCORRECT", 0),
            counts.get("MULTIPLE", 0),
            counts.get("BLANK", 0),
            counts.get("LOW_CONFIDENCE", 0),
            counts.get("FAULTY_BONUS", 0),
            counts.get("DROPPED_BONUS", 0),
            "Yes" if row["review_required"] else "No",
            row["source_file"],
            row["page_number"],
            row["alignment_confidence"],
            row["output_folder"],
        ])

    marks_styles = {
        1: _repeat(1, len(marks_headers)),
        2: _repeat(2, len(marks_headers)),
        4: _repeat(3, len(marks_headers)),
    }
    for row_number in range(5, len(marks_rows) + 1):
        styles = _repeat(0, len(marks_headers))
        styles[6] = 4
        styles[19] = 5
        marks_styles[row_number] = styles

    detail_headers = [
        "Class", "Roll", "Student Name", "Question", "Student Answer",
        "Detected Options", "Correct Answer", "Status", "Positive Mark",
        "Negative Mark", "Final Mark", "Confidence", "Manual Review",
    ]
    detail_rows: List[List[Any]] = [detail_headers]
    for row in records:
        for question in sorted(answer_key):
            key_answer = answer_key[question]
            if not key_answer:
                continue
            answer = row.get("answers", {}).get(str(question), {})
            response = (row.get("evaluation") or {}).get("responses", {}).get(str(question), {})
            selected = answer.get("selected_option")
            detail_rows.append([
                row.get("class_name", ""),
                row.get("roll", ""),
                row.get("name", ""),
                question,
                selected or "",
                ", ".join(response.get("detected_options") or answer.get("detected_options") or []),
                response.get("correct_option") or key_answer,
                response.get("response_status") or answer.get("status", ""),
                response.get("awarded_marks", 0),
                response.get("penalty_marks", 0),
                response.get("final_marks", 0),
                response.get("confidence_score", answer.get("confidence", 0.0)),
                "Yes" if response.get("requires_manual_review") or answer.get("requires_manual_review") else "No",
            ])

    detail_styles = {1: _repeat(3, len(detail_headers))}
    for row_number in range(2, len(detail_rows) + 1):
        styles = _repeat(0, len(detail_headers))
        styles[10] = 5
        detail_styles[row_number] = styles

    key_rows: List[List[Any]] = [["Question", "Correct Answer"]]
    key_rows.extend([[question, answer_key[question]] for question in sorted(answer_key) if answer_key[question]])

    worksheets = {
        "Marks": _worksheet_xml(
            marks_rows,
            row_styles=marks_styles,
            widths=[15, 10, 24, 12, 16, 13, 13, 16, 12, 10, 10, 10, 10, 16, 14, 14, 18, 26, 9, 20, 42],
            merges=["A1:U1", "A2:U2"],
            freeze_row=4,
        ),
        "Answer Details": _worksheet_xml(
            detail_rows,
            row_styles=detail_styles,
            widths=[15, 10, 24, 10, 16, 18, 16, 14, 14, 12, 12, 14],
            freeze_row=1,
        ),
        "Answer Key": _worksheet_xml(
            key_rows,
            row_styles={1: _repeat(3, 2)},
            widths=[18, 18],
            freeze_row=1,
        ),
    }
    _write_xlsx(output, worksheets)
    return output

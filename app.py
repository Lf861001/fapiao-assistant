from __future__ import annotations

import io
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from pypdf import PdfReader, PdfWriter
from werkzeug.utils import secure_filename


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    APP_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    APP_DIR = BASE_DIR

OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / ".tmp_uploads"

COMPANIES = {
    "1219": "柯马(上海)工程有限公司",
    "1226": "柯马(上海)国际贸易有限公司",
    "1227": "柯昆(昆山)自动化有限公司",
}

app = Flask(__name__, template_folder=str(APP_DIR / "templates"))
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024

INVOICE_NUMBER_PATTERN = re.compile(r"(?<!\d)(\d{20})(?!\d)")


def prepare_folders() -> None:
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def clean_part(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", "", value)
    return re.sub(r'[\\/:*?"<>|]', "_", value)


def count_named_files(files) -> int:
    return sum(1 for file in files if file and file.filename)


def extract_invoice_number_from_filename(file_name: str) -> str | None:
    match = INVOICE_NUMBER_PATTERN.search(file_name)
    return match.group(1) if match else None


def compress_invoice_numbers(invoice_numbers: list[str]) -> str:
    if any(not item.isdigit() for item in invoice_numbers):
        return "&".join(invoice_numbers)

    indexed_numbers = sorted((int(item), item) for item in invoice_numbers)
    groups: list[list[tuple[int, str]]] = []
    current_group: list[tuple[int, str]] = []

    for invoice in indexed_numbers:
        if not current_group or invoice[0] == current_group[-1][0] + 1:
            current_group.append(invoice)
            continue
        groups.append(current_group)
        current_group = [invoice]

    if current_group:
        groups.append(current_group)

    invoice_parts: list[str] = []
    for group in groups:
        first_invoice = group[0][1]
        last_invoice = group[-1][1]
        if len(group) == 1:
            invoice_parts.append(first_invoice)
        else:
            invoice_parts.append(f"{first_invoice}-{last_invoice[-2:]}")

    return "&".join(invoice_parts)


def validate_pdf_storage(files, group_name: str, contract_dir: Path) -> list[Path]:
    saved_paths: list[Path] = []
    for index, file in enumerate(files, start=1):
        if not file or not file.filename:
            continue
        if not file.filename.lower().endswith(".pdf"):
            raise ValueError(f"{group_name} 只能上传 PDF 文件。")

        original_name = secure_filename(file.filename) or f"{group_name}_{index}.pdf"
        saved_path = contract_dir / f"{group_name}_{index:02d}_{original_name}"
        file.save(saved_path)

        try:
            PdfReader(str(saved_path))
        except Exception as exc:
            raise ValueError(f"{file.filename} 不是有效的 PDF 文件。") from exc

        saved_paths.append(saved_path)

    return saved_paths


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> None:
    writer = PdfWriter()
    for pdf_path in pdf_paths:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            writer.add_page(page)

    with output_path.open("wb") as output_file:
        writer.write(output_file)


def find_duplicate_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    duplicate_set: set[str] = set()
    for item in items:
        if item in seen and item not in duplicate_set:
            duplicates.append(item)
            duplicate_set.add(item)
            continue
        seen.add(item)
    return duplicates


def parse_output_file_info(file_path: Path) -> dict[str, str] | None:
    stem_parts = file_path.stem.split("_", 3)
    if len(stem_parts) != 4:
        return None
    company_code, supplier_code, po_number, invoice_part = stem_parts
    return {
        "companyCode": company_code,
        "supplierCode": supplier_code,
        "poNumber": po_number,
        "invoicePart": invoice_part,
        "fileName": file_path.name,
    }


def collect_output_state() -> dict[str, object]:
    invoice_numbers: set[str] = set()
    po_numbers: set[str] = set()
    files: list[dict[str, str]] = []

    for pdf_file in sorted(OUTPUT_DIR.glob("*.pdf")):
        file_info = parse_output_file_info(pdf_file)
        files.append({"name": pdf_file.name})
        if not file_info:
            continue
        po_numbers.add(file_info["poNumber"])
        for match in INVOICE_NUMBER_PATTERN.findall(pdf_file.name):
            invoice_numbers.add(match)

    return {
        "invoiceNumbers": sorted(invoice_numbers),
        "poNumbers": sorted(po_numbers),
        "files": files,
    }


def clear_generated_files() -> None:
    if not OUTPUT_DIR.exists():
        return
    for file_path in OUTPUT_DIR.glob("*"):
        if file_path.is_file():
            file_path.unlink(missing_ok=True)


@app.route("/")
def index():
    return render_template("index.html", companies=COMPANIES)


@app.route("/api/output-state")
def output_state():
    state = collect_output_state()
    return jsonify({"ok": True, **state})


@app.route("/api/generate", methods=["POST"])
def generate_pdf():
    company_code = clean_part(request.form.get("companyCode", ""))
    supplier_code = clean_part(request.form.get("supplierCode", ""))
    po_number = clean_part(request.form.get("poNumber", ""))

    if company_code not in COMPANIES:
        return jsonify({"ok": False, "message": "请选择有效的公司代码。"}), 400
    if not supplier_code or not po_number:
        return jsonify({"ok": False, "message": "请填写供应商代码和合同号/PO。"}), 400

    invoice_files = request.files.getlist("invoiceFiles")
    delivery_files = request.files.getlist("deliveryFiles")
    if not invoice_files or not delivery_files:
        return jsonify({"ok": False, "message": "请上传发票 PDF 和送货单 PDF。"}), 400

    invoice_file_count = count_named_files(invoice_files)
    if not invoice_file_count:
        return jsonify({"ok": False, "message": "请至少上传一个发票 PDF。"}), 400

    invoice_numbers: list[str] = []
    for file in invoice_files:
        if not file or not file.filename:
            continue
        invoice_number = extract_invoice_number_from_filename(file.filename)
        if not invoice_number:
            return jsonify(
                {
                    "ok": False,
                    "message": f"发票 PDF 文件名中必须包含连续 20 位数字发票号：{file.filename}",
                }
            ), 400
        invoice_numbers.append(invoice_number)

    duplicate_in_upload = find_duplicate_items(invoice_numbers)
    if duplicate_in_upload:
        return jsonify(
            {
                "ok": False,
                "message": f"本次上传的发票号不能重复：{'、'.join(duplicate_in_upload)}",
            }
        ), 400

    output_state_data = collect_output_state()
    existing_invoice_numbers = set(output_state_data["invoiceNumbers"])
    duplicate_with_output = [number for number in invoice_numbers if number in existing_invoice_numbers]
    if duplicate_with_output:
        return jsonify(
            {
                "ok": False,
                "message": f"这些发票号已在输出文件夹中生成过递交 PDF，不能重复上传：{'、'.join(duplicate_with_output)}",
            }
        ), 400

    existing_po_numbers = set(output_state_data["poNumbers"])
    if po_number in existing_po_numbers:
        return jsonify({"ok": False, "message": f"合同号重复：{po_number}"}), 400

    with tempfile.TemporaryDirectory(dir=TEMP_DIR) as contract_temp:
        contract_dir = Path(contract_temp)
        try:
            saved_invoices = validate_pdf_storage(invoice_files, "发票", contract_dir)
            saved_deliveries = validate_pdf_storage(delivery_files, "送货单", contract_dir)
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

        if not saved_invoices or not saved_deliveries:
            return jsonify({"ok": False, "message": "请上传发票 PDF 和送货单 PDF。"}), 400

        invoice_part = compress_invoice_numbers(invoice_numbers)
        output_name = f"{company_code}_{supplier_code}_{po_number}_{invoice_part}.pdf"
        output_path = OUTPUT_DIR / output_name

        try:
            merge_pdfs([*saved_invoices, *saved_deliveries], output_path)
        except Exception as exc:
            return jsonify({"ok": False, "message": f"PDF 合并失败：{exc}"}), 500

    return jsonify(
        {
            "ok": True,
            "message": "已生成递交文件。",
            "fileName": output_path.name,
            "downloadUrl": f"/output/{output_path.name}",
        }
    )


@app.route("/api/files")
def list_files():
    files = [{"name": path.name} for path in sorted(OUTPUT_DIR.glob("*.pdf"))]
    return jsonify({"ok": True, "files": files})


@app.route("/api/files/<path:file_name>", methods=["DELETE"])
def delete_file(file_name: str):
    file_path = OUTPUT_DIR / file_name
    if not file_path.is_file():
        return jsonify({"ok": False, "message": "文件不存在。"}), 404

    file_path.unlink(missing_ok=True)
    return jsonify({"ok": True, "message": f"已删除文件：{file_path.name}"})


@app.route("/output/<path:file_name>")
def download_file(file_name: str):
    file_path = OUTPUT_DIR / file_name
    if not file_path.is_file():
        return jsonify({"ok": False, "message": "文件不存在。"}), 404
    return send_file(file_path, as_attachment=True, download_name=file_path.name)


@app.route("/api/download-all")
def download_all():
    pdf_files = sorted(OUTPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        return jsonify({"ok": False, "message": "输出文件夹中还没有 PDF 文件。"}), 400

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for pdf_file in pdf_files:
            archive.write(pdf_file, arcname=pdf_file.name)

    zip_buffer.seek(0)
    clear_generated_files()
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name="fapiao_output.zip",
        mimetype="application/zip",
    )


if __name__ == "__main__":
    prepare_folders()
    app.run(host="127.0.0.1", port=5000, debug=True)

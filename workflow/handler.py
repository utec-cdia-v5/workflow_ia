import base64
import csv
import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import boto3
from botocore.exceptions import BotoCoreError, ClientError

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"
CSV_ENCODING = "utf-8-sig"

stepfunctions_client = boto3.client("stepfunctions")
s3_client = boto3.client("s3")
dynamodb_resource = boto3.resource("dynamodb")


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_response(status_code: int, payload: Any) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(payload, ensure_ascii=False),
    }


def parse_request_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")
    if body is None or body == "":
        return {}

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    if isinstance(body, dict):
        return body

    try:
        return json.loads(body)
    except json.JSONDecodeError as error:
        raise ValueError("El body no contiene JSON valido.") from error


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"La variable de entorno {name} no esta configurada.")
    return value


def parse_s3_uri(link: str) -> Tuple[str, str]:
    parsed = urlparse(link)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError(f"Ruta S3 invalida: {link}")

    bucket = parsed.netloc
    key = unquote(parsed.path.lstrip("/"))
    return bucket, key


def normalize_folder_prefix(prefix: str) -> str:
    if prefix == "":
        return prefix
    return prefix if prefix.endswith("/") else f"{prefix}/"


def extract_start_inputs(payload: Dict[str, Any]) -> Tuple[str, str, str]:
    instructions_s3_link = (
        payload.get("instructions_s3_link")
        or payload.get("instrucciones_s3_link")
        or payload.get("instructionsLink")
    )
    content_s3_folder_link = (
        payload.get("content_s3_folder_link")
        or payload.get("contents_s3_folder_link")
        or payload.get("content_folder_s3_link")
        or payload.get("folder_s3_link")
        or payload.get("content_s3_prefix")
    )
    recipient_email = (
        payload.get("email")
        or payload.get("recipient_email")
        or payload.get("correo")
    )

    if not instructions_s3_link or not content_s3_folder_link or not recipient_email:
        raise ValueError(
            "Debes enviar instructions_s3_link, content_s3_folder_link y email."
        )

    _, instructions_key = parse_s3_uri(instructions_s3_link)
    if not instructions_key:
        raise ValueError("instructions_s3_link debe apuntar a un archivo markdown.")

    parse_s3_uri(content_s3_folder_link)

    if "@" not in recipient_email:
        raise ValueError("El campo email no parece valido.")

    return instructions_s3_link, content_s3_folder_link, recipient_email


def post_json(
    url: str,
    payload: Any,
    headers: Dict[str, str],
    timeout_seconds: int,
) -> Tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=headers, method="POST")

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset, errors="replace")
            return response.getcode(), body
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} al invocar {url}: {error_body}") from error
    except URLError as error:
        raise RuntimeError(f"No se pudo conectar con {url}: {error.reason}") from error


def call_agente_ia_api(instructions_s3_link: str, content_s3_link: str) -> Any:
    agente_api_url = require_env("AGENTE_IA_API_URL")
    request_payload = {
        "instructions_s3_link": instructions_s3_link,
        "content_s3_link": content_s3_link,
    }

    _, response_body = post_json(
        url=agente_api_url,
        payload=request_payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "workflow-ia/1.0",
        },
        timeout_seconds=90,
    )

    if response_body == "":
        return {}

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as error:
        raise RuntimeError("El API de agente no devolvio JSON valido.") from error


def start_workflow(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        payload = parse_request_body(event)
        instructions_s3_link, content_s3_folder_link, recipient_email = extract_start_inputs(
            payload
        )
    except ValueError as error:
        return json_response(400, {"error": str(error)})

    try:
        state_machine_arn = require_env("WORKFLOW_STATE_MACHINE_ARN")
        execution_name = (
            f"workflow-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-"
            f"{uuid.uuid4().hex[:8]}"
        )
        execution_input = {
            "instructions_s3_link": instructions_s3_link,
            "content_s3_folder_link": content_s3_folder_link,
            "email": recipient_email,
            "workflow_execution_id": execution_name,
            "requested_at": iso_utc_now(),
        }
        response = stepfunctions_client.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(execution_input, ensure_ascii=False),
        )
    except (RuntimeError, ClientError, BotoCoreError) as error:
        return json_response(
            502,
            {
                "error": "No fue posible iniciar el workflow.",
                "detail": str(error),
            },
        )

    return json_response(
        202,
        {
            "message": "Workflow iniciado de forma asincrona.",
            "executionArn": response.get("executionArn"),
            "executionName": execution_name,
            "startDate": response.get("startDate").isoformat()
            if response.get("startDate")
            else None,
        },
    )


def list_markdown_files(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    instructions_s3_link = event.get("instructions_s3_link")
    content_s3_folder_link = event.get("content_s3_folder_link")
    recipient_email = event.get("email")
    workflow_execution_id = event.get("workflow_execution_id")

    if (
        not instructions_s3_link
        or not content_s3_folder_link
        or not recipient_email
        or not workflow_execution_id
    ):
        raise ValueError("Input incompleto para listar archivos markdown.")

    content_bucket, content_prefix_raw = parse_s3_uri(content_s3_folder_link)
    content_prefix = normalize_folder_prefix(content_prefix_raw)

    files: List[Dict[str, str]] = []
    paginator = s3_client.get_paginator("list_objects_v2")

    try:
        for page in paginator.paginate(Bucket=content_bucket, Prefix=content_prefix):
            for item in page.get("Contents", []):
                content_key = item.get("Key", "")
                if not content_key or content_key.endswith("/"):
                    continue
                lower = content_key.lower()
                if lower.endswith(".md") or lower.endswith(".markdown"):
                    files.append(
                        {
                            "content_key": content_key,
                            "content_s3_link": f"s3://{content_bucket}/{content_key}",
                            "file_name": os.path.basename(content_key),
                        }
                    )
    except (ClientError, BotoCoreError) as error:
        raise RuntimeError(f"No fue posible listar objetos en S3: {error}") from error

    files.sort(key=lambda item: item["content_key"])

    if not files:
        raise RuntimeError("No se encontraron archivos markdown para evaluar.")

    return {
        "instructions_s3_link": instructions_s3_link,
        "content_s3_folder_link": content_s3_folder_link,
        "content_bucket": content_bucket,
        "content_prefix": content_prefix,
        "email": recipient_email,
        "workflow_execution_id": workflow_execution_id,
        "files": files,
        "total_files": len(files),
    }


def evaluate_file(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    instructions_s3_link = event.get("instructions_s3_link")
    content_s3_link = event.get("content_s3_link")
    workflow_execution_id = event.get("workflow_execution_id")

    if not instructions_s3_link or not content_s3_link or not workflow_execution_id:
        raise ValueError("Input incompleto para evaluar archivo.")

    _, content_key = parse_s3_uri(content_s3_link)
    file_name = event.get("file_name") or os.path.basename(content_key)

    evaluation_result = call_agente_ia_api(
        instructions_s3_link=instructions_s3_link,
        content_s3_link=content_s3_link,
    )

    table_name = require_env("RESULTS_TABLE_NAME")
    table = dynamodb_resource.Table(table_name)

    item = {
        "execution_id": workflow_execution_id,
        "content_key": content_key,
        "file_name": file_name,
        "content_s3_link": content_s3_link,
        "evaluated_at": iso_utc_now(),
        "result_json": json.dumps(evaluation_result, ensure_ascii=False),
    }

    try:
        table.put_item(Item=item)
    except (ClientError, BotoCoreError) as error:
        raise RuntimeError(f"No fue posible guardar resultado en DynamoDB: {error}") from error

    return {
        "execution_id": workflow_execution_id,
        "file_name": file_name,
        "content_key": content_key,
        "content_s3_link": content_s3_link,
        "evaluation_result": evaluation_result,
    }


def csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def collect_result_columns(evaluations: List[Dict[str, Any]]) -> List[str]:
    columns = set()
    for evaluation in evaluations:
        result = evaluation.get("evaluation_result")
        if isinstance(result, dict):
            for key in result.keys():
                columns.add(str(key))
        else:
            columns.add("resultado")

    if not columns:
        columns.add("resultado")

    return sorted(columns)


def build_csv_report(evaluations: List[Dict[str, Any]], columns: List[str]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")

    header = ["archivo", "ruta_s3"] + columns
    writer.writerow(header)

    for evaluation in evaluations:
        file_name = evaluation.get("file_name") or evaluation.get("content_key") or "sin_nombre"
        content_s3_link = evaluation.get("content_s3_link", "")
        result = evaluation.get("evaluation_result")

        row = [csv_cell(file_name), csv_cell(content_s3_link)]
        for column in columns:
            if isinstance(result, dict):
                row.append(csv_cell(result.get(column)))
            elif column == "resultado":
                row.append(csv_cell(result))
            else:
                row.append("")

        writer.writerow(row)

    return output.getvalue()


def generate_report(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    recipient_email = event.get("email")
    content_bucket = event.get("content_bucket")
    workflow_execution_id = event.get("workflow_execution_id", "workflow-sin-id")
    evaluations = event.get("evaluations", [])

    if not recipient_email or not content_bucket:
        raise ValueError("Input incompleto para generar reporte.")

    if not isinstance(evaluations, list) or not evaluations:
        raise RuntimeError("No hay evaluaciones para crear el reporte CSV.")

    columns = collect_result_columns(evaluations)

    csv_report = build_csv_report(evaluations, columns)
    csv_bytes = csv_report.encode(CSV_ENCODING)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_file_name = f"resultado-{workflow_execution_id}-{timestamp}.csv"
    report_key = f"resultados/{report_file_name}"

    try:
        s3_client.put_object(
            Bucket=content_bucket,
            Key=report_key,
            Body=csv_bytes,
            ContentType="text/csv; charset=utf-8",
        )
    except (ClientError, BotoCoreError) as error:
        raise RuntimeError(f"No fue posible guardar el reporte en S3: {error}") from error

    return {
        "email": recipient_email,
        "workflow_execution_id": workflow_execution_id,
        "files_processed": len(evaluations),
        "report_bucket": content_bucket,
        "report_key": report_key,
        "report_s3_link": f"s3://{content_bucket}/{report_key}",
        "report_file_name": report_file_name,
        "attachment_base64": base64.b64encode(csv_bytes).decode(
            "ascii"
        ),
    }


def send_email(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    recipient_email = event.get("email")
    report_s3_link = event.get("report_s3_link")
    report_file_name = event.get("report_file_name", "resultados.csv")
    attachment_base64 = event.get("attachment_base64")
    workflow_execution_id = event.get("workflow_execution_id", "workflow-sin-id")
    files_processed = event.get("files_processed", 0)

    if not recipient_email or not report_s3_link or not attachment_base64:
        raise ValueError("Input incompleto para enviar correo.")

    sendgrid_api_key = require_env("SENDGRID_API_KEY")
    sendgrid_from_email = require_env("SENDGRID_FROM_EMAIL")
    sendgrid_from_name = os.getenv("SENDGRID_FROM_NAME", "Workflow IA")

    payload = {
        "personalizations": [{"to": [{"email": recipient_email}]}],
        "from": {
            "email": sendgrid_from_email,
            "name": sendgrid_from_name,
        },
        "subject": f"Resultados workflow IA {workflow_execution_id}",
        "content": [
            {
                "type": "text/plain",
                "value": (
                    "El workflow finalizo correctamente. "
                    f"Archivos evaluados: {files_processed}. "
                    f"Reporte CSV almacenado en {report_s3_link}."
                ),
            }
        ],
        "attachments": [
            {
                "content": attachment_base64,
                "filename": report_file_name,
                "type": "text/csv",
                "disposition": "attachment",
            }
        ],
    }

    status_code, _ = post_json(
        url=SENDGRID_API_URL,
        payload=payload,
        headers={
            "Authorization": f"Bearer {sendgrid_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "workflow-ia/1.0",
        },
        timeout_seconds=30,
    )

    if status_code not in {200, 202}:
        raise RuntimeError(f"SendGrid devolvio estado inesperado: {status_code}")

    return {
        "message": "Correo enviado correctamente.",
        "email": recipient_email,
        "report_s3_link": report_s3_link,
        "files_processed": files_processed,
        "workflow_execution_id": workflow_execution_id,
    }

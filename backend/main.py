"""
main.py

FastAPI backend for the AI Medical Report Explainer.

Endpoints:
    POST /api/upload        -> upload a report (PDF/image), get full analysis
    POST /api/chat          -> ask a question about a specific report
    GET  /api/report/{id}   -> fetch a stored report's analysis
    GET  /api/reports       -> list all reports (for dashboard trend chart)
    GET  /api/health        -> healthcheck + basic app info

Configuration is centralized in config.py / .env (see .env.example).

Run with:
    uvicorn main:app --reload --host $HOST --port $PORT
"""

import os
import shutil
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
from utils.logger import get_logger
from utils.rate_limit import RateLimitMiddleware
from nlp.extractor import extract_text
from nlp.medical_parser import parse_parameters
from nlp.summarizer import summarize_report
from nlp.chatbot import answer_question
from ml.disease_predictor import analyze_risks, compute_health_score
from utils.db import init_db, save_report, get_report, get_all_reports

log = get_logger(__name__)

REPORTS_DIR = (
    settings.reports_dir
    if os.path.isabs(settings.reports_dir)
    else os.path.join(os.path.dirname(__file__), settings.reports_dir)
)
os.makedirs(REPORTS_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info(f"{settings.app_name} v{settings.app_version} starting in '{settings.environment}' mode")
    log.info(f"CORS origins: {settings.cors_origin_list}")
    log.info(f"Reports dir: {REPORTS_DIR}")
    yield
    log.info(f"{settings.app_name} shutting down")


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    log.warning(f"Validation error on {request.url.path}: {exc}")
    return JSONResponse(status_code=422, content={"detail": "Invalid request data.", "errors": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception(f"Unhandled error on {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our end. Please try again."})


class ChatRequest(BaseModel):
    question: str
    report_id: int | None = None


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@app.post("/api/upload")
async def upload_report(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.allowed_extension_set:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(settings.allowed_extension_set))}",
        )

    # Enforce max upload size (read in chunks so we never buffer an oversized
    # file fully into memory before rejecting it).
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = os.path.join(REPORTS_DIR, saved_name)

    total_written = 0
    try:
        with open(saved_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                total_written += len(chunk)
                if total_written > max_bytes:
                    out.close()
                    os.remove(saved_path)
                    raise HTTPException(
                        413, f"File too large. Max allowed size is {settings.max_upload_size_mb}MB."
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to save uploaded file")
        raise HTTPException(500, f"Failed to save uploaded file: {e}")

    log.info(f"Saved upload '{file.filename}' -> {saved_name} ({total_written} bytes)")

    try:
        raw_text = extract_text(saved_path)
    except Exception as e:
        log.exception("Text extraction failed")
        raise HTTPException(500, f"Failed to extract text: {e}")
    finally:
        if settings.delete_files_after_processing and os.path.exists(saved_path):
            os.remove(saved_path)

    parameters = parse_parameters(raw_text)
    if not parameters:
        raise HTTPException(
            422,
            "Couldn't detect any recognizable medical parameters in this report. "
            "Try a clearer scan or a different file.",
        )

    summary = summarize_report(parameters)
    risks = analyze_risks(parameters)
    health_score = compute_health_score(parameters)
    report_id = save_report(file.filename, parameters, risks, health_score)

    log.info(f"Report #{report_id} processed: {len(parameters)} parameters, score={health_score}")

    return {
        "report_id": report_id,
        "filename": file.filename,
        "parameters": parameters,
        "summary": summary,
        "risks": risks,
        "health_score": health_score,
        "disclaimer": (
            "This report is for educational purposes only and is not a substitute "
            "for professional medical advice, diagnosis, or treatment."
        ),
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    report_params = None
    if req.report_id is not None:
        report = get_report(req.report_id)
        if report:
            report_params = report["parameters"]

    answer = answer_question(req.question, report_params)
    return {"answer": answer}


@app.get("/api/report/{report_id}")
def get_report_endpoint(report_id: int):
    report = get_report(report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@app.get("/api/reports")
def list_reports():
    """Used by the dashboard to plot a health-score trend across reports."""
    return get_all_reports()

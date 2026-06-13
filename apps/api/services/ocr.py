from __future__ import annotations

import io
import logging
import shutil
import time
from typing import Any

import fitz
import httpx

from config import settings

logger = logging.getLogger(__name__)

# Azure Computer Vision Read limits each HTTP request body to 4 MB.
AZURE_MAX_REQUEST_BYTES = 3_900_000

PageRange = tuple[int, int]  # 0-based inclusive start/end page indices in source PDF


class OcrNotAvailableError(RuntimeError):
    """Raised when the configured OCR provider is not set up locally."""


class OcrProcessingError(RuntimeError):
    """Raised when OCR runs but fails (API error, timeout, oversized input, etc.)."""


def get_ocr_provider() -> str:
    provider = settings.ocr_provider.strip().lower()
    if provider in ("tesseract", "azure"):
        return provider
    return "tesseract"


def _configure_tesseract() -> None:
    import pytesseract

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def is_tesseract_available() -> bool:
    if shutil.which("tesseract") is None and not settings.tesseract_cmd:
        return False
    try:
        import pytesseract

        _configure_tesseract()
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def is_azure_vision_available() -> bool:
    return bool(settings.azure_vision_endpoint.strip() and settings.azure_vision_key.strip())


def is_ocr_available() -> bool:
    provider = get_ocr_provider()
    if provider == "azure":
        return is_azure_vision_available()
    return is_tesseract_available()


def ocr_unavailable_message() -> str:
    provider = get_ocr_provider()
    if provider == "azure":
        return (
            "Azure Computer Vision is not configured. "
            "Set AZURE_VISION_ENDPOINT and AZURE_VISION_KEY."
        )
    return "Tesseract OCR is not installed. On macOS run: brew install tesseract"


def ocr_pdf(
    path: str,
    *,
    max_pages: int | None = None,
    lang: str | None = None,
) -> list[dict[str, Any]]:
    provider = get_ocr_provider()
    page_limit = max_pages or settings.ocr_max_pages

    if provider == "azure":
        return _ocr_pdf_azure(path, max_pages=page_limit)

    return _ocr_pdf_tesseract(path, max_pages=page_limit, lang=lang)


def _ocr_pdf_tesseract(
    path: str,
    *,
    max_pages: int,
    lang: str | None,
) -> list[dict[str, Any]]:
    if not is_tesseract_available():
        raise OcrNotAvailableError(ocr_unavailable_message())

    import pytesseract
    from PIL import Image

    _configure_tesseract()
    ocr_lang = lang or settings.ocr_lang

    doc = fitz.open(path)
    pages: list[dict[str, Any]] = []

    try:
        for index, page in enumerate(doc):
            if index >= max_pages:
                break

            pixmap = page.get_pixmap(dpi=settings.ocr_dpi)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            text = pytesseract.image_to_string(image, lang=ocr_lang).strip()
            if text:
                pages.append(
                    {
                        "text": text,
                        "page": index + 1,
                        "metadata": {"source": "tesseract_ocr"},
                    }
                )
    finally:
        doc.close()

    return pages


def _page_image_for_azure(page: fitz.Page) -> tuple[bytes, str]:
    """Render one PDF page as a compressed image under Azure's 4 MB request limit."""
    from PIL import Image

    dpi_candidates = [settings.ocr_dpi, 150, 120, 96, 72]
    tried: set[int] = set()

    for dpi in dpi_candidates:
        if dpi in tried:
            continue
        tried.add(dpi)

        pixmap = page.get_pixmap(dpi=dpi)
        png_bytes = pixmap.tobytes("png")
        if len(png_bytes) <= AZURE_MAX_REQUEST_BYTES:
            return png_bytes, "image/png"

        image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        for quality in (85, 70, 55, 40, 30):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)
            jpeg_bytes = buffer.getvalue()
            if len(jpeg_bytes) <= AZURE_MAX_REQUEST_BYTES:
                return jpeg_bytes, "image/jpeg"

    raise OcrProcessingError(
        "PDF page image is too large for Azure Read (4 MB per request). "
        "Try a lower OCR_DPI or split the PDF."
    )


def _extract_pdf_slice(doc: fitz.Document, start_index: int, end_index: int) -> bytes:
    """Extract a page range from the source PDF, preserving embedded image compression."""
    batch = fitz.open()
    try:
        batch.insert_pdf(doc, from_page=start_index, to_page=end_index)
        return batch.tobytes()
    finally:
        batch.close()


def _group_pages_into_batches(doc: fitz.Document, max_pages: int) -> list[PageRange]:
    """
    Pack pages into Azure submissions:
    - each request body must stay under 4 MB
    - F0 free tier reliably processes up to 2 PDF pages per request
    """
    limit = min(max_pages, doc.page_count)
    tier_cap = max(1, settings.azure_ocr_batch_max_pages)
    batches: list[PageRange] = []
    start = 0

    while start < limit:
        max_end = min(start + tier_cap - 1, limit - 1)
        end = max_end

        while end >= start:
            body = _extract_pdf_slice(doc, start, end)
            if len(body) <= AZURE_MAX_REQUEST_BYTES:
                break
            end -= 1

        if end < start:
            batches.append((start, start))
        else:
            batches.append((start, end))

        start = batches[-1][1] + 1

    return batches


def _ocr_pdf_azure(path: str, *, max_pages: int) -> list[dict[str, Any]]:
    if not is_azure_vision_available():
        raise OcrNotAvailableError(ocr_unavailable_message())

    endpoint = settings.azure_vision_endpoint.rstrip("/")
    analyze_url = f"{endpoint}/vision/v3.2/read/analyze"
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_vision_key,
    }

    doc = fitz.open(path)
    pages: list[dict[str, Any]] = []

    try:
        batches = _group_pages_into_batches(doc, max_pages)
        logger.info(
            "Azure OCR: %s page(s) across %s submission(s), up to %s pages/request",
            min(max_pages, doc.page_count),
            len(batches),
            settings.azure_ocr_batch_max_pages,
        )

        with httpx.Client(timeout=120.0) as client:
            for batch_index, (start_index, end_index) in enumerate(batches, start=1):
                body, content_type = _submission_body_for_range(
                    doc, start_index, end_index
                )

                batch_results = _azure_read_document(
                    client,
                    analyze_url,
                    headers,
                    body,
                    content_type,
                    batch_label=f"batch {batch_index}/{len(batches)}",
                )

                first_page = start_index + 1
                for page_result in batch_results:
                    relative_page = int(page_result.get("page", 1))
                    absolute_page = first_page + relative_page - 1
                    text = page_result.get("text", "").strip()
                    if not text:
                        continue
                    pages.append(
                        {
                            "text": text,
                            "page": absolute_page,
                            "metadata": {
                                "source": "azure_computer_vision_read",
                                "batch": batch_index,
                            },
                        }
                    )

                if settings.azure_ocr_request_delay_sec > 0:
                    time.sleep(settings.azure_ocr_request_delay_sec)
    finally:
        doc.close()

    return pages


def _submission_body_for_range(
    doc: fitz.Document,
    start_index: int,
    end_index: int,
) -> tuple[bytes, str]:
    if start_index == end_index:
        slice_bytes = _extract_pdf_slice(doc, start_index, end_index)
        if len(slice_bytes) <= AZURE_MAX_REQUEST_BYTES:
            return slice_bytes, "application/pdf"

        image_bytes, content_type = _page_image_for_azure(doc[start_index])
        return image_bytes, content_type

    slice_bytes = _extract_pdf_slice(doc, start_index, end_index)
    if len(slice_bytes) > AZURE_MAX_REQUEST_BYTES:
        raise OcrProcessingError(
            f"Azure OCR slice pages {start_index + 1}-{end_index + 1} exceeds 4 MB"
        )
    return slice_bytes, "application/pdf"


def _azure_read_document(
    client: httpx.Client,
    analyze_url: str,
    headers: dict[str, str],
    body_bytes: bytes,
    content_type: str,
    *,
    batch_label: str,
) -> list[dict[str, Any]]:
    request_headers = {**headers, "Content-Type": content_type}

    for attempt in range(settings.azure_ocr_max_retries + 1):
        response = client.post(analyze_url, headers=request_headers, content=body_bytes)

        if response.status_code == 429 and attempt < settings.azure_ocr_max_retries:
            retry_after = float(response.headers.get("Retry-After", "2"))
            logger.warning(
                "Azure OCR rate limited for %s; retrying in %.1fs",
                batch_label,
                retry_after,
            )
            time.sleep(retry_after)
            continue

        if response.status_code >= 400:
            raise OcrProcessingError(
                f"Azure Read API error for {batch_label} "
                f"({response.status_code}): {response.text[:300]}"
            )
        break
    else:
        raise OcrProcessingError(f"Azure Read API rate limit exceeded for {batch_label}")

    operation_url = response.headers.get("Operation-Location")
    if not operation_url:
        raise OcrProcessingError(
            f"Azure Read API did not return Operation-Location for {batch_label}"
        )

    result = _poll_azure_read_result(client, operation_url, headers)
    read_results = result.get("analyzeResult", {}).get("readResults", [])
    parsed: list[dict[str, Any]] = []

    for page_result in read_results:
        lines = page_result.get("lines", [])
        text = "\n".join(line.get("text", "").strip() for line in lines if line.get("text"))
        parsed.append(
            {
                "page": int(page_result.get("page", len(parsed) + 1)),
                "text": text.strip(),
            }
        )

    return parsed


def _poll_azure_read_result(
    client: httpx.Client,
    operation_url: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    deadline = time.time() + settings.azure_ocr_poll_timeout_sec

    while time.time() < deadline:
        response = client.get(operation_url, headers=headers)
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "3"))
            logger.warning("Azure OCR poll rate limited; retrying in %.1fs", retry_after)
            time.sleep(retry_after)
            continue
        if response.status_code >= 400:
            raise OcrProcessingError(
                f"Azure Read poll error ({response.status_code}): {response.text[:300]}"
            )

        payload = response.json()
        status = payload.get("status", "").lower()

        if status == "succeeded":
            return payload
        if status == "failed":
            message = payload.get("message") or "Azure Read operation failed"
            raise OcrProcessingError(message)

        time.sleep(settings.azure_ocr_poll_interval_sec)

    raise OcrProcessingError("Azure Read operation timed out")

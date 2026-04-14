#!/usr/bin/env python3
"""
Parse a PDF manual via Datalab (Marker) and write cache artifacts.

Requires:
  pip install datalab-python-sdk
  Environment variable DATALAB_API_KEY

Outputs into:
  {output_dir}/.parse-cache/
    parsed.md
    parsed.json
    images/
    metadata.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, Optional


def _require_api_key() -> str:
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        raise RuntimeError("DATALAB_API_KEY is required.")
    return api_key


def _decode_images(images: Optional[Dict[str, str]]) -> Dict[str, bytes]:
    """Datalab returns images as filename -> base64 string."""
    out: Dict[str, bytes] = {}
    if not images:
        return out
    for name, b64 in images.items():
        if not isinstance(b64, str):
            continue
        try:
            out[str(name)] = base64.b64decode(b64)
        except Exception:
            continue
    return out


def _convert_options(
    mode: str,
    *,
    force_ocr_hint: bool,
) -> Any:
    from datalab_sdk import ConvertOptions  # type: ignore

    additional: Optional[Dict[str, Any]] = None
    if force_ocr_hint:
        # API may honor this inside additional_config; harmless if ignored.
        additional = {"force_ocr": True}

    return ConvertOptions(
        mode=mode,
        output_format="markdown,json",
        disable_image_extraction=False,
        additional_config=additional,
    )


def parse_once(
    pdf_path: Path,
    mode: str,
    *,
    force_ocr_hint: bool,
    max_polls: int,
    poll_interval: int,
    request_timeout: int,
) -> Dict[str, Any]:
    _require_api_key()
    try:
        from datalab_sdk import DatalabClient  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "datalab-python-sdk is required. Install with: pip install datalab-python-sdk"
        ) from exc

    options = _convert_options(mode, force_ocr_hint=force_ocr_hint)
    client = DatalabClient(timeout=request_timeout)
    result = client.convert(
        file_path=str(pdf_path),
        options=options,
        max_polls=max_polls,
        poll_interval=poll_interval,
    )

    if not getattr(result, "success", False):
        err = getattr(result, "error", None) or "unknown error"
        raise RuntimeError(f"Datalab convert failed: {err}")

    markdown = getattr(result, "markdown", None) or ""
    json_payload = getattr(result, "json", None)
    if json_payload is None:
        json_payload = {}

    return {
        "markdown": markdown,
        "json_payload": json_payload,
        "quality_score": getattr(result, "parse_quality_score", None),
        "adapter": "datalab_sdk.DatalabClient.convert",
        "images": _decode_images(getattr(result, "images", None)),
    }


def _write_outputs(
    output_dir: Path,
    markdown: str,
    json_payload: Any,
    quality_score: Optional[float],
    adapter: str,
    images: Dict[str, bytes],
    mode: str,
    force_ocr_used: bool,
) -> None:
    cache_dir = output_dir / ".parse-cache"
    tmp_dir = output_dir / ".parse-cache.tmp"
    images_dir = tmp_dir / "images"

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    (tmp_dir / "parsed.md").write_text(markdown, encoding="utf-8")
    (tmp_dir / "parsed.json").write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    metadata = {
        "mode": mode,
        "force_ocr_hint_used": force_ocr_used,
        "quality_score": quality_score,
        "adapter": adapter,
        "image_count": len(images),
    }
    (tmp_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    for name, data in images.items():
        (images_dir / name).write_bytes(data)

    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    tmp_dir.replace(cache_dir)


def _cache_is_valid(output_dir: Path) -> bool:
    """Return True if .parse-cache already has the essential output files."""
    cache_dir = output_dir / ".parse-cache"
    return (cache_dir / "parsed.json").is_file() and (cache_dir / "parsed.md").is_file()


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse device manual into .parse-cache artifacts.")
    parser.add_argument("--pdf", required=True, help="Path to source PDF.")
    parser.add_argument("--output-dir", required=True, help="Device output directory (e.g. ref/devices/a6-rs).")
    parser.add_argument("--mode", default="accurate", help="Convert mode: fast, balanced, or accurate.")
    parser.add_argument("--retry-quality-threshold", type=float, default=3.0)
    parser.add_argument("--no-force-ocr-retry", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-parse even if .parse-cache already contains parsed.json and parsed.md.",
    )
    default_max_polls = int(os.getenv("DATALAB_CONVERT_MAX_POLLS", "1800"))
    parser.add_argument(
        "--max-polls",
        type=int,
        default=default_max_polls,
        help="Datalab job polling attempts (× --poll-interval ≈ max wait). "
        "Default from DATALAB_CONVERT_MAX_POLLS or 1800 (~30 min).",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=1,
        help="Seconds between Datalab status polls (SDK default: 1).",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=300,
        help="Per HTTP request timeout in seconds (passed to DatalabClient).",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    if not args.force and _cache_is_valid(output_dir):
        print(f"SKIP: .parse-cache already exists at {output_dir / '.parse-cache'}")
        print("Use --force to re-parse.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)

    poll_kw = dict(
        max_polls=args.max_polls,
        poll_interval=args.poll_interval,
        request_timeout=args.request_timeout,
    )
    first = parse_once(pdf_path, args.mode, force_ocr_hint=False, **poll_kw)
    quality = first["quality_score"]
    use_retry = (
        not args.no_force_ocr_retry
        and quality is not None
        and quality < args.retry_quality_threshold
    )

    final = first
    forced_ocr_used = False
    if use_retry:
        retry = parse_once(pdf_path, args.mode, force_ocr_hint=True, **poll_kw)
        retry_quality = retry["quality_score"]
        if retry_quality is not None and (quality is None or retry_quality >= quality):
            final = retry
            forced_ocr_used = True

    _write_outputs(
        output_dir=output_dir,
        markdown=final["markdown"],
        json_payload=final["json_payload"],
        quality_score=final["quality_score"],
        adapter=final["adapter"],
        images=final["images"],
        mode=args.mode,
        force_ocr_used=forced_ocr_used,
    )

    print(f"Parsed PDF: {pdf_path}")
    print(f"Output cache: {output_dir / '.parse-cache'}")
    print(f"Adapter: {final['adapter']}")
    print(f"Quality score: {final['quality_score']}")
    print(f"Force-OCR retry used: {forced_ocr_used}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

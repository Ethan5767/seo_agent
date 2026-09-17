"""Image and video SEO checks over already-fetched HTML."""

from __future__ import annotations

import re

_IMG = re.compile(r"<img\b([^>]*)>", re.I | re.S)
_VIDEO = re.compile(r"<video\b([^>]*)>(.*?)</video>", re.I | re.S)
_ATTR = re.compile(r"\b([\w:-]+)=[\"']([^\"']*)[\"']", re.I)


def _attrs(raw: str) -> dict[str, str]:
    return {key.lower(): value for key, value in _ATTR.findall(raw or "")}


def media_rows(html: str) -> list[dict]:
    rows: list[dict] = []
    images = [_attrs(raw) for raw in _IMG.findall(html or "")]
    if images:
        missing_alt = [img.get("src", "image") for img in images if not img.get("alt", "").strip()]
        missing_size = [img.get("src", "image") for img in images if not img.get("width") or not img.get("height")]
        lazy_missing = [img.get("src", "image") for img in images if not img.get("loading")]
        rows.append({"code": "media.image_alt", "what": "Image alt text", "severity": "warn" if missing_alt else "ok",
                     "why": "Descriptive alt text gives search engines and assistive technology an image alternative.",
                     "fix": "Add concise, accurate alt text to informative images; use empty alt for decorative images.",
                     "detail": f"{len(missing_alt)} of {len(images)} missing", "pages": missing_alt[:100]})
        rows.append({"code": "media.image_dimensions", "what": "Image dimensions and CLS risk", "severity": "warn" if missing_size else "ok",
                     "why": "Explicit dimensions reserve layout space and reduce cumulative layout shift.",
                     "fix": "Set width and height attributes or equivalent aspect-ratio styling.",
                     "detail": f"{len(missing_size)} of {len(images)} missing dimensions", "pages": missing_size[:100]})
        rows.append({"code": "media.image_lazy_loading", "what": "Below-fold image loading hints", "severity": "info",
                     "why": "Lazy loading can reduce initial work for images that are not visible at first paint.",
                     "fix": "Use loading=\"lazy\" for below-fold images, but keep the hero image eager.",
                     "detail": f"{len(lazy_missing)} image(s) have no loading hint", "pages": lazy_missing[:100]})
        nonmodern = [img.get("src", "image") for img in images if not re.search(r"\.(?:avif|webp)(?:$|[?#])", img.get("src", ""), re.I)]
        rows.append({"code": "media.image_format", "what": "Modern image formats", "severity": "info",
                     "why": "WebP and AVIF commonly reduce image bytes while preserving visual quality.",
                     "fix": "Serve modern formats with a compatible fallback where appropriate.",
                     "detail": f"{len(nonmodern)} of {len(images)} image URL(s) are not obviously WebP/AVIF", "pages": nonmodern[:100]})
    else:
        rows.append({"code": "media.no_images", "what": "Images", "severity": "info", "why": "No HTML images were found to audit.",
                     "fix": "No action unless the page is expected to contain images.", "detail": "0 images"})
    videos = _VIDEO.findall(html or "")
    schema_video = bool(re.search(r'"@type"\s*:\s*["\']VideoObject["\']', html or "", re.I))
    if videos or schema_video:
        missing_track = [raw for attrs, raw in videos if not re.search(r"<track\b", raw, re.I)]
        rows.append({"code": "media.video_schema", "what": "VideoObject schema", "severity": "ok" if schema_video else "warn",
                     "why": "VideoObject markup helps search engines understand playable media.",
                     "fix": "Add accurate VideoObject JSON-LD with a real thumbnail and upload date.", "detail": "present" if schema_video else "missing"})
        rows.append({"code": "media.video_captions", "what": "Video captions/transcript", "severity": "warn" if missing_track else "ok",
                     "why": "Captions make video content accessible and expose its words to crawlers.",
                     "fix": "Provide captions or a transcript for each video.", "detail": f"{len(missing_track)} video(s) without a track"})
    return rows

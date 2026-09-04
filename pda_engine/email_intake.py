"""
Parse an agency-appointment email into (body_text, [attachment_paths]) so the
AI extractor can read the body AND any attached particulars/cargo documents in
one pass. Supports .eml (standard MIME, stdlib) and .msg (Outlook, extract-msg).

Appointments frequently arrive as an email where the real vessel particulars /
cargo details sit in an attached PDF or spreadsheet, not the body -- so we pull
both out and hand them all to Claude together.
"""

import email
from email import policy
from pathlib import Path

_SKIP_ATTACH_EXTS = {".p7s", ".asc", ".ics"}  # signatures / calendar noise, not particulars


def parse_email(path, out_dir):
    """Returns (body_text, [attachment_paths]). Attachments are written into
    out_dir. Raises ValueError for an unsupported extension."""
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    if ext == ".eml":
        return _parse_eml(path, out_dir)
    if ext == ".msg":
        return _parse_msg(path, out_dir)
    raise ValueError(f"Unsupported email format: {ext}")


def _safe_name(name, fallback, out_dir):
    name = Path(name or fallback).name  # strip any path components
    dest = out_dir / name
    i = 1
    while dest.exists():
        dest = out_dir / f"{dest.stem}_{i}{dest.suffix}"
        i += 1
    return dest


def _parse_eml(path, out_dir):
    with open(path, "rb") as fh:
        msg = email.message_from_binary_file(fh, policy=policy.default)

    body_parts = []
    attachments = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        disp = part.get_content_disposition()
        ctype = part.get_content_type()
        if disp == "attachment" or (part.get_filename() and ctype != "text/plain"):
            fn = part.get_filename() or "attachment"
            if Path(fn).suffix.lower() in _SKIP_ATTACH_EXTS:
                continue
            data = part.get_payload(decode=True)
            if data:
                dest = _safe_name(fn, "attachment", out_dir)
                dest.write_bytes(data)
                attachments.append(str(dest))
        elif ctype == "text/plain":
            try:
                body_parts.append(part.get_content())
            except Exception:
                pass

    header = f"Subject: {msg.get('subject', '')}\nFrom: {msg.get('from', '')}\n\n"
    return header + "\n".join(body_parts), attachments


def _parse_msg(path, out_dir):
    import extract_msg

    m = extract_msg.Message(str(path))
    try:
        header = f"Subject: {m.subject or ''}\nFrom: {m.sender or ''}\n\n"
        body = m.body or ""
        attachments = []
        for att in m.attachments:
            fn = att.longFilename or att.shortFilename or "attachment"
            if Path(fn).suffix.lower() in _SKIP_ATTACH_EXTS:
                continue
            data = att.data
            if isinstance(data, bytes):
                dest = _safe_name(fn, "attachment", out_dir)
                dest.write_bytes(data)
                attachments.append(str(dest))
        return header + body, attachments
    finally:
        m.close()

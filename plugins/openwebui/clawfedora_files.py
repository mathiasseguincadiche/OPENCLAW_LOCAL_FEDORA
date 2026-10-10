"""Open WebUI global filter owned by OPENCLAW_LOCAL_FEDORA.

It deliberately disables Open WebUI's built-in file RAG for this provider. The only information
forwarded is metadata for files the authenticated user owns. The host bridge resolves the local
upload path again, validates it, and feeds the original file to the project's own ingestion chain.
"""

from typing import Optional

from open_webui.models.files import Files


class Filter:
    file_handler = True

    def __init__(self):
        self.file_handler = True

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        **_: object,
    ) -> dict:
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        message = metadata.get("user_message") if isinstance(metadata.get("user_message"), dict) else {}
        # Prefer the latest user message, never re-import a whole thread\u0027s older attachments.
        refs = (
            message.get("files") or []
            if "files" in message
            else body.get("files") or metadata.get("files") or []
        )
        if not isinstance(refs, list) or not refs:
            return body
        user_id = str((__user__ or {}).get("id", ""))
        if not user_id:
            raise ValueError("utilisateur Open WebUI absent pour les pièces jointes")
        if len(refs) > 20:
            raise ValueError("20 pièces jointes maximum par message")
        exported = []
        seen = set()
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            file_id = str(ref.get("id", ""))
            if not file_id or file_id in seen:
                continue
            seen.add(file_id)
            item = await Files.get_file_by_id_and_user_id(file_id, user_id)
            if item is None or not item.path:
                raise ValueError("pièce jointe introuvable ou non autorisée")
            meta = item.meta if isinstance(item.meta, dict) else {}
            exported.append(
                {
                    "id": item.id,
                    "filename": item.filename,
                    "path": item.path,
                    "sha256": meta.get("file_hash") or item.hash,
                    "content_type": meta.get("content_type"),
                    "size": meta.get("size"),
                    "kind": ref.get("type", "file"),
                }
            )
        if exported:
            body["clawfedora_files"] = exported
        return body

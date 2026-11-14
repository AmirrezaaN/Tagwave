"""Error types carrying a stable `code` that the UI translates."""

from __future__ import annotations


class TagwaveError(Exception):
    code = "error"

    def __init__(self, message: str = "", code: str | None = None, **details):
        super().__init__(message or self.__class__.__name__)
        if code:
            self.code = code
        self.details = details

    def to_json(self) -> dict:
        return {"code": self.code, "message": str(self), "details": self.details}


class UnsupportedFileError(TagwaveError):
    code = "unsupported-file"


class FileChangedError(TagwaveError):
    code = "file-changed"


class FileReadOnlyError(TagwaveError):
    code = "read-only"


class FileInUseError(TagwaveError):
    code = "file-in-use"


class IntegrityError(TagwaveError):
    code = "integrity"


class CannotTagError(TagwaveError):
    code = "cannot-tag"

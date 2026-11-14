"""The set of audio files currently open in the app."""

from __future__ import annotations

import itertools
import os
import re
import threading
from dataclasses import dataclass

from .blobs import BlobStore
from .core import audiofile
from .core.audiofile import LoadedFile
from .core.errors import TagwaveError


class UnknownFileError(TagwaveError):
    code = "unknown-file"


@dataclass
class Entry:
    id: str
    loaded: LoadedFile
    version: int
    pictures: list   # [{'blob', 'type', 'desc'}]

    @property
    def path(self) -> str:
        return self.loaded.path


def natural_key(path: str):
    d, name = os.path.split(path)
    parts = re.split(r"(\d+)", name.lower())
    return (os.path.normcase(d), [int(p) if p.isdigit() else p for p in parts])


def expand_paths(paths, recursive: bool = True) -> list:
    """Files and folders -> sorted list of supported audio files."""
    out = []
    seen = set()
    for p in paths or []:
        if not isinstance(p, str) or not p:
            continue
        p = os.path.abspath(p)
        if os.path.isdir(p):
            found = []
            if recursive:
                for root, dirs, files in os.walk(p):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    found += [os.path.join(root, f) for f in files if audiofile.is_supported_path(f)]
            else:
                found = [os.path.join(p, f) for f in os.listdir(p)
                         if audiofile.is_supported_path(f) and os.path.isfile(os.path.join(p, f))]
            found.sort(key=natural_key)
            candidates = found
        elif os.path.isfile(p) and audiofile.is_supported_path(p):
            candidates = [p]
        else:
            candidates = []
        for c in candidates:
            if ".tagwave-" in os.path.basename(c):   # our own temporary files
                continue
            key = os.path.normcase(c)
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out


class Session:
    def __init__(self, blobs: BlobStore):
        self.blobs = blobs
        self._files: dict = {}
        self._order: list = []
        self._by_path: dict = {}
        self._ids = itertools.count(1)
        self._lock = threading.RLock()

    # --------------------------------------------------------------- access
    def get(self, file_id: str) -> Entry:
        with self._lock:
            e = self._files.get(file_id)
        if e is None:
            raise UnknownFileError("This file is no longer open.")
        return e

    def has_path(self, path: str) -> bool:
        with self._lock:
            return os.path.normcase(os.path.abspath(path)) in self._by_path

    def all(self) -> list:
        with self._lock:
            return [self._files[i] for i in self._order if i in self._files]

    # ------------------------------------------------------------ mutation
    def _register_pictures(self, loaded: LoadedFile) -> list:
        pics = []
        for p in loaded.snapshot.pictures:
            blob = self.blobs.put(p.data)
            pics.append({"blob": blob, "type": int(p.type), "desc": p.desc or ""})
        # Free the bytes: everything is in the blob store now.
        for p in loaded.snapshot.pictures:
            p.data = b""
        return pics

    def load(self, path: str) -> LoadedFile:
        return audiofile.load(path)

    def add_loaded(self, loaded: LoadedFile) -> Entry | None:
        pics = self._register_pictures(loaded)
        key = os.path.normcase(loaded.path)
        with self._lock:
            if key in self._by_path:
                return None
            e = Entry("f%d" % next(self._ids), loaded, 1, pics)
            self._files[e.id] = e
            self._order.append(e.id)
            self._by_path[key] = e.id
            return e

    def add(self, path: str) -> Entry | None:
        if self.has_path(path):
            return None
        return self.add_loaded(self.load(path))

    def reload(self, file_id: str, new_path: str | None = None) -> Entry:
        e = self.get(file_id)
        loaded = audiofile.load(new_path or e.path)
        pics = self._register_pictures(loaded)
        with self._lock:
            old_key = os.path.normcase(e.path)
            if self._by_path.get(old_key) == e.id:
                del self._by_path[old_key]
            e.loaded = loaded
            e.pictures = pics
            e.version += 1
            self._by_path[os.path.normcase(loaded.path)] = e.id
        return e

    def remove(self, ids) -> None:
        with self._lock:
            for i in ids or []:
                e = self._files.pop(i, None)
                if e is None:
                    continue
                self._by_path.pop(os.path.normcase(e.path), None)
            self._order = [i for i in self._order if i in self._files]

    # ---------------------------------------------------------------- JSON
    def to_json(self, e: Entry, playable: bool) -> dict:
        lf = e.loaded
        d, name = os.path.split(lf.path)
        pics = []
        for p in e.pictures:
            info = self.blobs.info(p["blob"])
            info.update(type=p["type"], desc=p["desc"])
            pics.append(info)
        return {
            "id": e.id, "path": lf.path, "name": name, "dir": d,
            "ext": os.path.splitext(name)[1].lstrip(".").lower(),
            "size": lf.size, "mtime": lf.mtime_ns // 1_000_000, "version": e.version,
            "canTag": lf.can_tag, "pictureTypes": lf.picture_types, "pictureDesc": lf.picture_desc,
            "tagFormat": lf.snapshot.tag_format, "info": lf.info,
            "fields": dict(lf.snapshot.fields), "custom": [list(c) for c in lf.snapshot.custom],
            "pictures": pics, "playable": playable,
        }

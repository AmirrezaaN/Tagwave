"""Every action the UI can request. Transport-independent (served over local HTTP)."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import __version__
from .blobs import BlobStore
from .core import audiofile, convert, ffmpeg, images, online, quality, rename
from .core.errors import TagwaveError
from .core.tags import FIELD_KEYS, PICTURE_TYPES, Picture, SaveOptions, TagChanges, validate_fields
from .events import EventBus
from .jobs import JobManager, error_json
from .preview import PreviewCache, direct_mime
from .session import Session, expand_paths
from .settings import Settings

MAX_IMAGE_BYTES = 60 * 1024 * 1024


class ApiError(TagwaveError):
    code = "bad-request"


class Api:
    def __init__(self, settings: Settings | None = None, temp_root: str | None = None):
        self.settings = settings or Settings()
        self.bus = EventBus()
        self.jobs = JobManager(self.bus)
        self.blobs = BlobStore(temp_root)
        self.session = Session(self.blobs)
        self.preview = PreviewCache(os.path.dirname(self.blobs.dir))
        self.native = None            # set by the window layer when running as a desktop app
        self.dev = False
        self.dirty = False
        self._sources: dict = {}      # (file id, version) -> convert.Source
        self.methods = {
            "init": self.init,
            "settings.set": self.settings_set,
            "files.list": self.files_list,
            "files.add": self.files_add,
            "files.remove": self.files_remove,
            "files.reload": self.files_reload,
            "files.save": self.files_save,
            "dialog.openFiles": self.dialog_open_files,
            "dialog.openFolder": self.dialog_open_folder,
            "dialog.pickFolder": self.dialog_pick_folder,
            "images.fromPaths": self.images_from_paths,
            "images.pick": self.images_pick,
            "images.cropInfo": self.images_crop_info,
            "images.crop": self.images_crop,
            "images.detectBorders": self.images_detect_borders,
            "images.export": self.images_export,
            "images.fetch": self.images_fetch,
            "convert.plan": self.convert_plan,
            "convert.start": self.convert_start,
            "jobs.cancel": self.jobs_cancel,
            "jobs.get": self.jobs_get,
            "rename.preview": self.rename_preview,
            "rename.apply": self.rename_apply,
            "tags.fromFilename": self.tags_from_filename,
            "quality.analyze": self.quality_analyze,
            "online.search": self.online_search,
            "online.details": self.online_details,
            "lyrics.import": self.lyrics_import,
            "lyrics.export": self.lyrics_export,
            "player.source": self.player_source,
            "system.reveal": self.system_reveal,
            "system.openUrl": self.system_open_url,
            "window.setTheme": self.window_set_theme,
            "window.setDirty": self.window_set_dirty,
            "window.close": self.window_close,
        }

    # ------------------------------------------------------------------ core
    def call(self, method: str, params: dict | None):
        fn = self.methods.get(method)
        if fn is None:
            raise ApiError("Unknown method: %s" % method)
        return fn(**(params or {}))

    def shutdown(self) -> None:
        self.jobs.shutdown()
        self.blobs.close()

    def file_json(self, entry) -> dict:
        return self.session.to_json(entry, bool(direct_mime(entry.loaded.info)))

    def _save_options(self) -> SaveOptions:
        s = self.settings
        return SaveOptions(id3_version=s.get("id3Version"), id3v1=s.get("id3v1"))

    def _require_native(self):
        if self.native is None:
            raise ApiError("Native dialogs are not available here.", "no-native")
        return self.native

    def _pictures(self, items) -> list:
        out = []
        for p in items or []:
            blob = p.get("blob")
            data = self.blobs.read(blob)
            mime = self.blobs.meta(blob)["mime"]
            if mime not in images.EMBEDDABLE:
                data, mime, _ = images.prepare_for_embedding(data)
            out.append(Picture(int(p.get("type", 3)), mime, str(p.get("desc") or ""), data))
        return out

    def _changes(self, item: dict, full: bool = False) -> TagChanges:
        fields = {k: ("" if v is None else str(v)) for k, v in (item.get("fields") or {}).items()
                  if k in FIELD_KEYS}
        if full:
            for k in FIELD_KEYS:
                fields.setdefault(k, "")
        custom = item.get("custom")
        if custom is not None:
            custom = [[str(k), "" if v is None else str(v)] for k, v in custom]
        pictures = self._pictures(item["pictures"]) if item.get("pictures") is not None else None
        return TagChanges(fields=fields, custom=custom, pictures=pictures)

    # ---------------------------------------------------------------- basics
    def init(self) -> dict:
        return {
            "version": __version__,
            "settings": self.settings.snapshot(),
            "ffmpeg": ffmpeg.available(),
            "native": self.native is not None,
            "dev": self.dev,
            "extensions": list(audiofile.SUPPORTED_EXTENSIONS),
            "fields": FIELD_KEYS,
            "pictureTypes": PICTURE_TYPES,
            "targets": {k: {"ext": v["ext"], "lossless": v["lossless"],
                            "qualities": list(convert.QUALITY.get(k, {}).keys())}
                        for k, v in convert.TARGETS.items()},
            "files": [self.file_json(e) for e in self.session.all()],
        }

    def settings_set(self, patch: dict) -> dict:
        return self.settings.update(patch)

    # ----------------------------------------------------------------- files
    def files_list(self) -> list:
        return [self.file_json(e) for e in self.session.all()]

    def add_paths(self, paths_, origin: str = "user") -> str | None:
        files = [p for p in expand_paths(paths_) if not self.session.has_path(p)]
        if not files:
            return None
        return self.jobs.start("load", self._load_job, files, meta={"count": len(files), "origin": origin})

    def files_add(self, paths: list) -> dict:
        return {"jobId": self.add_paths(paths)}

    def _load_job(self, job, files: list) -> dict:
        errors, added = [], 0
        batch: list = []
        last = time.monotonic()

        def load_one(p):
            try:
                return p, self.session.load(p), None
            except Exception as exc:  # noqa: BLE001
                return p, None, error_json(exc)

        with ThreadPoolExecutor(max_workers=4) as ex:
            for i, (p, loaded, err) in enumerate(ex.map(load_one, files)):
                if job.cancelled:
                    break
                if err:
                    errors.append({"path": p, "error": err})
                else:
                    e = self.session.add_loaded(loaded)
                    if e is not None:
                        batch.append(self.file_json(e))
                        added += 1
                if batch and (len(batch) >= 25 or time.monotonic() - last > 0.3):
                    job.event("files.added", {"files": batch})
                    batch, last = [], time.monotonic()
                job.set_progress((i + 1) / len(files))
        if batch:
            job.event("files.added", {"files": batch})
        return {"added": added, "errors": errors}

    def files_remove(self, ids: list) -> bool:
        self.session.remove(ids)
        return True

    def files_reload(self, ids: list) -> dict:
        files, errors = [], []
        for i in ids:
            try:
                files.append(self.file_json(self.session.reload(i)))
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": i, "error": error_json(exc)})
        return {"files": files, "errors": errors}

    def files_save(self, items: list) -> dict:
        return {"jobId": self.jobs.start("save", self._save_job, items, meta={"count": len(items)})}

    def _save_job(self, job, items: list) -> dict:
        opts = self._save_options()
        verify = bool(self.settings.get("verifyOnSave"))
        keep_mtime = bool(self.settings.get("preserveMtime"))
        saved, errors = [], []
        for n, item in enumerate(items):
            if job.cancelled:
                break
            fid = item.get("id")
            try:
                entry = self.session.get(fid)
                changes = self._changes(item)
                if not changes.is_empty():
                    if not entry.loaded.can_tag:
                        raise TagwaveError("This format can't store tags.", "cannot-tag")
                    audiofile.save(entry.path, changes, opts, expected=entry.loaded.stamp,
                                   verify_audio=verify, preserve_mtime=keep_mtime)
                    entry = self.session.reload(fid)
                f = self.file_json(entry)
                saved.append(f)
                job.event("files.saved", {"file": f})
            except Exception as exc:  # noqa: BLE001
                err = error_json(exc)
                errors.append({"id": fid, "error": err})
                job.event("files.saveFailed", {"id": fid, "error": err})
            job.set_progress((n + 1) / max(1, len(items)))
        return {"saved": [f["id"] for f in saved], "errors": errors}

    # --------------------------------------------------------------- dialogs
    def dialog_open_files(self) -> dict:
        exts = ";".join("*" + e for e in audiofile.SUPPORTED_EXTENSIONS)
        paths_ = self._require_native().open_files("Audio files (%s)" % exts, self.settings.get("lastOpenDir"))
        if paths_:
            self.settings.update({"lastOpenDir": os.path.dirname(paths_[0])})
            return {"jobId": self.add_paths(paths_)}
        return {"jobId": None}

    def dialog_open_folder(self) -> dict:
        folder = self._require_native().pick_folder(self.settings.get("lastOpenDir"))
        if folder:
            self.settings.update({"lastOpenDir": folder})
            return {"jobId": self.add_paths([folder])}
        return {"jobId": None}

    def dialog_pick_folder(self, initial: str = "") -> dict:
        folder = self._require_native().pick_folder(initial or self.settings.get("lastExportDir"))
        if folder:
            self.settings.update({"lastExportDir": folder})
        return {"path": folder}

    # ---------------------------------------------------------------- images
    def _put_image(self, data: bytes) -> dict:
        if len(data) > MAX_IMAGE_BYTES:
            raise ApiError("The image is too large.", "image-too-large")
        if not images.is_image(data):
            raise ApiError("This isn't a supported image.", "not-image")
        data, _mime, converted = images.prepare_for_embedding(data)
        info = self.blobs.info(self.blobs.put(data))
        info["converted"] = converted
        return info

    def upload_image(self, data: bytes) -> dict:
        return self._put_image(data)

    def images_from_paths(self, paths: list) -> dict:
        out, errors = [], []
        for p in paths or []:
            try:
                with open(p, "rb") as f:
                    out.append(self._put_image(f.read(MAX_IMAGE_BYTES + 1)))
            except Exception as exc:  # noqa: BLE001
                errors.append({"path": p, "error": error_json(exc)})
        return {"images": out, "errors": errors}

    def images_pick(self, multiple: bool = False) -> dict:
        types = "Images (*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.gif;*.tif;*.tiff)"
        paths_ = self._require_native().open_files(types, self.settings.get("lastImageDir"), multiple)
        if not paths_:
            return {"images": [], "errors": []}
        self.settings.update({"lastImageDir": os.path.dirname(paths_[0])})
        return self.images_from_paths(paths_)

    def images_crop_info(self, blob: str) -> dict:
        return images.crop_capabilities(self.blobs.read(blob))

    def images_detect_borders(self, blob: str) -> dict:
        return images.detect_borders(self.blobs.read(blob))

    def images_crop(self, blob: str, x: int, y: int, w: int, h: int, mode: str = "lossless") -> dict:
        data = self.blobs.read(blob)
        x, y, w, h = int(x), int(y), int(w), int(h)
        caps = images.crop_capabilities(data)
        if mode == "lossless":
            if not caps["lossless"]:
                raise ApiError("Lossless crop isn't possible for this image.", "lossless-unavailable")
            out = images.crop_jpeg_lossless(data, x, y, w, h) if caps["isJpeg"] else images.crop_to_png(data, x, y, w, h)
        else:
            out = images.crop_to_png(data, x, y, w, h)
        info = self.blobs.info(self.blobs.put(out))
        info["converted"] = False
        return info

    def images_export(self, blob: str, name: str = "cover") -> dict:
        meta = self.blobs.meta(blob)
        ext = ".png" if meta["mime"] == images.PNG else ".jpg"
        path = self._require_native().save_file(name + ext, "Image (*%s)" % ext, self.settings.get("lastImageDir"))
        if not path:
            return {"path": None}
        if not path.lower().endswith(ext):
            path += ext
        with open(path, "wb") as f:
            f.write(self.blobs.read(blob))
        return {"path": path}

    def images_fetch(self, url: str) -> dict:
        try:
            data = online.download_image(url)
        except online.LookupError_ as exc:
            raise ApiError("Download failed.", "online-" + exc.code) from None
        return self._put_image(data)

    # --------------------------------------------------------------- convert
    def _source(self, entry) -> convert.Source:
        key = (entry.id, entry.version)
        src = self._sources.get(key)
        if src is None:
            src = convert.analyze_source(entry.path, entry.loaded.info)
            self._sources[key] = src
        return src

    def _convert_options(self, o: dict) -> convert.ConvertOptions:
        target = o.get("target")
        if target not in convert.TARGETS:
            raise ApiError("Choose an output format.", "bad-target")
        out_dir = o.get("outputDir") if o.get("outputMode") == "custom" else None
        if o.get("outputMode") == "custom" and not out_dir:
            raise ApiError("Choose an output folder.", "no-output-dir")
        return convert.ConvertOptions(
            target=target, quality=(o.get("quality") or None), flac_level=int(o.get("flacLevel", 8)),
            out_dir=out_dir, overwrite=o.get("overwrite", "rename"),
            verify=bool(self.settings.get("verifyConversions")), tag_opts=self._save_options())

    def convert_plan(self, ids: list, options: dict) -> list:
        opts = self._convert_options(options)
        out = []
        for fid in ids:
            try:
                e = self.session.get(fid)
                plan = convert.make_plan(self._source(e), opts)
                path, action = convert.output_path(e.path, opts, reserve=False)
                out.append({"id": fid, "plan": plan.to_json(), "output": path, "action": action})
            except Exception as exc:  # noqa: BLE001
                out.append({"id": fid, "error": error_json(exc)})
        return out

    def convert_start(self, items: list, options: dict) -> dict:
        opts = self._convert_options(options)
        for it in items:
            validate_fields({k: v for k, v in (it.get("fields") or {}).items() if k in FIELD_KEYS})
        return {"jobId": self.jobs.start("convert", self._convert_job, items, opts, bool(options.get("addToList")),
                                         meta={"count": len(items), "target": opts.target})}

    def _convert_job(self, job, items: list, opts: convert.ConvertOptions, add_to_list: bool) -> dict:
        n = len(items)
        progress = [0.0] * n
        results: list = [None] * n
        lock = threading.Lock()

        def report(i, f):
            with lock:
                progress[i] = f
                total = sum(progress) / max(1, n)
            job.set_progress(total)
            job.event("convert.item", {"index": i, "state": "running", "progress": f})

        def one(i, item):
            if job.cancelled:
                results[i] = {"id": item.get("id"), "state": "cancelled"}
                return
            out = None
            try:
                e = self.session.get(item["id"])
                src = self._source(e)
                plan = convert.make_plan(src, opts)
                out, action = convert.output_path(e.path, opts)
                if action == "skip":
                    results[i] = {"id": e.id, "state": "skipped", "path": out}
                else:
                    tags = self._changes(item, full=True)
                    if tags.pictures is None:
                        tags.pictures = self._pictures(e.pictures)
                    if tags.custom is None:
                        tags.custom = [list(c) for c in e.loaded.snapshot.custom]
                    res = convert.convert(src, plan, out, tags, opts, lambda f: report(i, f), job.cancel_event)
                    results[i] = {"id": e.id, "state": "done", "path": res["path"], "verified": res["verified"],
                                  "warnings": res["warnings"], "mode": plan.mode, "bitPerfect": plan.bit_perfect}
            except convert.Cancelled:
                results[i] = {"id": item.get("id"), "state": "cancelled"}
            except Exception as exc:  # noqa: BLE001
                results[i] = {"id": item.get("id"), "state": "error", "error": error_json(exc)}
            finally:
                if out:
                    convert.release_name(out)
                report(i, 1.0)
                job.event("convert.item", {"index": i, "state": results[i]["state"], "progress": 1.0,
                                           "result": results[i]})

        workers = max(1, min(4, (os.cpu_count() or 2) // 2))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(lambda a: one(*a), enumerate(items)))
        if add_to_list:
            done = [r["path"] for r in results if r and r.get("state") == "done"]
            if done:
                self.add_paths(done, origin="convert")
        return {"results": results}

    def jobs_cancel(self, id: str) -> bool:
        return self.jobs.cancel(id)

    def jobs_get(self, id: str) -> dict | None:
        j = self.jobs.get(id)
        return j.to_json() if j else None

    # ---------------------------------------------------------------- rename
    def rename_preview(self, items: list, pattern: str) -> list:
        data = []
        for it in items:
            e = self.session.get(it["id"])
            data.append({"id": e.id, "path": e.path, "fields": it.get("fields") or e.loaded.snapshot.fields})
        return rename.preview(data, pattern)

    def rename_apply(self, items: list, pattern: str) -> dict:
        plan = self.rename_preview(items, pattern)
        results = rename.apply(plan)
        files = []
        for r in results:
            if r["ok"] and r["newPath"] != r["path"]:
                try:
                    files.append(self.file_json(self.session.reload(r["id"], r["newPath"])))
                except Exception as exc:  # noqa: BLE001
                    r["ok"], r["error"] = False, error_json(exc)["code"]
        hist = [pattern] + [p for p in (self.settings.get("renameHistory") or []) if p != pattern]
        self.settings.update({"renamePattern": pattern, "renameHistory": hist[:8]})
        return {"results": results, "files": files}

    def tags_from_filename(self, ids: list, pattern: str) -> list:
        out = []
        for fid in ids:
            e = self.session.get(fid)
            stem = os.path.splitext(os.path.basename(e.path))[0]
            out.append({"id": fid, "fields": rename.parse_filename(pattern, stem)})
        self.settings.update({"parsePattern": pattern})
        return out

    # --------------------------------------------------------------- quality
    def quality_analyze(self, id: str) -> dict:
        e = self.session.get(id)
        return {"jobId": self.jobs.start("quality", self._quality_job, e.id, meta={"id": e.id})}

    def _quality_job(self, job, fid: str) -> dict:
        e = self.session.get(fid)
        fd, png = tempfile.mkstemp(suffix=".png", dir=self.blobs.dir)
        os.close(fd)
        try:
            job.set_progress(0.1, force=True)
            result = quality.analyze(e.path, e.loaded.info, png)
            with open(png, "rb") as f:
                result["spectrogram"] = self.blobs.info(self.blobs.put(f.read()))
        finally:
            if os.path.exists(png):
                os.remove(png)
        result["duration"] = e.loaded.info.get("duration")
        result["id"] = fid
        return result

    # ---------------------------------------------------------------- online
    def online_search(self, artist: str = "", title: str = "", album: str = "", providers=None) -> dict:
        if not self.settings.get("onlineEnabled"):
            raise ApiError("Online lookup is turned off in Settings.", "online-disabled")
        providers = providers or self.settings.get("onlineProviders")
        return {"jobId": self.jobs.start("online", lambda job: online.search(artist, title, album, providers))}

    def online_details(self, provider: str, id: str) -> dict:
        if provider != "deezer":
            return {}
        try:
            return online.deezer_details(id)
        except online.LookupError_ as exc:
            raise ApiError("Lookup failed.", "online-" + exc.code) from None

    # ---------------------------------------------------------------- lyrics
    def lyrics_import(self) -> dict:
        paths_ = self._require_native().open_files("Lyrics (*.lrc;*.txt)", self.settings.get("lastOpenDir"), False)
        if not paths_:
            return {"text": None}
        with open(paths_[0], "rb") as f:
            raw = f.read(4 * 1024 * 1024)
        for enc in ("utf-8-sig", "utf-16", "cp1256", "latin-1"):
            try:
                text = raw.decode(enc)
                if enc == "utf-16" and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                    continue
                return {"text": text.replace("\r\n", "\n"), "path": paths_[0]}
            except UnicodeDecodeError:
                continue
        raise ApiError("Couldn't read this file.", "bad-text")

    def lyrics_export(self, text: str, name: str = "lyrics") -> dict:
        path = self._require_native().save_file(name + ".lrc", "Lyrics (*.lrc)", self.settings.get("lastOpenDir"))
        if not path:
            return {"path": None}
        if not path.lower().endswith((".lrc", ".txt")):
            path += ".lrc"
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return {"path": path}

    # ---------------------------------------------------------------- player
    def player_source(self, id: str) -> dict:
        e = self.session.get(id)
        _path, mime, transcoded = self.preview.source(e.path, e.loaded.info)
        return {"url": "/media/audio/%s?v=%d" % (e.id, e.version), "mime": mime, "transcoded": transcoded}

    def audio_file(self, file_id: str) -> tuple[str, str]:
        e = self.session.get(file_id)
        path, mime, _ = self.preview.source(e.path, e.loaded.info)
        return path, mime

    # ---------------------------------------------------------------- system
    def system_reveal(self, path: str) -> bool:
        if not os.path.exists(path):
            raise ApiError("File not found.", "not-found")
        subprocess.Popen('explorer /select,"%s"' % os.path.normpath(path))
        return True

    def system_open_url(self, url: str) -> bool:
        if not url.startswith("https://"):
            raise ApiError("Bad link.")
        os.startfile(url)  # type: ignore[attr-defined]
        return True

    # ---------------------------------------------------------------- window
    def window_set_theme(self, dark: bool, background: str = "") -> bool:
        if self.native:
            self.native.set_theme(bool(dark), background)
        return True

    def window_set_dirty(self, dirty: bool) -> bool:
        self.dirty = bool(dirty)
        return True

    def window_close(self) -> bool:
        if self.native:
            self.native.close_now()
        return True


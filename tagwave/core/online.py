"""Optional online lookup of tags and cover art (MusicBrainz/Cover Art Archive, iTunes, Deezer).

Nothing here runs unless the user explicitly clicks "Search online". Cover images are
downloaded byte-for-byte; they're never re-encoded.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .. import __version__
from . import images

USER_AGENT = "Tagwave/%s ( desktop music tag editor )" % __version__
TIMEOUT = 12
MAX_IMAGE = 40 * 1024 * 1024

_mb_lock = threading.Lock()
_mb_last = [0.0]


class LookupError_(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _get(url: str, *, binary: bool = False, limit: int = 5 * 1024 * 1024):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as exc:
        raise LookupError_("not-found" if exc.code == 404 else "http") from None
    except (socket.timeout, TimeoutError):
        raise LookupError_("timeout") from None
    except (urllib.error.URLError, OSError):
        raise LookupError_("network") from None
    if len(data) > limit:
        raise LookupError_("too-large")
    return data if binary else json.loads(data.decode("utf-8"))


def _q(s: str) -> str:
    return (s or "").replace("\\", " ").replace('"', " ").strip()


# ------------------------------------------------------------------- providers

def search_musicbrainz(artist: str, title: str, album: str) -> list:
    parts = []
    if title:
        parts.append('recording:"%s"' % _q(title))
    if artist:
        parts.append('artist:"%s"' % _q(artist))
    if album:
        parts.append('release:"%s"' % _q(album))
    if not parts:
        return []
    url = "https://musicbrainz.org/ws/2/recording?" + urllib.parse.urlencode(
        {"query": " AND ".join(parts), "fmt": "json", "limit": 50})
    data = None
    for attempt in range(2):
        with _mb_lock:   # MusicBrainz asks for at most one request per second
            wait = 1.05 - (time.monotonic() - _mb_last[0])
            if wait > 0:
                time.sleep(wait)
            try:
                data = _get(url)
                break
            except LookupError_ as exc:
                if exc.code != "http" or attempt == 1:
                    raise
            finally:
                _mb_last[0] = time.monotonic()
        time.sleep(1.5)   # usually a transient 503 "slow down"
    # Rank: good text match, official studio albums, then the "canonical" recording
    # (the one released most often), earliest release first.
    ranked = []
    for rec in data.get("recordings", []):
        releases = rec.get("releases") or []
        for rel in releases:
            rg = rel.get("release-group") or {}
            ranked.append(((
                -(int(rec.get("score", 0) or 0) // 10),
                0 if rel.get("status") == "Official" else 1,
                0 if rg.get("primary-type") == "Album" and not rg.get("secondary-types") else 1,
                -min(len(releases), 20),
                rel.get("date") or "9999",
            ), rec, rel))
    ranked.sort(key=lambda x: x[0])
    out = []
    seen = set()
    for _key, rec, rel in ranked:
        if len(out) >= 15:
            break
        rid = rel.get("id")
        if not rid or (rel.get("title"), rel.get("date")) in seen:
            continue
        seen.add((rel.get("title"), rel.get("date")))
        credit = "".join(c.get("name", "") + c.get("joinphrase", "") for c in rec.get("artist-credit", []))
        media = (rel.get("media") or [{}])[0]
        track = (media.get("track") or [{}])[0]
        number = str(track.get("number", "") or "")
        if not number.isdigit():
            offset = media.get("track-offset")
            number = str(offset + 1) if isinstance(offset, int) else ""
        rel_credit = "".join(c.get("name", "") + c.get("joinphrase", "")
                             for c in rel.get("artist-credit", [])) or credit
        out.append({
            "provider": "musicbrainz", "id": "%s:%s" % (rec.get("id"), rid),
            "title": rec.get("title", ""), "artist": credit, "album": rel.get("title", ""),
            "albumartist": rel_credit, "date": rel.get("date", "") or "",
            "track": number, "tracktotal": str(media.get("track-count", "") or ""),
            "disc": str(media.get("position", "") or ""), "disctotal": "",
            "genre": "", "isrc": (rec.get("isrcs") or [""])[0],
            "thumb": "https://coverartarchive.org/release/%s/front-250" % rid,
            "covers": [{"url": "https://coverartarchive.org/release/%s/front" % rid, "label": "original"}],
        })
    return out


def _itunes_art(url100: str, size: str) -> str:
    return url100.replace("100x100bb", size)


def search_itunes(artist: str, title: str, album: str) -> list:
    term = " ".join(x for x in (artist, title or album) if x)
    if not term:
        return []
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": term, "media": "music", "entity": "song", "limit": 15})
    data = _get(url)
    out = []
    for r in data.get("results", []):
        art = r.get("artworkUrl100", "")
        out.append({
            "provider": "itunes", "id": str(r.get("trackId", "")),
            "title": r.get("trackName", ""), "artist": r.get("artistName", ""),
            "album": r.get("collectionName", ""),
            "albumartist": r.get("collectionArtistName", "") or r.get("artistName", ""),
            "date": (r.get("releaseDate") or "")[:10], "genre": r.get("primaryGenreName", ""),
            "track": str(r.get("trackNumber", "") or ""), "tracktotal": str(r.get("trackCount", "") or ""),
            "disc": str(r.get("discNumber", "") or ""), "disctotal": str(r.get("discCount", "") or ""),
            "isrc": "",
            "thumb": _itunes_art(art, "200x200bb") if art else "",
            # Asking for a huge size returns the largest image Apple has.
            "covers": [{"url": _itunes_art(art, "10000x10000bb"), "label": "max"}] if art else [],
        })
    return out


def search_deezer(artist: str, title: str, album: str) -> list:
    term = " ".join(_q(x) for x in (artist, title or album) if x)
    if not term:
        return []
    data = _get("https://api.deezer.com/search?" + urllib.parse.urlencode({"q": term, "limit": 15}))
    out = []
    for r in data.get("data", []):
        alb = r.get("album") or {}
        out.append({
            "provider": "deezer", "id": str(r.get("id", "")),
            "title": r.get("title", ""), "artist": (r.get("artist") or {}).get("name", ""),
            "album": alb.get("title", ""), "albumartist": "", "date": "", "genre": "",
            "track": "", "tracktotal": "", "disc": "", "disctotal": "", "isrc": "",
            "thumb": alb.get("cover_medium", ""),
            "covers": [{"url": alb.get("cover_xl", ""), "label": "1000"}] if alb.get("cover_xl") else [],
            "needsDetails": True,
        })
    return out


def deezer_details(track_id: str) -> dict:
    t = _get("https://api.deezer.com/track/%s" % urllib.parse.quote(track_id))
    alb = t.get("album") or {}
    out = {"date": t.get("release_date", "") or "", "track": str(t.get("track_position", "") or ""),
           "disc": str(t.get("disk_number", "") or ""), "isrc": t.get("isrc", "") or ""}
    if alb.get("id"):
        try:
            a = _get("https://api.deezer.com/album/%s" % alb["id"])
            out["tracktotal"] = str(a.get("nb_tracks", "") or "")
            out["albumartist"] = (a.get("artist") or {}).get("name", "")
            genres = (a.get("genres") or {}).get("data") or []
            out["genre"] = genres[0]["name"] if genres else ""
            out["date"] = out["date"] or a.get("release_date", "")
        except LookupError_:
            pass
    return out


PROVIDERS = {"musicbrainz": search_musicbrainz, "itunes": search_itunes, "deezer": search_deezer}


def search(artist: str, title: str, album: str, providers=None) -> dict:
    providers = [p for p in (providers or PROVIDERS) if p in PROVIDERS]
    results: list = []
    errors: list = []
    with ThreadPoolExecutor(max_workers=len(providers) or 1) as ex:
        futs = {p: ex.submit(PROVIDERS[p], artist, title, album) for p in providers}
        for p, fut in futs.items():
            try:
                results.extend(fut.result())
            except LookupError_ as exc:
                errors.append({"provider": p, "code": exc.code})
            except Exception:
                errors.append({"provider": p, "code": "error"})
    return {"results": results, "errors": errors}


def download_image(url: str) -> bytes:
    if not url.lower().startswith("https://"):
        raise LookupError_("bad-url")
    data = _get(url, binary=True, limit=MAX_IMAGE)
    if not images.is_image(data):
        raise LookupError_("not-image")
    return data

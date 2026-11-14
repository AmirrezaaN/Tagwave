import json
import os
import time
import urllib.error
import urllib.request

import pytest

from tagwave.api import Api
from tagwave.server import Server
from tagwave.settings import Settings


@pytest.fixture
def srv(tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    api = Api(Settings(str(tmp_path / "settings.json")), temp_root=str(tmp_path / "tmp"))
    s = Server(api, ui_dir=str(ui), token="secret")
    s.start()
    yield s
    s.stop()
    api.shutdown()


def _req(s, path, body=None, headers=None, method=None, token=True):
    h = {"Content-Type": "application/json"}
    if token:
        h["X-Tagwave-Token"] = s.token
    h.update(headers or {})
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (s.port, path), data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=60)


def call(s, method, **params):
    r = json.loads(_req(s, "/api/call", {"method": method, "params": params}).read())
    if not r["ok"]:
        raise AssertionError(r["error"])
    return r["result"]


def wait_job(s, job_id, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        j = call(s, "jobs.get", id=job_id)
        if j and j["state"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job timeout")


def test_security(srv):
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(srv, "/api/call", {"method": "init"}, token=False)
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(srv, "/api/call", {"method": "init"}, headers={"Host": "evil.example:80"})
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(srv, "/api/call", {"method": "init"}, headers={"Origin": "https://evil.example"})
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(srv, "/media/blob/" + "0" * 40, token=False)
    assert e.value.code == 403
    # path traversal on static files
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(srv, "/..%2f..%2fsettings.json", token=False)
    assert e.value.code == 404
    assert _req(srv, "/", token=False).status == 200


def test_end_to_end(srv, sample, jpeg_bytes, tmp_path):
    paths = [sample("mp3"), sample("flac16"), sample("alac")]
    info = call(srv, "init")
    assert info["ffmpeg"] and info["files"] == []
    job = call(srv, "files.add", paths=paths + [paths[0]])["jobId"]
    assert wait_job(srv, job)["result"]["added"] == 3
    files = call(srv, "files.list")
    assert [f["name"] for f in files] == [os.path.basename(p) for p in paths]
    mp3, flac, alac = files

    # upload a cover (as if pasted) and save it with new tags to two files at once
    up = json.loads(_req(srv, "/api/upload", jpeg_bytes, headers={"Content-Type": "application/octet-stream"}).read())
    blob = up["result"]["blob"]
    assert up["result"]["width"] == 600
    items = [{"id": f["id"], "fields": {"album": "Batch Album", "title": "T%d" % i},
              "pictures": [{"blob": blob, "type": 3, "desc": ""}]} for i, f in enumerate((mp3, flac))]
    res = wait_job(srv, call(srv, "files.save", items=items)["jobId"])["result"]
    assert res["errors"] == [] and len(res["saved"]) == 2
    files = {f["id"]: f for f in call(srv, "files.list")}
    assert files[mp3["id"]]["fields"]["album"] == "Batch Album"
    assert files[flac["id"]]["pictures"][0]["blob"] == blob
    assert files[flac["id"]]["version"] == 2

    # media: original cover bytes and a thumbnail
    body = _req(srv, "/media/blob/%s?t=secret" % blob, token=False).read()
    assert body == jpeg_bytes
    assert _req(srv, "/media/thumb/%s?s=64&t=secret" % blob, token=False).headers["Content-Type"] == "image/jpeg"

    # audio streaming with ranges; ALAC gets a lossless preview
    src = call(srv, "player.source", id=alac["id"])
    assert src["transcoded"] and src["mime"] == "audio/flac"
    r = _req(srv, src["url"] + "&t=secret", headers={"Range": "bytes=100-199"}, token=False)
    assert r.status == 206 and len(r.read()) == 100 and r.headers["Content-Range"].startswith("bytes 100-199/")
    direct = call(srv, "player.source", id=mp3["id"])
    assert not direct["transcoded"]

    # conversion plan + run
    plan = call(srv, "convert.plan", ids=[flac["id"], mp3["id"]], options={"target": "alac", "outputMode": "custom",
                                                                         "outputDir": str(tmp_path / "out")})
    assert plan[0]["plan"]["bitPerfect"] and not plan[1]["plan"]["bitPerfect"]
    out = wait_job(srv, call(srv, "convert.start", items=[{"id": flac["id"], "fields": files[flac["id"]]["fields"],
                                                           "pictures": [{"blob": blob, "type": 3, "desc": ""}]}],
                             options={"target": "alac", "outputMode": "custom", "outputDir": str(tmp_path / "out"),
                                      "addToList": True})["jobId"])
    r0 = out["result"]["results"][0]
    assert r0["state"] == "done" and r0["verified"], r0
    time.sleep(0.5)
    assert any(f["path"] == r0["path"] for f in call(srv, "files.list"))

    # rename from tags
    ren = call(srv, "rename.apply", items=[{"id": mp3["id"]}], pattern="{album} - {title}")
    assert ren["results"][0]["ok"] and ren["files"][0]["name"] == "Batch Album - T0.mp3"

    # quality analysis job
    q = wait_job(srv, call(srv, "quality.analyze", id=flac["id"])["jobId"])
    assert q["state"] == "done" and q["result"]["spectrogram"]["mime"] == "image/png"


def test_save_error_reported(srv, sample):
    job = call(srv, "files.add", paths=[sample("wav16")])["jobId"]
    wait_job(srv, job)
    f = call(srv, "files.list")[0]
    res = wait_job(srv, call(srv, "files.save", items=[{"id": f["id"], "fields": {"date": "yesterday"}}])["jobId"])
    assert res["result"]["errors"][0]["error"]["code"] == "invalid-date"

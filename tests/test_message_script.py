import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from pacttsclone.app import create_app
from pacttsclone.composition import insertion_points, quiet_insertion_points
from pacttsclone.config import Settings
from pacttsclone.domain import GenerationRequest, GenerationSettings, UserError, Waveform
from pacttsclone.message_script import parse_script
from pacttsclone.models import ChannelConfig
from pacttsclone.service import GenerationService
from pacttsclone.sfx import SfxSettings
from pacttsclone.studio import Studio

from .conftest import wait_job
from .test_v2 import wait_until


def effect_audio():
    stream = io.BytesIO()
    sf.write(stream, np.full(12000, 0.4), 48000, format="WAV", subtype="PCM_16")
    stream.seek(0)
    return stream


@pytest.fixture
def script_studio(tmp_path, engine, mp3):
    service = GenerationService(Settings(data_dir=tmp_path / "data"), engine)
    studio = Studio(service)
    for title in ("Pac", "Lula"):
        with mp3.open("rb") as stream:
            studio.voices.create(stream, title, title + ".mp3", title + " reference")
    voices = {v["title"]: v["id"] for v in service.store.all("voice")}
    studio.save_channel(
        ChannelConfig(
            name="test",
            commands={"!pac": voices["Pac"], "!lula": voices["Lula"]},
            user_cooldown_seconds=0,
        )
    )
    service.store.patch("channel", "test", enabled=True)
    studio.sfx.save(SfxSettings(title="Fart", triggers=["[fart]", "****"]), effect_audio())
    try:
        yield studio
    finally:
        studio.close()


def test_parse_switches_escaping_case_and_model_tags():
    effects = [{"id": "sound", "triggers": ["[fart]", "****"], "enabled": True}]
    result = parse_script(
        r"!PAC [happy] hello \[fart] !lula wow ****",
        {"!pac": "pac", "!lula": "lula"},
        effects,
    )
    assert result == [
        {"voice_id": "pac", "parts": [{"text": "[happy] hello [fart]"}]},
        {"voice_id": "lula", "parts": [{"text": "wow"}, {"sfx_id": "sound"}]},
    ]
    assert parse_script("!pac abc!lula def", {"!pac": "p"}, [])[0]["parts"] == [
        {"text": "abc!lula def"},
    ]


@pytest.mark.parametrize(
    "text",
    [
        "!pac hello !unknown world",
        "!pac !pac hi",
        "!pac hi !pac",
        "!pac a !pac b !pac c !pac d !pac e",
        "!pac " + "[fart]" * 9,
    ],
)
def test_parser_rejects_invalid_or_excess_work(text):
    with pytest.raises(UserError):
        parse_script(text, {"!pac": "p"}, [{"id": "s", "triggers": ["[fart]"]}])


def test_whole_speech_once_then_insert_at_word_boundary(script_studio, engine):
    studio = script_studio
    original = engine.synthesize

    def paused_speech(reference, request):
        waveform = original(reference, request)
        waveform.samples[
            round(0.31 * waveform.sample_rate) : round(0.39 * waveform.sample_rate)
        ] = 0
        return waveform

    engine.synthesize = paused_speech
    engine.align_words = lambda waveform: [
        {"text": "Hello", "timestamp": (0.0, 0.15)},
        {"text": "my", "timestamp": (0.15, 0.3)},
        {"text": "name", "timestamp": (0.4, 0.6)},
        {"text": "is", "timestamp": (0.6, 0.7)},
        {"text": "Pac", "timestamp": (0.7, 1.0)},
    ]
    job = studio.receive("test", "viewer", "!pac Hello, my [fart] name is Pac")
    result = wait_job(studio.service, job["id"])
    assert result["status"] == "succeeded", result["error"]
    assert [call[1].text for call in engine.calls] == ["Hello, my name is Pac"]
    details = result["metrics"]["composition"][0]
    assert details["mode"] == "whole_utterance"
    assert details["boundary_check"] == "quiet_gap"
    assert details["placements"][0]["speech_seconds"] == pytest.approx(0.35, abs=0.002)
    # Decode the actual final MP3 to verify inserted time and SFX placement.
    decoded = studio.service.outputs / "check.wav"
    studio.service.audio._run(
        "ffmpeg",
        [
            "-v",
            "error",
            "-y",
            "-i",
            str(studio.service.output_path(job["id"])),
            str(decoded),
        ],
    )
    samples, rate = sf.read(decoded)
    assert len(samples) / rate == pytest.approx(1.25, abs=0.02)
    assert np.mean(samples[int(0.4 * rate) : int(0.5 * rate)]) > 0.3
    wait_until(lambda: len(studio.playback.items("test")) == 1)
    assert len(studio.service.history()) == 1


def test_mismatched_alignment_uses_explicit_segmented_fallback(script_studio, engine):
    engine.align_words = lambda _: [{"text": "wrong", "timestamp": (0, 0.5)}]
    job = script_studio.receive("test", "viewer", "!pac hello [fart] world")
    result = wait_job(script_studio.service, job["id"])
    assert result["status"] == "succeeded"
    assert [call[1].text for call in engine.calls] == ["hello world", "hello", "world"]
    assert result["metrics"]["composition"][0]["mode"] == "segmented"


def test_multi_voice_snapshot_survives_effect_deletion(script_studio, engine):
    studio = script_studio
    with studio.service._lock:
        job = studio.receive("test", "viewer", "!pac hello [fart] !lula somethingelse ****")
        effect = studio.store.all("sfx")[0]
        studio.sfx.delete(effect["id"])
        for voice in studio.store.all("voice"):
            studio.voices.set_generation_settings(
                voice["id"],
                GenerationSettings(volume=0),
            )
    result = wait_job(studio.service, job["id"])
    assert result["status"] == "succeeded"
    assert [c[1].text for c in engine.calls] == ["hello", "somethingelse"]
    assert [c[1].ref_text for c in engine.calls] == ["Pac reference", "Lula reference"]
    assert all(c[1].volume == 100 for c in engine.calls)
    assert len(result["voice_ids"]) == 2
    assert result["voice_title"] == "Pac / Lula"
    wait_until(lambda: len(studio.playback.items("test")) == 1)


def test_moderation_across_effects_and_voices_before_render(script_studio, engine):
    studio = script_studio
    studio.store.patch("channel", "test", custom_filters=["secret phrase"])
    for message in ("!pac secret [fart] phrase", "!pac secret !lula phrase"):
        assert studio.receive("test", "viewer", message) is None
    assert not engine.calls
    assert not studio.service.history()


def test_limits_disabled_effects_and_single_message_cooldown(script_studio):
    studio = script_studio
    studio.store.patch("channel", "test", max_voice_sections=1)
    assert studio.receive("test", "viewer", "!pac hello !lula hi") is None
    studio.store.patch("channel", "test", max_voice_sections=4, user_cooldown_seconds=60)
    job = studio.receive("test", "viewer", "!pac hello !lula hi")
    assert job
    assert studio.receive("test", "viewer", "!pac another") is None
    wait_job(studio.service, job["id"])


def test_cancelling_queued_script_cleans_snapshot(script_studio):
    with script_studio.service._lock:
        job = script_studio.receive("test", "viewer", "!pac hello [fart] !lula hi")
        result = script_studio.service.cancel(job["id"])
        assert result["status"] == "cancelled"
        from pathlib import Path

        assert not Path(job["workspace"]).exists()
    assert not script_studio.playback.items("test")


def test_failure_in_later_voice_publishes_no_audio(script_studio, engine):
    original = engine.synthesize

    def fail(reference, request):
        if request.ref_text == "Lula reference":
            raise UserError("Failed second voice")
        return original(reference, request)

    engine.synthesize = fail
    job = script_studio.receive("test", "viewer", "!pac hello !lula hi")
    result = wait_job(script_studio.service, job["id"])
    assert result["status"] == "failed"
    assert "section 2" in result["error"]
    assert not result["output_url"]
    assert not script_studio.service.output_path(job["id"]).exists()
    assert not script_studio.playback.items("test")


def test_local_inline_effect_preserves_overrides_and_autoqueue(script_studio, engine):
    studio = script_studio
    voice = next(v for v in studio.store.all("voice") if v["title"] == "Pac")
    job = studio.generate_voice(
        voice["id"],
        GenerationRequest(
            text="hello ****",
            volume=40,
            autoqueue_general=True,
            requester_name="Local tester",
        ),
    )
    result = wait_job(studio.service, job["id"])
    assert result["status"] == "succeeded"
    assert engine.calls[0][1].volume == 40
    assert result["requester_name"] == "Local tester"
    # Completion callback may run immediately after status is committed.
    wait_until(lambda: studio.playback.items("playbackMain"))
    assert not studio.playback.items("test")


@pytest.mark.parametrize(
    "chunks",
    [
        [{"text": "hi", "timestamp": (None, 1)}],
        [{"text": "hi", "timestamp": (0, float("nan"))}],
        [{"text": "hi", "timestamp": (0, 2)}],
        [{"text": "hi", "timestamp": (0, 0.5)}, {"text": "hi", "timestamp": (0.2, 0.8)}],
    ],
)
def test_unsafe_alignment_is_rejected(chunks):
    with pytest.raises(UserError):
        insertion_points([{"text": "hi"}, {"sfx_id": "x"}, {"text": "hi"}], chunks, 1)


def test_sfx_api_validation_replacement_persistence_and_csrf(tmp_path, engine):
    settings = Settings(data_dir=tmp_path / "data")
    app = create_app(settings, engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        headers = {"x-pactts-token": token}
        assert client.post("/api/sfx", data={"title": "x"}).status_code == 403
        response = client.post(
            "/api/sfx",
            headers=headers,
            data={"title": "Fart", "triggers": "[fart]\n****"},
            files={"audio": ("fart.wav", effect_audio(), "audio/wav")},
        )
        assert response.status_code == 201, response.text
        effect = response.json()
        assert client.get(effect["audio_url"]).status_code == 200
        assert client.get("/api/state").json()["sfx"][0]["id"] == effect["id"]
        invalid = client.post(
            "/api/sfx",
            headers=headers,
            data={"title": "Bad", "triggers": "[happy]"},
            files={"audio": ("x.wav", effect_audio(), "audio/wav")},
        )
        assert invalid.status_code == 422
        duplicate = client.post(
            "/api/sfx",
            headers=headers,
            data={"title": "Dup", "triggers": "[fart]"},
            files={"audio": ("x.wav", effect_audio(), "audio/wav")},
        )
        assert duplicate.status_code == 422
        value = {k: effect[k] for k in SfxSettings.model_fields}
        value.update(enabled=False, volume=50, duration=0.1)
        assert (
            client.put("/api/sfx/" + effect["id"], headers=headers, json=value).status_code == 200
        )
        preview = client.get("/api/sfx/" + effect["id"] + "/preview")
        samples, rate = sf.read(io.BytesIO(preview.content))
        assert len(samples) / rate == pytest.approx(.1)
        assert np.mean(samples) == pytest.approx(.2, abs=.0001)
        assert (
            client.post(
                "/api/sfx/" + effect["id"] + "/audio",
                headers=headers,
                files={"audio": ("x.wav", effect_audio(), "audio/wav")},
            ).status_code
            == 200
        )
    app = create_app(settings, engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        effect = client.get("/api/sfx").json()[0]
        assert effect["volume"] == 50
        assert effect["duration"] == 0.1
        assert not effect["enabled"]
        headers = {"x-pactts-token": client.get("/api/session").json()["token"]}
        assert client.delete("/api/sfx/" + effect["id"], headers=headers).status_code == 200
        assert client.get(effect["audio_url"]).status_code == 404


def test_active_composite_cancellation_kills_worker_and_recovers(tmp_path, mp3):
    from pacttsclone.worker import ProcessRunner

    from .worker_fake import ProcessFakeEngine

    settings = Settings(data_dir=tmp_path / "data")
    runner = ProcessRunner(settings, ProcessFakeEngine)
    service = GenerationService(settings, runner=runner)
    studio = Studio(service)
    try:
        with mp3.open("rb") as stream:
            voice = studio.voices.create(stream, "Pac", "pac.mp3", "Known reference")
        studio.save_channel(
            ChannelConfig(
                name="test",
                commands={
                    "!pac": voice["id"],
                    "!lula": voice["id"],
                },
                user_cooldown_seconds=0,
            )
        )
        studio.store.patch("channel", "test", enabled=True)
        job = studio.receive("test", "viewer", "!pac hang !lula hello")
        wait_until(lambda: service.get(job["id"])["stage"] == "inference")
        pid = runner.pid
        service.cancel(job["id"])
        wait_until(lambda: service.get(job["id"])["status"] == "cancelled")
        assert runner.pid != pid
        assert not service.output_path(job["id"]).exists()
        assert not studio.playback.items("test")
        recovered = studio.receive("test", "viewer", "!pac hello !lula again")
        assert wait_job(service, recovered["id"])["status"] == "succeeded"
    finally:
        studio.close()


def test_matching_words_without_a_quiet_gap_cannot_cut_a_syllable():
    parts = [{"text": "hello"}, {"sfx_id": "sound"}, {"text": "world"}]
    chunks = [{"text": "hello", "timestamp": (0, 0.4)}, {"text": "world", "timestamp": (0.6, 1)}]
    samples = np.full(48000, 0.2, dtype=np.float32)
    with pytest.raises(UserError, match="No verified quiet gap"):
        quiet_insertion_points(parts, chunks, samples, 48000)
    samples[22000:26000] = 0
    assert quiet_insertion_points(parts, chunks, samples, 48000) == [0.5]


def test_multiple_effects_preserve_start_and_every_speech_sample(script_studio, engine):
    original = engine.synthesize

    def paused_speech(reference, request):
        waveform = original(reference, request)
        rate = waveform.sample_rate
        for left, right in ((0.31, 0.39), (0.61, 0.69)):
            waveform.samples[round(left * rate) : round(right * rate)] = 0
        return waveform

    engine.synthesize = paused_speech
    engine.align_words = lambda waveform: [
        {"text": "one", "timestamp": (0, 0.3)},
        {"text": "two", "timestamp": (0.4, 0.6)},
        {"text": "three", "timestamp": (0.7, 1)},
    ]
    job = script_studio.receive("test", "viewer", "!pac one [fart] two **** three")
    result = wait_job(script_studio.service, job["id"])
    assert result["status"] == "succeeded"
    details = result["metrics"]["composition"][0]
    assert details["speech_samples"] == 48000
    assert [p["output_seconds"] for p in details["placements"]] == pytest.approx(
        [0.35, 0.9], abs=0.002
    )
    assert len(engine.calls) == 1
    decoded = script_studio.service.outputs / "multiple-check.wav"
    script_studio.service.audio._run(
        "ffmpeg",
        [
            "-v",
            "error",
            "-y",
            "-i",
            str(script_studio.service.output_path(job["id"])),
            str(decoded),
        ],
    )
    samples, rate = sf.read(decoded)
    assert len(samples) / rate == pytest.approx(1.5, abs=0.02)
    expected = 0.1 * np.sin(2 * np.pi * 440 * np.arange(len(samples)) / rate)
    # First word's onset and body are retained; effects extend rather than replace speech.
    assert (
        np.corrcoef(
            samples[round(0.01 * rate) : round(0.15 * rate)],
            expected[round(0.01 * rate) : round(0.15 * rate)],
        )[0, 1]
        > 0.99
    )


def test_multiple_voices_keep_each_voice_onset_in_the_mp3(script_studio, engine):
    def speech(reference, request):
        frequency = 330 if request.ref_text.startswith("Pac") else 660
        engine.calls.append((reference, request))
        return Waveform(0.1 * np.sin(2 * np.pi * frequency * np.arange(24000) / 24000), 24000)

    engine.synthesize = speech
    job = script_studio.receive("test", "viewer", "!pac first !lula second")
    assert wait_job(script_studio.service, job["id"])["status"] == "succeeded"
    decoded = script_studio.service.outputs / "voices-check.wav"
    script_studio.service.audio._run(
        "ffmpeg",
        [
            "-v",
            "error",
            "-y",
            "-i",
            str(script_studio.service.output_path(job["id"])),
            str(decoded),
        ],
    )
    samples, rate = sf.read(decoded)
    assert len(samples) / rate == pytest.approx(2, abs=0.02)
    for offset, frequency in ((0, 330), (1, 660)):
        actual = samples[round((offset + 0.01) * rate) : round((offset + 0.15) * rate)]
        time = np.arange(len(actual)) / rate + 0.01
        assert np.corrcoef(actual, np.sin(2 * np.pi * frequency * time))[0, 1] > 0.99


def test_many_saved_effect_records_and_audio_survive_application_restart(tmp_path, engine):
    settings = Settings(data_dir=tmp_path / "data")
    app = create_app(settings, engine)
    ids = []
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = {"x-pactts-token": client.get("/api/session").json()["token"]}
        for title in ("Fart", "Bleep", "Bell"):
            response = client.post(
                "/api/sfx",
                headers=headers,
                data={"title": title, "triggers": "[" + title.lower() + "]"},
                files={"audio": ("effect.wav", effect_audio(), "audio/wav")},
            )
            assert response.status_code == 201, response.text
            ids.append(response.json()["id"])
        assert len(set(ids)) == 3
    assert all((settings.data_dir / "sfx" / (key + ".wav")).is_file() for key in ids)
    restarted = create_app(settings, engine)
    with TestClient(restarted, base_url="http://127.0.0.1") as client:
        records = client.get("/api/sfx").json()
        assert {record["id"] for record in records} == set(ids)
        assert {record["title"] for record in records} == {"Fart", "Bleep", "Bell"}
        for record in records:
            assert client.get(record["audio_url"]).status_code == 200

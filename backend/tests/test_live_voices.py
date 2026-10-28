import numpy as np
import pytest

from app.services import live_voices
from app.services.live_voices import VoiceBook, VoiceEmbedder

RATE = live_voices.SAMPLE_RATE


def _unit(*xs):
    v = np.array(xs, dtype=np.float64)
    return v / np.linalg.norm(v)


def _voice(angle):
    """A voiceprint at an angle (degrees) from the first axis: two of them are cos(difference) apart."""
    a = np.radians(angle)
    return _unit(np.cos(a), np.sin(a))


def test_fbank_matches_the_features_the_model_was_trained_with():
    t = np.arange(RATE) / RATE
    wav = (0.3 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 1500 * t) + 0.05 * np.sin(2 * np.pi * 3100 * t)).astype(np.float32)
    feats = live_voices.fbank(wav)
    assert feats.shape == (101, 80)
    # Values from SpeechBrain's Fbank(n_mels=80) with the sentence mean taken off.
    for frame, expected in {0: [42.2, 45.48, 17.02, 11.39], 50: [-1.38, -1.59, -0.44, -0.27], 100: [42.26, 45.52, 17.03, 11.43]}.items():
        assert feats[frame, [0, 10, 40, 79]] == pytest.approx(expected, abs=0.05)


def test_a_piece_too_short_to_hold_a_voice_has_no_voiceprint(tmp_path):
    embedder = VoiceEmbedder(tmp_path / "none.onnx")
    assert not embedder.available()
    assert embedder.embed(bytes(int(1.4 * live_voices.BYTES_PER_SECOND))) is None


@pytest.mark.skipif(not VoiceEmbedder().available(), reason="the speaker model file is not in models/")
def test_the_model_gives_unit_voiceprints_that_tell_two_sounds_apart():
    embedder = VoiceEmbedder()
    t = np.arange(int(2 * RATE)) / RATE

    def pcm(hz):
        return (np.sin(2 * np.pi * hz * t) * 8000 + np.sin(2 * np.pi * 2.3 * hz * t) * 3000).astype(np.int16).tobytes()

    a, a2, b = embedder.embed(pcm(140)), embedder.embed(pcm(140)), embedder.embed(pcm(310))
    assert np.linalg.norm(a) == pytest.approx(1.0) and a.shape == (192,)
    assert float(a @ a2) == pytest.approx(1.0)
    assert float(a @ b) < 0.99


def test_the_same_voice_stays_one_voice_and_a_far_one_is_new():
    book = VoiceBook()
    assert book.hear(0.0, _voice(0), 3).voice == 1
    assert book.hear(5.0, _voice(10), 3).voice == 1
    assert book.hear(10.0, _voice(80), 3).voice == 2
    assert book.hear(15.0, _voice(5), 3).voice == 1
    assert book.hear(20.0, _voice(85), 3).voice == 2


def test_a_piece_only_just_close_enough_goes_to_the_closest_voice_but_is_not_sure():
    book = VoiceBook()
    book.hear(0.0, _voice(0), 3)
    # 65 degrees away (cosine 0.42) is over NEW_BELOW and under SURE_ABOVE.
    heard = book.hear(5.0, _voice(65), 3)
    assert (heard.voice, heard.sure) == (1, False)
    assert book.hear(10.0, _voice(20), 3).sure


def test_voices_stop_at_the_limit():
    book = VoiceBook()
    for i in range(live_voices.MAX_VOICES + 3):
        book.hear(float(i), _unit(*[1.0 if j == i else 0.0 for j in range(live_voices.MAX_VOICES + 3)]), 2)
    assert len(book.voices) == live_voices.MAX_VOICES


def test_merging_two_voices_moves_their_past_and_future():
    book = VoiceBook()
    book.hear(0.0, _voice(0), 3)
    book.hear(5.0, _voice(80), 3)
    book.hear(10.0, _voice(85), 3)
    assert book.merge(1, 2)
    assert list(book.voices) == [1]
    assert book.voices[1].pieces == 3
    assert book.hear(15.0, _voice(82), 3).voice == 1
    # The merged voice's profile now covers both, so a line moved off it is found again by its key.
    assert book.move(10.0, None) == 3
    assert not book.merge(1, 1) and not book.merge(1, 9)


def test_moving_a_line_teaches_the_voices():
    book = VoiceBook()
    book.hear(0.0, _voice(0), 3)
    book.hear(5.0, _voice(90), 3)
    # This one was put on voice 1 but is the second person.
    assert book.hear(10.0, _voice(40), 3).voice == 1
    assert book.move(10.0, 2) == 2
    assert book.voices[1].pieces == 1 and book.voices[2].pieces == 2
    assert book.move(10.0, 2) == 2
    assert book.move(99.0, 2) is None
    assert book.move(10.0, 7) is None


def test_moving_the_only_line_of_a_voice_to_a_new_one_leaves_one_voice():
    book = VoiceBook()
    book.hear(0.0, _voice(0), 3)
    book.hear(5.0, _voice(90), 3)
    new = book.move(5.0, None)
    assert new == 3 and sorted(book.voices) == [1, 3]

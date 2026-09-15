from app.services.stt_batch import use_channel_stt, wav_channel_count


def _wav(channels: int) -> bytes:
    # Minimal RIFF/WAVE header; audio payload unused.
    return (
        b"RIFF"
        + (36).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + channels.to_bytes(2, "little")
        + (8000).to_bytes(4, "little")
        + (16000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + (0).to_bytes(4, "little")
    )


def test_wav_channel_count_reads_header():
    assert wav_channel_count(_wav(2)) == 2
    assert wav_channel_count(_wav(1)) == 1


def test_non_wav_counts_as_mono():
    assert wav_channel_count(b"ID3mp3") == 1


def test_vocify_call_always_uses_channel_stt():
    assert use_channel_stt(b"ID3", source="vocify_call") is True
    assert use_channel_stt(_wav(1), source="hubspot_call") is False
    assert use_channel_stt(_wav(2), source="hubspot_call") is True

from app.services.speechmatics_batch import batch_transcription_config


def test_speaker_diarization_default():
    cfg = batch_transcription_config(language="es", diarization=True)
    assert cfg["diarization"] == "speaker"
    assert "speaker_diarization_config" in cfg


def test_stereo_uses_channel_diarization():
    cfg = batch_transcription_config(language="es", diarization=True, channel=True)
    assert cfg["diarization"] == "channel"
    assert "speaker_diarization_config" not in cfg

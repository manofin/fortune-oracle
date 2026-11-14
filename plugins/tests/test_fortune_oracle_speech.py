"""Real media probing + synthesis contract/routing. Does not fake a live TTS test."""
import json
import math
import shutil
import subprocess
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from hermes_ext.fortune_oracle import speech
from hermes_ext.fortune_oracle.platforms import telegram, line

READING = {'ok':True,'kind':'test','text':'오늘은 작은 행동을 하나 정해 보세요.','evidence':{'score':60}}
PROFILE = {'birth_date':'1990-05-15','birth_time':'07:30','gender':'male','birth_place':'PRIVATE PLACE'}


@pytest.fixture(scope='module')
def media(tmp_path_factory):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Audio contract tests require ffmpeg and ffprobe')
    root = tmp_path_factory.mktemp('audio')
    files = {}
    for name,codec in [('sample.mp3','libmp3lame'),('sample.ogg','libopus'),('sample.wav','pcm_s16le')]:
        path = root/name
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.25',
                        '-c:a',codec,str(path)],check=True,capture_output=True)
        files[path.suffix] = path
    return files


def synthesizer(media, *, chunks=1, suffix='.mp3'):
    calls = []
    def run(**kwargs):
        calls.append(kwargs)
        base = Path(kwargs['output_path'])
        paths = []
        for i in range(chunks):
            dest = base.with_name(f'narration_{i}').with_suffix(suffix)
            shutil.copyfile(media[suffix],dest)
            paths.append(str(dest))
        return json.dumps({'success':True,'file_path':paths[0],'file_paths':paths,'provider':'contract-test'})
    return run,calls


def test_probe_checks_actual_codec_duration_and_not_extension(media,tmp_path):
    assert speech.inspect_audio(media['.ogg'])['voice_compatible'] is True
    assert speech.inspect_audio(media['.mp3'])['voice_compatible'] is False
    assert 200 <= speech.inspect_audio(media['.mp3'])['duration_ms'] <= 400
    renamed = tmp_path/'fake.ogg'
    shutil.copyfile(media['.wav'],renamed)
    probe = speech.inspect_audio(renamed)
    assert probe['format'] == 'wav' and not probe['voice_compatible']
    broken = tmp_path/'garbage.mp3'
    broken.write_text('not audio')
    assert speech.inspect_audio(broken) is None
    empty = tmp_path/'empty.mp3'
    empty.touch()
    assert speech.inspect_audio(empty) is None
    assert speech.inspect_audio(tmp_path/'missing.mp3') is None


def test_calculated_text_sent_once_and_all_chunks_preserved(media,tmp_path):
    tts,calls = synthesizer(media,chunks=2)
    result = speech.synthesize_reading(READING,tts=tts,output_root=tmp_path)
    assert result['ok'] is True
    assert len(calls) == 1 and calls[0]['text'] == READING['text']
    assert result['reading'] == READING
    assert len(result['audio_files']) == len(result['audio']) == 2
    assert result['media_response'].count('MEDIA:') == 2
    assert result['delivery'] == 'audio'
    assert all(Path(p).is_file() for p in result['audio_files'])


@pytest.mark.parametrize('language, spoken_language', [('ko', 'Korean'), ('en-US', 'English')])
def test_narration_language_preserves_completed_reading(media, tmp_path, language, spoken_language):
    tts, calls = synthesizer(media)
    reading = {**READING, 'language': language}
    result = speech.synthesize_reading(reading, tts=tts, output_root=tmp_path)
    assert result['ok']
    assert calls[0]['text'] == reading['text']
    assert spoken_language in calls[0]['instructions']
    assert result['reading'] == reading
    assert result['language'] == language.split('-')[0]


def test_unsupported_narration_language_does_not_send_text(tmp_path):
    with patch.object(speech, '_runtime_tts') as runtime:
        result = speech.synthesize_reading({**READING, 'language': 'private-invalid'}, output_root=tmp_path)
    assert not runtime.called and result['error'] == 'unsupported_language'
    assert result['text_fallback'] == READING['text']
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('language', ['ko','en'])
def test_iching_voice_describes_same_draw_in_words_once(media, tmp_path, language):
    tts, calls = synthesizer(media)
    result = telegram.prepare_reading('/voice_fortune iching PUBLIC_TEST | 7 8 9 8 7 6',
                                      language=language, tts=tts, output_root=tmp_path)
    assert result['ok'] and len(calls) == 1
    source = result['reading']
    assert source['lines'] == [7,8,9,8,7,6] and source['changing_lines'] == [3,6]
    assert source['hexagram']['number'] == 63 and source['transformed']['number'] == 42
    assert '━' in result['text'] and '━' not in calls[0]['text']
    assert 'PUBLIC_TEST' not in calls[0]['text']
    assert result['spoken_text'] == calls[0]['text'] == source['speech_text']
    if language == 'en':
        assert 'Line 6: old yin, changing.' in calls[0]['text']
        assert 'Line 3: old yang, changing.' in calls[0]['text']
        assert 'Line 2: young yin, unchanging.' in calls[0]['text']
        assert 'Line 1: young yang, unchanging.' in calls[0]['text']
    else:
        assert '6효: 노음, 변화하는 음효.' in calls[0]['text']
        assert '3효: 노양, 변화하는 양효.' in calls[0]['text']


@pytest.mark.parametrize('narration', ['', None, 123])
def test_invalid_prepared_narration_keeps_visual_fallback_without_tts(tmp_path, narration):
    with patch.object(speech, '_runtime_tts') as runtime:
        result = speech.synthesize_reading({**READING,'speech_text':narration},output_root=tmp_path)
    assert not runtime.called and result['error'] == 'invalid_narration'
    assert result['text_fallback'] == READING['text'] and list(tmp_path.iterdir()) == []


def test_line_same_audio_basename_never_reuses_another_jobs_public_url(media, tmp_path):
    responses = []
    for name in ('job_a','job_b'):
        job = tmp_path/name
        job.mkdir()
        sample = job/'narration.mp3'
        shutil.copyfile(media['.mp3'], sample)
        responses.append(line.prepare_voice_fortune(text='public test',public_url='https://example.org',audio_file=sample))
    assert all(response['ok'] for response in responses)
    assert responses[0]['media_url'] != responses[1]['media_url']
    for response in responses:
        assert response['media_url'].endswith(response['media_key'])
        assert 'narration.mp3' not in response['media_url'] and 'job_' not in response['media_url']
        assert response['message']['originalContentUrl'] == response['media_url']
        assert Path(response['audio_file']).is_file()


def test_opus_delivery_uses_verified_voice_tag(media,tmp_path):
    tts,_ = synthesizer(media,suffix='.ogg')
    result = speech.synthesize_reading(READING,tts=tts,output_root=tmp_path)
    assert result['delivery'] == 'voice'
    assert result['media_response'].startswith('[[audio_as_voice]]')


@pytest.mark.parametrize('response',[{'success':False,'error':'PRIVATE TOKEN'},'not json',
    {'success':True}, {'success':True,'file_path':'/missing'}, None])
def test_provider_failure_is_safe_text_fallback_and_cleans_job(response,tmp_path):
    result = speech.synthesize_reading(READING,tts=lambda **kw:response,output_root=tmp_path)
    assert result['ok'] is False and result['text_fallback'] == READING['text']
    assert 'PRIVATE' not in str(result) and 'media_response' not in result
    assert list(tmp_path.iterdir()) == []


def test_external_file_not_delivered_or_deleted(media,tmp_path):
    external = media['.mp3']
    result = speech.synthesize_reading(READING,tts=lambda **kw:{'success':True,'file_path':str(external)},output_root=tmp_path)
    assert result['ok'] is False
    assert external.exists()
    assert list(tmp_path.iterdir()) == []


def test_one_invalid_chunk_discards_entire_delivery(media,tmp_path):
    def provider(**kw):
        valid = Path(kw['output_path'])
        shutil.copyfile(media['.mp3'],valid)
        bad = valid.with_name('bad.mp3')
        bad.write_bytes(b'')
        return {'success':True,'file_paths':[str(valid),str(bad)]}
    result = speech.synthesize_reading(READING,tts=provider,output_root=tmp_path)
    assert not result['ok'] and list(tmp_path.iterdir()) == []


def test_no_reading_no_tts_and_no_scratch(tmp_path):
    with patch.object(speech,'_runtime_tts') as runtime:
        for reading in (None,{}, {'ok':False,'text':'계산 불가'}, {'ok':True,'text':''}):
            result = speech.synthesize_reading(reading,output_root=tmp_path)
            assert not result['ok']
        assert not runtime.called
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('speed',[0,3,float('nan'),float('inf'),True,'1'])
def test_invalid_speed_does_not_call_provider(speed,tmp_path):
    with patch.object(speech,'_runtime_tts') as runtime:
        result = speech.synthesize_reading(READING,speed=speed,output_root=tmp_path)
    assert result['error'] == 'invalid_speed' and not runtime.called


def test_existing_runtime_tool_is_default_and_import_failure_falls_back(media,tmp_path):
    tts,calls = synthesizer(media)
    with patch.object(speech,'_runtime_tts',return_value=tts) as runtime:
        assert speech.synthesize_reading(READING,output_root=tmp_path)['ok']
    assert runtime.call_count == 1 and calls
    with patch.object(speech,'_runtime_tts',side_effect=ImportError('PRIVATE dependency')):
        result = speech.synthesize_reading(READING,output_root=tmp_path)
    assert not result['ok'] and 'PRIVATE' not in str(result)


def test_daily_voice_has_actual_evidence_and_no_raw_birth_data(media,tmp_path):
    tts,calls = synthesizer(media)
    result = telegram.prepare_reading('/voice_fortune',profile=PROFILE,tts=tts,output_root=tmp_path)
    assert result['ok']
    assert result['reading']['kind'] == 'daily'
    assert result['reading']['evidence']['day_pillar']
    for private in ('1990-05-15','07:30','PRIVATE PLACE'):
        assert private not in calls[0]['text']
    with patch.object(speech,'_runtime_tts') as runtime:
        assert not telegram.prepare_reading('/voice_fortune',profile=None)['ok']
        assert not runtime.called


def test_tarot_voice_reuses_same_draw_evidence_and_invalid_input_skips_tts(media,tmp_path):
    tts,calls = synthesizer(media)
    result = telegram.prepare_reading('/운세음성 tarot 질문 | 0 8r 21',tts=tts,output_root=tmp_path)
    assert result['ok']
    assert [c['id'] for c in result['reading']['cards']] == [0,8,21]
    assert len(calls) == 1 and calls[0]['text'] == result['reading']['text']
    assert not telegram.prepare_reading('/voice_fortune voice_fortune')['ok']
    assert not telegram.prepare_reading('/voice_fortune tarot',tts=tts,output_root=tmp_path)['ok']
    assert len(calls) == 1


def test_telegram_audio_guard_and_line_mp3_duration_payload(media,tmp_path):
    assert telegram.prepare_voice_fortune(text='풀이',tts_available=True,audio_file=tmp_path/'missing.mp3')['ok'] is False
    tg = telegram.prepare_voice_fortune(text='풀이',tts_available=True,audio_file=media['.ogg'])
    assert tg['ok'] and tg['delivery'] == 'voice'
    wav = telegram.prepare_voice_fortune(text='풀이',tts_available=True,audio_file=media['.wav'])
    assert wav['delivery'] == 'document'
    response = line.prepare_voice_fortune(text='풀이',public_url='https://example.org',audio_file=media['.mp3'])
    assert response['ok'] and response['message']['duration'] == response['duration_ms'] > 0
    assert response['message']['originalContentUrl'] == response['media_url']
    assert not line.prepare_voice_fortune(text='풀이',public_url='https://example.org',audio_file=media['.wav'])['ok']

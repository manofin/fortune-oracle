"""Calculated reading → existing Hermes TTS → verified audio delivery.

Hermes runtime TTS is imported only on request. No sys.path changes, provider
installation, credential loading or gateway changes here. An injected callable
may implement the same text_to_speech_tool contract for another host.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path


def inspect_audio(audio_file) -> dict | None:
    """Verify an actual audio stream and duration, not just an extension or path."""
    try:
        path = Path(audio_file).resolve(strict=True)
        if not path.is_file() or not 0 < path.stat().st_size <= 50 * 1024 * 1024:
            return None
        if any(c in str(path) for c in ('\n','\r','\x00')):
            return None
        probe = shutil.which('ffprobe')
        if not probe:
            return None
        result = subprocess.run([probe,'-v','error','-show_entries',
            'stream=codec_type,codec_name,duration:format=duration,format_name',
            '-of','json',str(path)],capture_output=True,text=True,timeout=10,check=False)
        if result.returncode:
            return None
        info = json.loads(result.stdout)
        streams = info.get('streams',[])
        audio = [s for s in streams if s.get('codec_type') == 'audio']
        if len(audio) != 1 or any(s.get('codec_type') != 'audio' for s in streams):
            return None
        duration = float(info.get('format',{}).get('duration') or audio[0].get('duration') or 0)
        if not math.isfinite(duration) or duration <= 0:
            return None
        fmt = info.get('format',{}).get('format_name','')
        codec = audio[0].get('codec_name','')
        if round(duration*1000) <= 0:
            return None
        return {'path':str(path),'duration_ms':round(duration*1000),
                'format':fmt,'codec':codec,'voice_compatible':fmt == 'ogg' and codec == 'opus'}
    except (OSError,ValueError,TypeError,subprocess.TimeoutExpired):
        return None


def _runtime_tts():
    from tools.tts_tool import text_to_speech_tool
    return text_to_speech_tool


def synthesize_reading(reading: dict, *, tts=None, output_root=None, speed=1.0, provider=None) -> dict:
    """Reuse a computed text once; retain all delivery chunks, never fabricate audio.

    Provider may return JSON or a dict with success/file_path/file_paths.
    Files must be generated inside this request's anonymous output directory.
    """
    text = reading.get('text','') if isinstance(reading,dict) else ''
    if not isinstance(reading,dict) or not reading.get('ok',False) or not isinstance(text,str) or not text.strip():
        return {'ok':False,'error':'reading_unavailable','text_fallback':text,
                'reading':reading}
    fallback = {'ok':False,'error':'tts_unavailable','text_fallback':text,'reading':reading}
    spoken = reading.get('speech_text', text)
    if not isinstance(spoken, str) or not spoken.strip():
        return {**fallback, 'error':'invalid_narration'}
    from .localization import language_code
    try:
        language = language_code(reading.get('language'))
    except ValueError:
        return {**fallback, 'error':'unsupported_language'}
    if not isinstance(speed,(int,float)) or isinstance(speed,bool) or not math.isfinite(speed) or not 0.5 <= speed <= 2.0:
        return {**fallback,'error':'invalid_speed'}
    job = None
    try:
        function = tts if tts is not None else _runtime_tts()
        root = Path(output_root) if output_root is not None else Path(tempfile.gettempdir())/'fortune_oracle_voice'
        root.mkdir(parents=True,exist_ok=True)
        job = Path(tempfile.mkdtemp(prefix='reading_',dir=root)).resolve()
        output = job/'narration.mp3'
        # Narration follows the calculated text rather than asking TTS to invent a reading.
        response = function(text=spoken,output_path=str(output),speed=float(speed),
                            instructions='Read the provided text faithfully in '
                            + ('English' if language == 'en' else 'Korean')
                            + ' in a calm, conversational voice. Do not add or change the reading.',
                            provider=provider)
        data = json.loads(response) if isinstance(response,str) else response
        if not isinstance(data,dict) or data.get('success') is not True:
            raise ValueError('No audio generated')
        paths = data.get('file_paths') or [data.get('file_path')]
        if not isinstance(paths,list) or not paths or len(paths) > 20:
            raise ValueError('Invalid delivery files')
        verified = []
        for path in paths:
            resolved = Path(path).resolve(strict=True)
            resolved.relative_to(job)
            audio = inspect_audio(resolved)
            if audio is None:
                raise ValueError('Invalid audio stream')
            verified.append(audio)
        voice = all(a['voice_compatible'] for a in verified)
        delivery = 'voice' if voice else 'audio' if all(a['format'] == 'mp3' for a in verified) else 'document'
        tags = '\n'.join('MEDIA:' + a['path'] for a in verified)
        if voice:
            tags = '[[audio_as_voice]]\n' + tags
        return {'ok':True,'text':text,'spoken_text':spoken,'audio_file':verified[0]['path'],
                'audio_files':[a['path'] for a in verified],'audio':verified,
                'delivery':delivery,'media_response':tags,
                'reading':reading,'provider':data.get('provider','configured'),'language':language}
    except Exception:
        if job is not None:
            shutil.rmtree(job,ignore_errors=True)
        return fallback


def prepare_daily_voice(profile, *, target_date=None, tts=None, output_root=None, speed=1.0, provider=None):
    from .daily_fortune_engine import build_personalized_daily, render_daily_channel_text
    daily = build_personalized_daily(profile,target_date=target_date)
    if not daily:
        return {'ok':False,'error':'reading_unavailable',
                'text_fallback':'등록된 출생정보가 없거나 계산하지 못했습니다. 출생정보를 확인해 주세요.'}
    reading = {'ok':True,'kind':'daily','text':render_daily_channel_text(daily),
               'language':daily.get('language','ko'),
               'evidence':{'day_pillar':daily['day_pillar'],'dayun_pillar':daily['dayun_pillar'],
                           'score':daily['score'],'basis':daily['dayun_basis']}}
    return synthesize_reading(reading,tts=tts,output_root=output_root,speed=speed,provider=provider)

#!/usr/bin/env python3
"""
Transcribe Web App - Flask application for video/audio transcription
"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from flask import Flask, render_template, request, Response, jsonify

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2500 * 1024 * 1024  # 2.5GB max upload
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'

SCRIPTS_DIR = Path(__file__).parent / 'scripts'


def stream_output(process):
    """Stream subprocess output as SSE events."""
    for line in iter(process.stderr.readline, ''):
        if line:
            yield f"data: {json.dumps({'type': 'progress', 'message': line.strip()})}\n\n"
    process.wait()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/transcribe', methods=['POST'])
def transcribe():
    """Handle transcription request with SSE streaming."""

    # Extract form data BEFORE entering generator (request context ends after this function returns)
    url = request.form.get('url', '').strip()
    api_key = request.form.get('api_key', '').strip()
    provider = request.form.get('provider', 'groq')
    timestamps = request.form.get('timestamps') == 'true'
    uploaded_file = request.files.get('file')

    # Save uploaded file immediately if present
    saved_upload_path = None
    if uploaded_file and uploaded_file.filename:
        filename = f"{uuid.uuid4()}_{uploaded_file.filename}"
        saved_upload_path = app.config['UPLOAD_FOLDER'] / filename
        uploaded_file.save(saved_upload_path)

    def generate():
        audio_path = None
        temp_audio = None
        upload_path = saved_upload_path

        try:
            if not api_key:
                yield f"data: {json.dumps({'type': 'error', 'message': 'APIキーが入力されていません'})}\n\n"
                return

            if not url and not upload_path:
                yield f"data: {json.dumps({'type': 'error', 'message': 'URLまたはファイルを入力してください'})}\n\n"
                return

            # Handle file upload
            if upload_path:
                yield f"data: {json.dumps({'type': 'progress', 'message': 'ファイルを処理中...'})}\n\n"

                # Convert to mp3 if needed
                if not str(upload_path).endswith('.mp3'):
                    yield f"data: {json.dumps({'type': 'progress', 'message': '音声形式を変換中...'})}\n\n"
                    temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
                    temp_audio.close()

                    cmd = ['ffmpeg', '-y', '-i', str(upload_path), '-vn', '-acodec', 'libmp3lame', '-b:a', '128k', temp_audio.name]
                    result = subprocess.run(cmd, capture_output=True, text=True)

                    if result.returncode != 0:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'変換エラー: {result.stderr[:200]}'})}\n\n"
                        return

                    audio_path = temp_audio.name
                    os.unlink(upload_path)  # Clean up original
                else:
                    audio_path = str(upload_path)

            # Handle URL download
            elif url:
                yield f"data: {json.dumps({'type': 'progress', 'message': '動画をダウンロード中...'})}\n\n"

                # Try yt-dlp first
                temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
                temp_audio.close()

                # Check if it's a Vimeo URL
                if 'vimeo.com' in url:
                    # Try download_vimeo.py first
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Vimeo HLSダウンロード開始...'})}\n\n"
                    cmd = [
                        sys.executable, str(SCRIPTS_DIR / 'download_vimeo.py'),
                        url, '-o', temp_audio.name
                    ]
                    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                    # Stream stderr for progress
                    stdout_data = ""
                    for line in iter(process.stderr.readline, ''):
                        if line.strip():
                            yield f"data: {json.dumps({'type': 'progress', 'message': line.strip()})}\n\n"

                    stdout_data, _ = process.communicate()

                    if process.returncode == 0:
                        try:
                            output = json.loads(stdout_data)
                            audio_path = output.get('path', temp_audio.name)
                        except:
                            audio_path = temp_audio.name
                    else:
                        # Fall back to yt-dlp
                        yield f"data: {json.dumps({'type': 'progress', 'message': 'Vimeo HLS失敗、yt-dlpを試行中...'})}\n\n"
                        cmd = [
                            sys.executable, str(SCRIPTS_DIR / 'download_audio.py'),
                            url, '-o', temp_audio.name
                        ]
                        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                        stdout_data = ""
                        for line in iter(process.stderr.readline, ''):
                            if line.strip():
                                yield f"data: {json.dumps({'type': 'progress', 'message': line.strip()})}\n\n"

                        stdout_data, _ = process.communicate()

                        if process.returncode != 0:
                            error_detail = stderr_data if 'stderr_data' in dir() else ''
                            yield f"data: {json.dumps({'type': 'error', 'message': f'ダウンロードエラー (code: {process.returncode})\\n{error_detail[:500]}'})}\n\n"
                            return

                        try:
                            output = json.loads(stdout_data)
                            audio_path = output.get('path', temp_audio.name)
                        except:
                            audio_path = temp_audio.name
                else:
                    # Use download_audio.py for other URLs
                    cmd = [
                        sys.executable, str(SCRIPTS_DIR / 'download_audio.py'),
                        url, '-o', temp_audio.name
                    ]
                    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                    stdout_data = ""
                    for line in iter(process.stderr.readline, ''):
                        if line.strip():
                            yield f"data: {json.dumps({'type': 'progress', 'message': line.strip()})}\n\n"

                    stdout_data, _ = process.communicate()

                    if process.returncode != 0:
                        # Collect all stderr output
                        all_stderr = []
                        for line in iter(process.stderr.readline, ''):
                            all_stderr.append(line)
                        stderr_text = ''.join(all_stderr)
                        yield f"data: {json.dumps({'type': 'error', 'message': f'ダウンロードエラー (code: {process.returncode})\\n{stderr_text[:500]}'})}\n\n"
                        return

                    try:
                        output = json.loads(stdout_data)
                        audio_path = output.get('path', temp_audio.name)
                    except:
                        audio_path = temp_audio.name

                yield f"data: {json.dumps({'type': 'progress', 'message': 'ダウンロード完了'})}\n\n"

            # Transcribe
            yield f"data: {json.dumps({'type': 'progress', 'message': '文字起こし開始...'})}\n\n"

            cmd = [
                sys.executable, str(SCRIPTS_DIR / 'transcribe.py'),
                audio_path,
                '--api-key', api_key,
                '--provider', provider,
                '--language', 'ja'
            ]

            if timestamps:
                cmd.append('--timestamps')

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            # Stream stderr for progress
            for line in iter(process.stderr.readline, ''):
                if line.strip():
                    yield f"data: {json.dumps({'type': 'progress', 'message': line.strip()})}\n\n"

            stdout_data, stderr_data = process.communicate()

            if process.returncode != 0:
                yield f"data: {json.dumps({'type': 'error', 'message': f'文字起こしエラー (code: {process.returncode})\\n{stderr_data[:500]}'})}\n\n"
                return

            transcript = stdout_data

            yield f"data: {json.dumps({'type': 'complete', 'transcript': transcript})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        finally:
            # Cleanup
            if audio_path and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                except:
                    pass

    return Response(generate(), mimetype='text/event-stream')


if __name__ == '__main__':
    # Ensure upload folder exists
    app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)

    print("Transcribe Web App")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000, threaded=True)

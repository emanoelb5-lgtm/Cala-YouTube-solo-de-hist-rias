"""Generate neural Brazilian narration and subtitles from actual word timings."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[1]


def srt_time(seconds: float) -> str:
    milliseconds = round(max(0, seconds) * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def make_subtitles(words: list[dict]) -> str:
    groups: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        candidate = " ".join(w["text"] for w in current + [word])
        span = (word["offset"] + word["duration"] - (current or [word])[0]["offset"]) / 10000000
        if current and (len(candidate) > 78 or len(textwrap.wrap(candidate, 42)) > 2 or span > 5.8):
            groups.append(current)
            current = []
        current.append(word)
        if word["text"].endswith((".", "?", "!")) and len(" ".join(w["text"] for w in current)) >= 20:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    lines = []
    for number, group in enumerate(groups, 1):
        start = group[0]["offset"] / 10000000
        end = (group[-1]["offset"] + group[-1]["duration"]) / 10000000
        spoken = " ".join(word["text"] for word in group)
        lines.append(f"{number}\n{srt_time(start)} --> {srt_time(end)}\n{textwrap.fill(spoken, 42)}\n")
    return "\n".join(lines)


def restore_punctuation(words: list[dict], text: str) -> list[dict]:
    source = text.split()
    normalize = lambda value: re.sub(r"\W", "", value).casefold()
    if len(source) == len(words) and all(normalize(token) == normalize(word["text"]) for token, word in zip(source, words)):
        return [{**word, "text": token} for token, word in zip(source, words)]
    return words


async def generate(text: str, voice: dict, output: Path, rate: str) -> dict:
    import edge_tts
    import edge_tts.communicate
    # Honor the configured system CA bundle while keeping certificate verification on.
    if os.environ.get("SSL_CERT_FILE"):
        edge_tts.communicate._SSL_CTX = ssl.create_default_context()
    output.mkdir(parents=True, exist_ok=True)
    audio_tmp = output / "narracao.partial.mp3"
    words: list[dict] = []
    for attempt in range(3):
        words = []
        try:
            request = edge_tts.Communicate(
                text, voice["name"], rate=rate, pitch=voice.get("pitch", "+0Hz"),
                boundary="WordBoundary", connect_timeout=15, receive_timeout=60,
            )
            with audio_tmp.open("wb") as stream:
                async for chunk in request.stream():
                    if chunk["type"] == "audio":
                        stream.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append({key: chunk[key] for key in ("offset", "duration", "text")})
            if audio_tmp.stat().st_size < 1000 or len(words) < max(1, int(len(text.split()) * 0.65)):
                raise ValueError("Áudio ou marcações da narração incompletos.")
            break
        except Exception:
            audio_tmp.unlink(missing_ok=True)
            if attempt == 2:
                raise
            await asyncio.sleep(2 * (attempt + 1))
    duration = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_tmp)],
        text=True,
    ).strip())
    audio_tmp.replace(output / "narracao.mp3")
    words = restore_punctuation(words, text)
    (output / "legendas.srt").write_text(make_subtitles(words), encoding="utf-8")
    (output / "words.json").write_text(json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"engine": "edge_tts", "voice": voice["name"], "rate": rate,
              "duration_seconds": duration, "word_boundaries": len(words),
              "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    (output / "narracao.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/channel.json")
    parser.add_argument("--rate", help="Velocidade do próprio sintetizador, por exemplo -3%%.")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    text = args.text_file.read_text(encoding="utf-8").strip()
    if not text:
        parser.error("O texto de narração está vazio.")
    try:
        report = asyncio.run(generate(text, config["voice"], args.output_dir, args.rate or config["voice"]["rate"]))
    except ImportError:
        print("Instale requirements-production.txt antes de gerar a voz.")
        return 1
    except Exception as exc:
        print(f"A narração não foi concluída ({type(exc).__name__}). Nenhum episódio pronto foi entregue.")
        return 1
    print(f"Narração gerada: {report['duration_seconds']:.2f} s; voz {report['voice']}; {report['word_boundaries']} palavras marcadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

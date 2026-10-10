"""Assemble narrated stories from images, animation clips and real footage."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FPS, WIDTH, HEIGHT = 24, 1920, 1080
PALETTE = {"navy": "#12172D", "gold": "#D9A34B", "parchment": "#F3E6CC"}
PERSISTENT_FRAME = True


def run(command: list[str], log: Path) -> None:
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=log.parent, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"FFmpeg não concluiu a etapa; consulte {log.name}.")


def local_asset(episode: Path, name: str) -> Path:
    asset = (episode / name).resolve()
    if not asset.is_relative_to(episode.resolve()) or not asset.is_file():
        raise ValueError("Asset ausente ou fora da pasta do episódio.")
    return asset


def color(key: str) -> str:
    value = PALETTE[key]
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise ValueError("Cor da identidade inválida.")
    return "0x" + value[1:]


def to_ass_time(value: str) -> str:
    return value.replace(",", ".")[:-1]


def make_ass(srt: str) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,40,&H00CCE6F3,&H00CCE6F3,&H002D1712,&HAA2D1712,0,0,0,0,100,100,0,0,3,2,0,2,100,100,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    entries = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        lines = block.splitlines()
        if len(lines) < 3:
            raise ValueError("Legenda SRT inválida.")
        start, end = lines[1].split(" --> ")
        spoken = r"\N".join(lines[2:]).replace("{", "｛").replace("}", "｝")
        entries.append(f"Dialogue: 0,{to_ass_time(start)},{to_ass_time(end)},Default,,0,0,0,,{spoken}")
    return header + "\n".join(entries) + "\n"


def render_shot(index: int, shot: dict, episode: Path, work: Path) -> Path:
    asset = local_asset(episode, shot["asset"])
    seconds = float(shot["duration_seconds"])
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Duração de cena inválida.")
    frames = round(seconds * FPS)
    if frames < 1:
        raise ValueError("A cena precisa ter pelo menos um quadro.")
    kind = shot.get("kind", "image")
    if kind not in ("image", "video"):
        raise ValueError("Tipo de asset deve ser image ou video.")
    motion = shot.get("motion", "push_in" if kind == "image" else "none")
    if isinstance(motion, bool):
        motion = "push_in" if motion else "none"
    if motion not in ("push_in", "pull_out", "pan_left", "pan_right", "none"):
        raise ValueError("Movimento de câmera desconhecido.")
    output = work / f"clip-{index:03d}.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    scaler = "neighbor" if shot.get("pixel_art", False) else "lanczos"
    filters = []
    if kind == "video":
        command += ["-stream_loop", "-1", "-i", str(asset)]
    elif motion == "none":
        command += ["-loop", "1", "-framerate", str(FPS), "-i", str(asset)]
    else:
        command += ["-i", str(asset)]
    moving_image = kind == "image" and motion != "none"
    scale_width, scale_height = (WIDTH * 2, HEIGHT * 2) if moving_image else (WIDTH, HEIGHT)
    filters += [f"scale={scale_width}:{scale_height}:force_original_aspect_ratio=increase:flags={scaler}",
                f"crop={scale_width}:{scale_height}", "setsar=1"]
    if moving_image:
        denominator = max(frames - 1, 1)
        z, x, y = "1.06", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
        if motion == "push_in":
            z = f"1+0.04*on/{denominator}"
        elif motion == "pull_out":
            z = f"1.04-0.04*on/{denominator}"
        elif motion == "pan_left":
            x = f"(iw-iw/zoom)*(1-on/{denominator})"
        else:
            x = f"(iw-iw/zoom)*on/{denominator}"
        filters.append(f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}")
    else:
        filters += ["setpts=PTS-STARTPTS", f"fps={FPS}"]
    if PERSISTENT_FRAME:
        filters.append(f"drawbox=x=18:y=18:w=iw-36:h=ih-36:color={color('gold')}@0.82:t=3")
    for field, y, size in (("caption", 115, 58), ("label", HEIGHT - 110, 25)):
        if value := shot.get(field):
            textfile = work / f"clip-{index:03d}-{field}.txt"
            textfile.write_text(value, encoding="utf-8")
            filters.append(f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile='{textfile.name}':fontcolor={color('parchment')}:fontsize={size}:x=90:y={y}:box=1:boxcolor={color('navy')}@0.75:boxborderw=16")
    filters.append("format=yuv420p")
    command += ["-vf", ",".join(filters), "-frames:v", str(frames), "-an", "-sn",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-threads", "2",
                "-r", str(FPS), "-movflags", "+faststart", str(output)]
    run(command, work / f"clip-{index:03d}.log")
    print(f"Cena {index + 1:02d} concluída.", flush=True)
    return output


def assemble(episode: Path, work: Path, workers: int, config: dict) -> None:
    global FPS, WIDTH, HEIGHT, PALETTE, PERSISTENT_FRAME
    FPS = config["video"]["fps"]
    WIDTH, HEIGHT = config["video"]["width"], config["video"]["height"]
    PALETTE = config["branding"]["palette"]
    PERSISTENT_FRAME = config["branding"]["persistent_frame"]
    episode, work = episode.resolve(), work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    storyboard = json.loads((episode / "storyboard.json").read_text(encoding="utf-8"))
    duration = float(storyboard["duration_seconds"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Duração total inválida.")
    shots = storyboard["shots"]
    if not shots or abs(sum(round(float(s["duration_seconds"]) * FPS) for s in shots) / FPS - duration) > 1 / FPS:
        raise ValueError("As cenas não cobrem a duração declarada.")
    metadata = json.loads((episode / "metadata.json").read_text(encoding="utf-8"))
    mode = storyboard.get("subtitle_mode", config["video"].get("subtitle_mode", "none"))
    if mode not in ("none", "external", "burned_in") or metadata.get("subtitle_mode", mode) != mode:
        raise ValueError("Modo de legenda desconhecido ou incoerente entre storyboard e metadados.")
    narration = work / "narracao.mp3"
    if not narration.is_file():
        raise ValueError("Narração ausente.")
    report = json.loads((work / "narracao.json").read_text(encoding="utf-8"))
    audio_duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(narration)], text=True))
    if abs(audio_duration - report["duration_seconds"]) > 0.2 or audio_duration > duration + 0.1:
        raise ValueError("A duração real da narração difere do relatório ou ultrapassa o vídeo.")
    if duration - audio_duration > max(12, duration * 0.04):
        raise ValueError("Há silêncio excessivo após a narração; ajuste a montagem à fala.")
    subtitle_file = work / "legendas.srt"
    if mode == "burned_in" and not subtitle_file.is_file():
        raise ValueError("As legendas fixas exigem um SRT sincronizado.")
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 3))) as pool:
        clips = list(pool.map(lambda pair: render_shot(pair[0], pair[1], episode, work), enumerate(shots)))
    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{clip.name}'\n" for clip in clips), encoding="utf-8")
    silent = work / "silent.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "1", "-i", str(concat), "-c", "copy", str(silent)], work / "concat.log")
    final_tmp = episode / "video.partial.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(narration)]
    fade_start = max(0, duration - 0.7)
    video_filters = [f"fade=t=out:st={max(0, duration-1)}:d=1"]
    if mode == "burned_in":
        (work / "legendas.ass").write_text(make_ass(subtitle_file.read_text(encoding="utf-8")), encoding="utf-8")
        video_filters.insert(0, "ass=legendas.ass")
    soundtrack = storyboard.get("soundtrack")
    if soundtrack:
        bed = local_asset(episode, soundtrack)
        gain = float(storyboard.get("soundtrack_gain_db", -22))
        if not math.isfinite(gain) or not -60 <= gain <= -6:
            raise ValueError("Volume de trilha inválido.")
        command += ["-stream_loop", "-1", "-i", str(bed)]
        filters = f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=9,apad,asplit=2[voice][control];[2:a]volume={gain}dB[bed];[bed][control]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=250[ducked];[voice][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.84,afade=t=out:st={fade_start}:d=0.7[mixed]"
        command += ["-filter_complex", filters, "-map", "0:v:0", "-map", "[mixed]"]
    else:
        command += ["-af", f"loudnorm=I=-16:TP=-1.5:LRA=9,apad,afade=t=out:st={fade_start}:d=0.7", "-map", "0:v:0", "-map", "1:a:0"]
    command += ["-vf", ",".join(video_filters), "-t", str(duration), "-sn", "-map_metadata", "-1",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-threads", "2", "-r", str(FPS),
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final_tmp)]
    run(command, work / "final.log")
    final_tmp.replace(episode / "video.mp4")
    if subtitle_file.is_file():
        shutil.copyfile(subtitle_file, episode / "legendas.srt")
    shutil.copyfile(narration, episode / "narracao.mp3")
    shutil.copyfile(work / "narracao.json", episode / "narracao.json")
    metadata["subtitle_mode"] = mode
    metadata["status"] = "produced"
    (episode / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Vídeo montado: {duration:.2f} s, {len(shots)} cenas, {WIDTH} × {HEIGHT}, {FPS} fps, legenda {mode}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--config", type=Path, default=ROOT / "config/channel.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    try:
        assemble(args.episode, args.work_dir, args.workers, config)
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Montagem não concluída: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

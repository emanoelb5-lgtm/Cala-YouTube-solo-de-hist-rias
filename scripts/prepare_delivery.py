"""Prepare a complete MP4 that fits the GitHub connector upload limit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def prepare(episode: Path, work: Path, max_bytes: int) -> None:
    video = episode / "video.mp4"
    if video.stat().st_size < max_bytes:
        print("MP4 dentro do tamanho de entrega.")
        return
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(video)], text=True))
    duration = float(probe["format"]["duration"])
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    audio_bitrate = int(audio.get("bit_rate") or 128_000)
    video_bitrate = int((max_bytes * 8 / duration - audio_bitrate) * 0.94)
    if video_bitrate < 80_000:
        raise ValueError("A duração exige outro meio de entrega para preservar a qualidade visual.")
    work.mkdir(parents=True, exist_ok=True)
    source = work / "delivery-master.mp4"
    output = work / "delivery-compact.mp4"
    shutil.copyfile(video, source)
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
              "-map", "0:v:0", "-c:v", "libx264", "-b:v", str(video_bitrate),
              "-preset", "slow", "-tune", "stillimage", "-threads", "8",
              "-pix_fmt", "yuv420p", "-passlogfile", str(work / "delivery-pass")]
    with (work / "delivery.log").open("w", encoding="utf-8") as log:
        subprocess.run(common + ["-pass", "1", "-an", "-f", "null", "-"],
                       stdout=log, stderr=log, check=True)
        print("Análise de compressão concluída.", flush=True)
        subprocess.run(common + ["-pass", "2", "-map", "0:a:0",
                       "-c:a", "copy", "-sn",
                       "-movflags", "+faststart", str(output)], stdout=log, stderr=log, check=True)
    if output.stat().st_size >= max_bytes:
        raise ValueError("O MP4 ainda ultrapassa o limite de envio; o original foi preservado.")
    # Copy only after FFmpeg closes the MP4, preserving its finalized headers.
    video.write_bytes(output.read_bytes())
    print(f"MP4 preparado: {video.stat().st_size / 1024**2:.2f} MiB. Confira a qualidade antes de entregar.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, help="Limite menor para o transporte por API.")
    args = parser.parse_args()
    config = json.loads((ROOT / "config/channel.json").read_text(encoding="utf-8"))
    limit = min(config["delivery"]["max_video_file_bytes"], args.max_bytes or config["delivery"]["max_video_file_bytes"])
    prepare(args.episode.resolve(), args.work_dir.resolve(), limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

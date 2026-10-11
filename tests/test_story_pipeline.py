"""Regression checks for the adapted story workflow; no voice service required."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class DraftTests(unittest.TestCase):
    def test_existing_episode_is_preserved_and_traversal_is_rejected(self):
        new = module("new_episode")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "templates", root / "templates")
            with patch.object(new, "ROOT", root):
                episode = new.create("ep-001-carta", "A carta", "original_fiction")
                sentinel = episode / "narracao.txt"
                sentinel.write_text("Texto preservado.")
                with self.assertRaises(ValueError):
                    new.create("ep-001-carta", "Outro título", "original_fiction")
                self.assertEqual(sentinel.read_text(), "Texto preservado.")
                with self.assertRaises(ValueError):
                    new.create("../fora", "A carta", "original_fiction")

    def test_subtitle_text_cannot_inject_ass_commands(self):
        build = module("assemble_video")
        ass = build.make_ass("1\n00:00:00,000 --> 00:00:01,000\nOlá {\\pos(0,0)}\n")
        self.assertNotIn("{\\pos", ass)
        self.assertIn("Olá", ass)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg não disponível")
class AssemblyTests(unittest.TestCase):
    def test_24fps_clip_mix_without_subtitles_and_valid_zip(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow não disponível")
        build, package = module("assemble_video"), module("package_episode")
        config = json.loads((ROOT / "config/channel.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            episode, work = root / "episode", root / "work"
            assets = episode / "assets"
            assets.mkdir(parents=True)
            work.mkdir()
            Image.new("RGB", (640, 360), "#12172D").save(assets / "scene.png")
            Image.new("RGB", (1280, 720), "#12172D").save(episode / "miniatura.png")
            Image.new("RGB", (1280, 720), "#12172D").save(episode / "miniatura.jpg")
            def ffmpeg(*args):
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)
            ffmpeg("-f", "lavfi", "-i", "color=c=#725B80:s=640x360:r=30:d=1", "-an", "-c:v", "libx264", str(assets / "animation.mp4"))
            ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=3.6", str(work / "narracao.mp3"))
            ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=4", str(assets / "bed.wav"))
            # Synthetic test tone; these fields exercise the metadata contract only.
            duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(work / "narracao.mp3")], text=True))
            narration = "Arquivo de teste, sem voz produzida."
            (episode / "narracao.txt").write_text(narration)
            (work / "narracao.json").write_text(json.dumps({"engine":"edge_tts", "voice":config["voice"]["name"], "duration_seconds":duration, "text_sha256":hashlib.sha256(narration.encode()).hexdigest()}))
            (episode / "storyboard.json").write_text(json.dumps({"duration_seconds":4, "subtitle_mode":"none", "soundtrack":"assets/bed.wav", "shots":[{"asset":"assets/scene.png","kind":"image","pixel_art":True,"duration_seconds":2,"motion":"pan_left"},{"asset":"assets/animation.mp4","kind":"video","duration_seconds":2,"label":"Teste técnico"}]}))
            metadata = {"status":"produced", "channel":config["name"], "title":"Teste técnico", "summary":"Exclusivamente um teste em pasta temporária.", "story_kind":"original_fiction", "fiction_notice":"Ficção original de teste.", "subtitle_mode":"none", "tags":[], "chapters":[{"start_seconds":0,"title":"Início"}], "sources":[], "credits":"Mídias sintéticas de teste."}
            (episode / "metadata.json").write_text(json.dumps(metadata))
            build.assemble(episode, work, 1, config)
            probe = json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(episode / "video.mp4")], text=True))
            streams = probe["streams"]
            video = next(s for s in streams if s["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"], video["avg_frame_rate"]), (1920,1080,"24/1"))
            self.assertFalse(any(s["codec_type"] == "subtitle" for s in streams))
            self.assertFalse((work / "legendas.ass").exists())
            self.assertAlmostEqual(float(probe["format"]["duration"]),4,delta=0.1)
            # Extend the test fixture to exercise real chapter and delivery checks.
            ffmpeg("-stream_loop","-1","-i",str(episode / "video.mp4"),"-t","20","-c:v","libx264","-preset","ultrafast","-crf","32","-r","24","-c:a","aac",str(episode / "extended.mp4"))
            (episode / "extended.mp4").replace(episode / "video.mp4")
            (episode / "roteiro.md").write_text("Teste técnico.")
            (episode / "fontes.md").write_text("Mídias sintéticas de teste.")
            test_config = copy.deepcopy(config)
            test_config["video"].update(duration_seconds=20,duration_tolerance_seconds=1)
            report = package.package(episode,test_config)
            self.assertEqual(report["subtitle_cues"],0)
            self.assertEqual(report["embedded_subtitle_streams"],0)
            with zipfile.ZipFile(episode / "publicacao.zip") as bundle:
                self.assertIsNone(bundle.testzip())
                self.assertIn("metadata.json",bundle.namelist())
                self.assertNotIn("video.mp4",bundle.namelist())
                self.assertNotIn("legendas.srt",bundle.namelist())
            # A valid container and full audio must not hide a truncated picture.
            ffmpeg("-i",str(episode / "video.mp4"),
                   "-filter_complex","[0:v]trim=duration=4,setpts=PTS-STARTPTS[short]",
                   "-map","[short]","-map","0:a:0",
                   "-c:v","libx264","-preset","ultrafast","-c:a","copy",
                   str(episode / "truncated-picture.mp4"))
            (episode / "truncated-picture.mp4").replace(episode / "video.mp4")
            with self.assertRaisesRegex(ValueError, "faixa está incompleta"):
                package.package(episode,test_config)


if __name__ == "__main__":
    unittest.main()

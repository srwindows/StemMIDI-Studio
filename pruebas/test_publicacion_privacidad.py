import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class TestNoPrivateMedia(unittest.TestCase):
    def test_no_source_collections(self):
        for path in ("datos_entrenamiento","mio_midis","canciones","bases_roland",
                     "proyectos","grabaciones","intro"):
            self.assertFalse((ROOT/path).exists(),path)
        extensions={".mid",".midi",".kar",".wav",".flac",".sf2",".sf3",".mp3"}
        found=[str(f.relative_to(ROOT)) for f in ROOT.rglob("*")
               if f.is_file() and ".git" not in f.parts and
               "__pycache__" not in f.parts and f.suffix.lower() in extensions]
        self.assertEqual(found,[])
    def test_statistical_model(self):
        data=json.loads((ROOT/"modelos_publicos/multinstrumental_markov_v1.json").read_text())
        self.assertEqual("PUBLIC_AGGREGATED_MARKOV_V1",data["distribution"])
        self.assertEqual("symbolic_markov_multinstrumental_v1",data["type"])
        self.assertFalse(data["notes_or_lyrics_stored"])
        self.assertEqual(42,len(data["profiles"]))
        self.assertTrue(all(set(x)=={"chords","intervals","interval_unigram"}
                         for x in data["profiles"].values()))

if __name__=="__main__":
    unittest.main()

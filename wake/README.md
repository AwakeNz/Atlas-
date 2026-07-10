# `wake/` — wake-word assets

- **`atlas.onnx`** *(not committed here)* — the trained "atlas" / "hey atlas"
  openWakeWord model. Produce it with the steps in `TRAINING.md`, then place it
  here (to bundle into the build) or in `models/atlas.onnx` next to the exe
  (drop-in, no rebuild). Until it exists, A.T.L.A.S. falls back to the
  `hey_jarvis` pretrained phrase so hands-free still works.
- **`TRAINING.md`** — full reproduction of how the model is trained (synthetic
  speech, no recording of the user).

The shared feature models (`melspectrogram.onnx`, `embedding_model.onnx`) are
downloaded to `models/` on first run — they are not stored here.

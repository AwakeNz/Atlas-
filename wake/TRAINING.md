# Training the "atlas" wake word (`wake/atlas.onnx`)

A.T.L.A.S. listens for **"atlas"** / **"hey atlas"** entirely on-device using
[openWakeWord](https://github.com/dscripka/openWakeWord). This document records
how `atlas.onnx` was produced so it can be reproduced or improved. **No audio
ever leaves the machine** at runtime — detection and transcription are local.

> Ship status: if `models/atlas.onnx` is absent at launch, A.T.L.A.S. falls
> back to an openWakeWord pretrained phrase (`hey_jarvis`) so hands-free still
> works out of the box, and logs a note. Train and drop in `atlas.onnx` for the
> real "atlas" phrase.

## How it was trained (openWakeWord synthetic-speech pipeline)

openWakeWord trains on **synthetic speech** — you never record yourself. The
official Colab automates it end to end:

1. Open the **openWakeWord automatic model training** Colab
   (`notebooks/automatic_model_training.ipynb` in the openWakeWord repo).
2. Set the target phrase:
   ```python
   target_word = "atlas"           # also generate "hey atlas" as a variant
   ```
3. The notebook uses a text-to-speech model (Piper) to synthesize **thousands**
   of clips of the phrase across many voices, speeds, and accents, then mixes
   in noise/room impulse responses for robustness.
4. Negative data (speech that is *not* the phrase) is drawn from the bundled
   ACAV100M / FMA / common-speech negative sets so the model learns to reject
   everyday conversation.
5. Training produces a small classifier exported to **ONNX**:
   ```
   atlas.onnx        # ~1–2 MB, the file this app loads
   ```
6. Download `atlas.onnx` and place it in **`wake/atlas.onnx`** (bundled into the
   build) or in **`models/atlas.onnx`** next to the exe (drop-in, no rebuild).

## Runtime feature models

openWakeWord needs two shared feature extractors alongside any phrase model:

```
models/melspectrogram.onnx     # audio → mel spectrogram
models/embedding_model.onnx    # spectrogram → embedding
```

These are **downloaded automatically on first run** by `core/models.py` (from
the openWakeWord releases), with a HUD progress bar. They are not phrase-
specific and are reused by every wake model.

## Tuning

- `settings.json → wake_sensitivity` (0–1): higher = triggers more easily.
  Internally mapped to a detection threshold; start at `0.5` and adjust.
- `settings.json → wake_phrases`: display/config only — the actual phrase is
  whatever `atlas.onnx` was trained on. Retrain to change it.

## Retraining checklist

- [ ] Generate ≥ 30k positive synthetic clips (more accents = fewer false negatives).
- [ ] Include "hey atlas" and "atlas" utterances.
- [ ] Validate against a held-out negative set; aim for < 1 false accept / hour idle.
- [ ] Export ONNX, confirm it loads with `onnxruntime` CPU provider.
- [ ] Drop into `models/atlas.onnx`, set `wake_sensitivity`, test in a noisy room.

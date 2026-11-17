# speech fixtures

`start-with-the-migration.16k.wav` — 2.3 s of speech, monosyllabic nothing fancy:

> shall we start with the migration

Committed rather than generated in the test, because generating it would need a text-to-speech
engine on every machine that runs the test, and a WAV is 73 KB. It is exactly what the capture path
produces — mono `s16le` at 16 kHz — so it can be handed to a transcriber without conversion.

Provenance: synthesized once with `espeak-ng 1.52` and resampled to 16 kHz.

```sh
espeak-ng -v en-us -s 150 -w /tmp/speech22k.wav "shall we start with the migration"
# then resample to 16 kHz mono s16le with numpy.interp; see git history of this file for the snippet
```

The voice is synthetic and deliberately robotic: if a model transcribes this, a real voice is easy.
Do not regenerate it casually — `tests/e2e/test_real_whisper.py` asserts words present in this clip,
and a different clip means re-checking which words survive a 75 MB model.

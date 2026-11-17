# Security

## Threat model, five lines

1. Audio never leaves the machine unless you configure a cloud engine explicitly.
2. The default engine is local `faster-whisper`; models are downloaded, not uploaded.
3. Recordings and transcripts live in the state directory, outside any git repository.
4. Cloud engines read their key from the environment or `.env` (gitignored); no key is ever written
   into a transcript, a log, or the config file that ships in the repo.
5. `flyon` records only what the operating system gives it access to: no elevation, no capture of
   other users' audio.

## Reporting

Open a private security advisory on the repository rather than a public issue.

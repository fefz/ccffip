# Streaming run state

Each run uses an isolated `WORKDIR`. `masscan.list` is producer-owned and is read only through complete newline boundaries. The run is **partial** until `masscan.done` exists and `run.log` contains both `MASSCAN_FINISHED` and `COLO_FINISHED`.

`state.json` is atomically replaced after validated TCP and Colo artifacts are durable. `seen.txt` is the durable canonical `IP:port` set; `published/pending.txt` contains only final labelled rows. A coordinator lock prevents concurrent consumers. A missing `.done` batch is replay-safe because endpoint and publication inputs are deduplicated.

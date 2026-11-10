# Where `pipeline_states.bin.xz` comes from

**This is not a Nintendo file, and it holds no game code or game data.** It is the list of Vulkan pipelines that
Hookshot's renderer made while people played on their own PCs, written by Hookshot itself.

- **What a record is:** one pipeline the game asked for. Each record holds:
  - the hashes of its shaders and of the program variant
  - the target formats
  - the vertex formats
  - the draw state it was built with

  There are no shaders in it, only their hashes. A player's build turns those hashes back into shaders from the
  player's own `hookshot_shaders.bin`. `nx2/pipeline_states.py` documents the record layout.
- **Who writes it:** a Hookshot game run writes `hookshot_pipeline_states.bin` next to the executable and adds each
  pipeline as it is made (`gpu/vk/vk_draw.cpp`).
- **How this list was made:** game runs' lists merged with `nx2/pipeline_states.py`, each pipeline kept once.
  - **1,261 pipelines** came from the first list, added to the repository in 5d491ba and moved here, compressed, in
    6643085.
  - **3,015 more** came from a second player's play on Linux (RTX 4070 Ti, DLSS, HD texture pack Lite), merged in
    5e4e211.
  - That makes **4,276 pipelines of 2,238 programs**.
- **What it is for:** `nx2/make_game.py` unpacks it beside the game as `hookshot_pipeline_states_shipped.bin`. The first
  start's shader preparation then builds these pipelines before the title screen, so the first field load doesn't wash
  out white while they compile.

To refresh it, play on a build of the current source and merge your `hookshot_pipeline_states.bin` into this file. The
commands are in [docs/development.md, "The pipeline state list"](../docs/development.md#the-pipeline-state-list).
Note each merge here, with where its list came from.

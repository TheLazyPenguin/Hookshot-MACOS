# Temporal history validity

DLSS and FSR4 use the shared temporal chain; FSR3.1 prepares its own inputs. If camera reprojection fails, motion vectors are unavailable and the previous picture has no valid mapping to the current one. Each path must deliver a reset in that same frame rather than retaining unusable history.

Validate both input matrices and each result coefficient before converting to float. A finite double outside the float range is rejected before conversion. Preserve the existing algorithm, singularity threshold and age/size rules: valid consecutive camera motion retains history. This adds no camera-cut heuristic or interface change.

The game-free fixture compiles actual reprojection math, both preparation policies, the shared frame reset and all three consumer assignments (DLSS, FSR4, FSR3.1). It covers singular and non-finite inputs, float overflow/boundaries, recovery, frame gaps, FSR3.1 size changes and valid perspectives at16:9 and ultrawide. Engine SDKs and a GPU are not required. CPU cases do not prove in-game frequency, visual gains or GPU handling of injected invalid matrices.

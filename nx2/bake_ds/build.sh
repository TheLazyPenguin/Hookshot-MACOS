#!/bin/bash
# (bake-deepseek) Build the offline translator: Eden's recompiler + sirit + one driver. No Vulkan device.
#
#   nx2/bake_ds/build.sh                 -> $OUT/bake_ds (default ${TMPDIR:-/tmp}/hookshot-ds)
#   OUT=... EXT=... CXX=... JOBS=... nx2/bake_ds/build.sh
#
# Sources are compiled into $OUT/obj, never into the repository. Needs a C++23 compiler (the recompiler's
# constexpr ASSERT uses a static local, which GCC accepts only at -std=c++2b; the game builds with clang
# -std=c++20), and the Vulkan/SPIR-V headers plus boost/fmt (the same CPM externals the game build uses).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=${ROOT:-$(cd "$HERE/../.." && pwd)}
OUT=${OUT:-${TMPDIR:-/tmp}/hookshot-ds}
CXX=${CXX:-g++}
JOBS=${JOBS:-$(nproc)}
EXT=${EXT:-}
if [ -z "$EXT" ]; then
  for d in "$ROOT/../azahar-build/externals" "$ROOT/buildext/cpm"; do
    if [ -f "$d/spirv-headers/include/spirv/unified1/spirv.hpp" ]; then EXT=$d; break; fi
  done
fi
if [ -z "${EXT:-}" ]; then
  echo "build.sh: no externals with spirv-headers (set EXT=... to a folder with spirv-headers, vulkan-headers, boost, fmt)" >&2
  exit 2
fi
mkdir -p "$OUT/obj"
INC=(-I"$ROOT/gpu/vk/compat" -I"$ROOT/gpu/compat" -I"$ROOT/gpu/vk/eden" -I"$ROOT/gpu/third_party/suyu"
     -I"$ROOT/gpu/vk/sirit/include" -I"$ROOT/gpu/vk/sirit/src"
     -I"$EXT/spirv-headers/include" -I"$EXT/spirv-headers/include/spirv/unified1"
     -I"$EXT/vulkan-headers/include" -I"$EXT/fmt/include" -I"$EXT/boost")
FLAGS=(-std=c++2b -O1 -Wno-everything -include algorithm -include cstdio -include cstdlib -include cstring
       -include functional -include string -include vector -DNDEBUG -DVK_NO_PROTOTYPES)

mapfile -t SRCS < <(find "$ROOT/gpu/vk/eden/shader_recompiler" "$ROOT/gpu/vk/sirit/src" -name '*.cpp' | sort)
OBJS=()
fail=0
pids=()
for src in "${SRCS[@]}"; do
  rel=${src#"$ROOT"/}
  obj="$OUT/obj/${rel//\//_}"
  obj=${obj%.cpp}.o
  OBJS+=("$obj")
  if [ -f "$obj" ] && [ "$obj" -nt "$src" ]; then continue; fi
  "$CXX" "${FLAGS[@]}" "${INC[@]}" -c "$src" -o "$obj" &
  pids+=($!)
  if [ "${#pids[@]}" -ge "$JOBS" ]; then
    wait -n || fail=1
    pids=()
  fi
done
for p in "${pids[@]:-}"; do [ -n "$p" ] && { wait "$p" || fail=1; }; done
[ "$fail" = 0 ] || { echo "build.sh: a source failed" >&2; exit 1; }
"$CXX" -std=c++2b -O1 -Wno-everything -DVK_NO_PROTOTYPES "${INC[@]}" \
  "$ROOT/nx2/bake_ds/bake_ds.cpp" "${OBJS[@]}" -o "$OUT/bake_ds"
echo "built $OUT/bake_ds ($(wc -l < "$ROOT/nx2/bake_ds/bake_ds.cpp") lines, ${#SRCS[@]} recompiler sources)"

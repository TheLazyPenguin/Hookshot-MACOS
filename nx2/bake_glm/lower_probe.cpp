// (bake-glm spike) encoding probe: hand-built native Ampere instructions through LowerToMaxwell, no GPU, no game.
//   lower_probe                      (the full probe suite)
// Exit codes: 0 all lowered, 1 some failed (their words on stderr).
#include <cstdio>
#include <span>
#include <string>
#include <string_view>
#include <vector>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"

using Shader::Ampere::Instruction;

static void set(Instruction& i, unsigned w0 = 0, unsigned w1 = 0, unsigned w2 = 0, unsigned w3 = 0) {
    i = Instruction{};
    i.words[0] = w0, i.words[1] = w1, i.words[2] = w2, i.words[3] = w3;
}
static bool probe(const char* name, const std::vector<Instruction>& code) {
    const auto r = Shader::Ampere::LowerToMaxwell(code);
    if (r) {
        std::printf("ok   %s: %zu Maxwell words\n", name, r.instructions.size());
        return true;
    }
    std::fprintf(stderr, "fail %s at +%#x: %s\n", name, r.error_offset, std::string(r.error).c_str());
    return false;
}

int main() {
    bool all = true;
    {   // EXIT unconditional (T=7 at bits 12..15, predicate field 7 at bits 87..90)
        Instruction e{};
        set(e, 0x794du, 0u, 0u, 0u);
        e.words[2] = 7u << 23;      // bits 84..85 = 0 (special mode), bits 87..90 = 7 (the unconditional predicate)
        all &= probe("exit", {e});
    }
    {   // MOV R2, immediate 0x3f800000 (1.0f)
        Instruction m{};
        set(m, 0x802u | (2u << 16), 0x3f800000u, 0u, 0u);
        m.words[2] = 0x00000f00u;   // Bits(72,4) = 15, Bits(76,16) = 0
        Instruction e{};
        set(e, 0x794du, 0, 0, 0);
        e.words[2] = 7u << 23;
        all &= probe("mov-imm", {m, e});
    }
    if (all) std::printf("probe: every case lowered\n");
    return all ? 0 : 1;
}

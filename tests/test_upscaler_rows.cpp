#include "../gpu/vk/upscaler_rows.h"

#include <cstdio>
#include <cstring>
#include <initializer_list>

#define CHECK(name, condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s at line %d\n", name, __LINE__); return 1; } } while (0)

int main() {
    namespace ur = mkwvk::upscaler_rows;
    using ur::DLAA;
    using ur::DLSS;
    using ur::GAME;
    // (the values saved before keep their shares; the new ones are DLSS's ratios, each a twelfth of the output)
    CHECK("saved values keep their shares", ur::percent(0) == 0 && ur::percent(1) == 100 && ur::percent(2) == 75 &&
                                                ur::percent(3) == 67 && ur::percent(4) == 50);
    CHECK("Balanced and Ultra Performance", ur::percent(5) == 58 && ur::percent(6) == 33);
    CHECK("a value past the row is Auto", ur::percent(7) == 0 && ur::percent(-1) == 0);
    for (int v = 1; v < ur::kValues; v++) {
        const int k = (int)(ur::percent(v) * 12 / 100.0 + 0.5);
        CHECK("each share is a twelfth", k * 100 / 12 == ur::percent(v) || (k * 100 + 11) / 12 == ur::percent(v));
    }
    CHECK("DLSS's mode names", !std::strcmp(ur::dlss_mode_name(3), "Quality") && !std::strcmp(ur::dlss_mode_name(5), "Balanced") &&
                                   !std::strcmp(ur::dlss_mode_name(4), "Performance") &&
                                   !std::strcmp(ur::dlss_mode_name(6), "Ultra Performance"));
    CHECK("no mode name for Auto, 100% or 75%", !ur::dlss_mode_name(0) && !ur::dlss_mode_name(1) && !ur::dlss_mode_name(2));

    // the game's own: Auto, 100, 75, 67, 50, as before
    CHECK("game: Right", ur::step(GAME, 0, 1) == 1 && ur::step(GAME, 1, 1) == 2 && ur::step(GAME, 3, 1) == 4 && ur::step(GAME, 4, 1) == 0);
    CHECK("game: Left", ur::step(GAME, 0, -1) == 4 && ur::step(GAME, 1, -1) == 0 && ur::step(GAME, 4, -1) == 3);
    // DLSS: Auto, Quality 67, Balanced 58, Performance 50, Ultra Performance 33
    CHECK("dlss: Right", ur::step(DLSS, 0, 1) == 3 && ur::step(DLSS, 3, 1) == 5 && ur::step(DLSS, 5, 1) == 4 &&
                             ur::step(DLSS, 4, 1) == 6 && ur::step(DLSS, 6, 1) == 0);
    CHECK("dlss: Left", ur::step(DLSS, 0, -1) == 6 && ur::step(DLSS, 3, -1) == 0 && ur::step(DLSS, 6, -1) == 4);
    // a value that is not a step (saved with the other upscaler): its neighbours by size
    CHECK("dlss from 75%", ur::step(DLSS, 2, 1) == 3 && ur::step(DLSS, 2, -1) == 0);
    CHECK("dlss from 100%", ur::step(DLSS, 1, 1) == 3 && ur::step(DLSS, 1, -1) == 0);
    CHECK("game from 58%", ur::step(GAME, 5, 1) == 4 && ur::step(GAME, 5, -1) == 3);
    CHECK("game from 33%", ur::step(GAME, 6, 1) == 0 && ur::step(GAME, 6, -1) == 4);
    CHECK("DLAA does not step", ur::step(DLAA, 3, 1) == 3 && ur::step(DLAA, 0, -1) == 0);

    // another upscaler: the nearest step (the larger on a tie), Auto stays Auto
    CHECK("snap to DLSS", ur::snap(DLSS, 0) == 0 && ur::snap(DLSS, 1) == 3 && ur::snap(DLSS, 2) == 3 && ur::snap(DLSS, 3) == 3 &&
                              ur::snap(DLSS, 4) == 4);
    CHECK("snap to the game's", ur::snap(GAME, 5) == 4 && ur::snap(GAME, 6) == 4 && ur::snap(GAME, 3) == 3 && ur::snap(GAME, 1) == 1);
    CHECK("DLAA keeps the value", ur::snap(DLAA, 5) == 5 && ur::snap(DLAA, 1) == 1);
    CHECK("a value past the row snaps to Auto", ur::snap(GAME, 9) == 0 && ur::snap(DLSS, -3) == 0);

    // the Upscaler row: all three where DLSS runs, the game's own alone elsewhere
    CHECK("upscaler with DLSS", ur::step_upscaler(0, 1, true) == 1 && ur::step_upscaler(1, 1, true) == 2 &&
                                    ur::step_upscaler(2, 1, true) == 0 && ur::step_upscaler(0, -1, true) == 2);
    CHECK("upscaler without DLSS", ur::step_upscaler(0, 1, false) == 0 && ur::step_upscaler(2, -1, false) == 0);
    CHECK("upscaler from a bad value", ur::step_upscaler(7, 1, true) == 1);

    // the Upscaler row only where more than the game's own runs; the rows with nothing to choose
    CHECK("upscaler row hidden with the game's own alone", !ur::upscaler_shown(ur::bit(GAME)) && !ur::upscaler_shown(0u) &&
                                                             ur::upscaler_shown(ur::bit(GAME) | ur::dlss_bits(true)) &&
                                                             !ur::upscaler_shown(ur::bit(GAME) | ur::dlss_bits(false)));
    // AMD FSR 3.1 on the same row, after DLAA: stepping visits only what runs here, and wraps
    {
        const unsigned all = ur::bit(GAME) | ur::dlss_bits(true) | ur::bit(ur::FSR3);
        const unsigned fsr3 = ur::bit(GAME) | ur::bit(ur::FSR3);
        CHECK("FSR 3.1 after DLAA", ur::FSR3 == 3);
        CHECK("upscaler steps through all four", ur::step_upscaler(DLAA, 1, all) == ur::FSR3 &&
                                                   ur::step_upscaler(ur::FSR3, 1, all) == GAME &&
                                                   ur::step_upscaler(GAME, -1, all) == ur::FSR3 &&
                                                   ur::step_upscaler(ur::FSR3, -1, all) == DLAA);
        CHECK("upscaler without DLSS skips it", ur::step_upscaler(GAME, 1, fsr3) == ur::FSR3 &&
                                                  ur::step_upscaler(ur::FSR3, 1, fsr3) == GAME &&
                                                  ur::step_upscaler(GAME, -1, fsr3) == ur::FSR3);
        CHECK("an upscaler that cannot run here steps as the game's own", ur::step_upscaler(DLSS, 1, fsr3) == ur::FSR3 &&
                                                                            ur::step_upscaler(ur::FSR3, 1, ur::bit(GAME)) == GAME);
        CHECK("the DLSS-only form is the mask's", ur::step_upscaler(DLAA, 1, true) == GAME && ur::step_upscaler(GAME, -1, true) == DLAA);
        CHECK("upscaler fixed only with nothing but the game's own",
              ur::upscaler_fixed(ur::bit(GAME)) && !ur::upscaler_fixed(fsr3) && !ur::upscaler_fixed(all));
        CHECK("upscaler row shown with FSR 3.1 alone", ur::upscaler_shown(fsr3) && ur::upscaler_shown(all) &&
                                                          ur::upscaler_shown(ur::bit(GAME) | ur::fsr4_bits(true)));
        CHECK("FSR 3.1's modes are DLSS's shares", ur::scales_by_mode(ur::FSR3) && ur::scales_by_mode(DLSS) &&
                                                     !ur::scales_by_mode(DLAA) && !ur::scales_by_mode(GAME));
        CHECK("FSR 3.1 steps as DLSS does", ur::step(ur::FSR3, 0, 1) == 3 && ur::step(ur::FSR3, 3, 1) == 5 &&
                                              ur::step(ur::FSR3, 6, 1) == 0 && ur::snap(ur::FSR3, 2) == 3);
        CHECK("the model row waits with FSR 3.1", ur::model_fixed(ur::FSR3, false) && !ur::model_fixed(DLSS, false) &&
                                                    !ur::model_fixed(DLAA, false));
        CHECK("FSR 3.1 has a Render resolution", !ur::resolution_fixed(ur::FSR3));
    }
    // AMD FSR 4 and its native AA after FSR 3.1 (saved values keep their meaning), on the same row and mask
    {
        using ur::FSR3;
        using ur::FSR4;
        using ur::FSR4_AA;
        const unsigned every = ur::bit(GAME) | ur::dlss_bits(true) | ur::bit(FSR3) | ur::fsr4_bits(true);
        const unsigned fsr4 = ur::bit(GAME) | ur::fsr4_bits(true);
        CHECK("FSR 4 after FSR 3.1", FSR4 == 4 && FSR4_AA == 5 && ur::kUpscalers == 6);
        CHECK("upscaler steps through all six", ur::step_upscaler(FSR3, 1, every) == FSR4 &&
                                                  ur::step_upscaler(FSR4, 1, every) == FSR4_AA &&
                                                  ur::step_upscaler(FSR4_AA, 1, every) == GAME &&
                                                  ur::step_upscaler(GAME, -1, every) == FSR4_AA &&
                                                  ur::step_upscaler(FSR4, -1, every) == FSR3);
        CHECK("upscaler with FSR 4 alone", ur::step_upscaler(GAME, 1, fsr4) == FSR4 && ur::step_upscaler(FSR4_AA, 1, fsr4) == GAME &&
                                               ur::step_upscaler(GAME, -1, fsr4) == FSR4_AA && !ur::upscaler_fixed(fsr4));
        CHECK("a saved FSR 4 where it cannot run steps as the game's own",
              ur::step_upscaler(FSR4, 1, ur::bit(GAME) | ur::dlss_bits(true)) == DLSS &&
              ur::step_upscaler(FSR4_AA, -1, ur::bit(GAME) | ur::bit(FSR3)) == FSR3);
        CHECK("engines", ur::is_dlss(DLSS) && ur::is_dlss(DLAA) && !ur::is_dlss(FSR3) && !ur::is_dlss(FSR4) &&
                             ur::is_fsr4(FSR4) && ur::is_fsr4(FSR4_AA) && !ur::is_fsr4(FSR3) && !ur::is_fsr4(DLAA) &&
                             !ur::is_fsr4(GAME));
        CHECK("full scale", ur::full_scale(DLAA) && ur::full_scale(FSR4_AA) && !ur::full_scale(FSR3) && !ur::full_scale(FSR4) &&
                                !ur::full_scale(DLSS) && !ur::full_scale(GAME));
        CHECK("FSR 4's modes are DLSS's shares", ur::scales_by_mode(FSR4) && !ur::scales_by_mode(FSR4_AA));
        for (int v = 0; v < ur::kValues; v++)
            for (int dir : {1, -1})
                CHECK("FSR 4 steps as DLSS", ur::step(FSR4, v, dir) == ur::step(DLSS, v, dir) && ur::snap(FSR4, v) == ur::snap(DLSS, v));
        CHECK("FSR 4's native AA does not step", ur::step(FSR4_AA, 3, 1) == 3 && ur::snap(FSR4_AA, 5) == 5);
        CHECK("the model row waits with FSR 4", ur::model_fixed(FSR4, false) && ur::model_fixed(FSR4_AA, false));
    }
    CHECK("upscaler fixed where DLSS cannot run", ur::upscaler_fixed(false) && !ur::upscaler_fixed(true));
    CHECK("render resolution fixed at full scale only", ur::resolution_fixed(DLAA) && ur::resolution_fixed(ur::FSR4_AA) &&
                                                             !ur::resolution_fixed(DLSS) && !ur::resolution_fixed(ur::FSR4) &&
                                                             !ur::resolution_fixed(GAME));
    // the Window scaling filter: needed only when the window is not the picture's size (unknown: needed)
    CHECK("filter not needed at the output's size", !ur::filter_needed(2560, 1440, 2560, 1440));
    CHECK("filter needed otherwise", ur::filter_needed(2048, 1152, 2560, 1440) && ur::filter_needed(2560, 1440, 2560, 1080) &&
                                         ur::filter_needed(0, 0, 0, 0) && ur::filter_needed(2560, 1440, 0, 0));
    // the DLSS model row: its presets (NVIDIA's numbers, K = 11), RX_VK_DLSS_PRESET over it, and when it applies
    CHECK("model presets", ur::model_preset(ur::MODEL_K) == 11 && ur::model_preset(ur::MODEL_M) == 13 &&
                               ur::model_preset(ur::MODEL_L) == 12 && ur::model_preset(ur::MODEL_DEFAULT) == 0);
    CHECK("model: a value past the row is K", ur::model_preset(-1) == 11 && ur::model_preset(ur::kModels) == 11);
    CHECK("model without the switch", ur::dlss_preset(ur::MODEL_M, nullptr) == 13 && ur::dlss_preset(ur::MODEL_DEFAULT, nullptr) == 0);
    CHECK("RX_VK_DLSS_PRESET wins", ur::dlss_preset(ur::MODEL_M, "K") == 11 && ur::dlss_preset(ur::MODEL_K, "m") == 13 &&
                                        ur::dlss_preset(ur::MODEL_K, "J") == 10 && ur::dlss_preset(ur::MODEL_M, "0") == 0);
    CHECK("RX_VK_DLSS_PRESET not a preset", !ur::preset_env(nullptr) && !ur::preset_env("") && !ur::preset_env("1") &&
                                                !ur::preset_env("05") && ur::dlss_preset(ur::MODEL_M, "7") == 13 &&
                                                ur::dlss_preset(ur::MODEL_L, "") == 12);
    CHECK("preset letters", ur::preset_letter(11) == 'K' && ur::preset_letter(13) == 'M' && ur::preset_letter(0) == '0');
    CHECK("model row shown only where DLSS runs", ur::model_shown(true) && !ur::model_shown(false));
    CHECK("model row fixed with the game's own or the switch", ur::model_fixed(GAME, false) && !ur::model_fixed(DLSS, false) &&
                                                               !ur::model_fixed(DLAA, false) && ur::model_fixed(DLSS, true));
    std::puts("upscaler rows: all checks passed");
}

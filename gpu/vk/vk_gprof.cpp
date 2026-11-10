// GPU profile (vk_gprof.h): a query pool of timestamps per recording slot and command buffer (the recording's, and its upload one).
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <unordered_map>
#include <vector>

#include "vk_gprof.h"
#include "vk_work.h"   // (after the others: its timestamps go through RX_VK_RECORDER with the commands around them)

namespace mkwvk {
namespace {

constexpr int kSlots = 48;                // (vk_replay.cpp's kRecordings)
constexpr uint32_t kQ = 2048;             // timestamps a command buffer can take in a recording
VkQueryPool pool = VK_NULL_HANDLE;
struct Span {
    std::string label;
    uint32_t qb = 0, qe = 0;              // (its timestamps: a run of a pass shares them with its neighbours)
    int items = 1;
    uint64_t bytes = 0;
    bool nested = false;                  // (a program's run inside a pass: counted by itself, not in the command buffer's total)
};
struct Stream {
    VkCommandBuffer cmd = VK_NULL_HANDLE;
    uint32_t base = 0;                    // (its first query)
    std::vector<Span> spans;
    uint32_t nq = 0;                      // (timestamps taken)
    uint32_t dirty = kQ;                  // (queries that may hold a result: the next use resets them; all of them before the first)
    int outer = -1;                       // (the open span)
    int run = -1;                         // (the open program run of the open pass, RX_VK_PASS_TIMING=2)
    uint64_t run_key = 0;
};
struct Slot {
    Stream s[2];                          // (0: the recording's command buffer, 1: its upload command buffer)
    bool used = false, up_sent = false;
};
Slot slots[kSlots];
int cur = -1;
struct Agg {
    double ns = 0;
    int64_t n = 0, items = 0;
    uint64_t bytes = 0;
};
std::unordered_map<std::string, Agg> totals[2];   // label -> what its spans took, per command buffer kind
double active_ns[2], sum_ns[2];                   // (the command buffers' first timestamp to last, and what their spans took)
int64_t recs[2], dropped;
int acc_frames = 0;

Stream* find(VkCommandBuffer cmd) {
    if (!pool || cur < 0 || !cmd) return nullptr;
    for (Stream& s : slots[cur].s)
        if (s.cmd == cmd) return &s;
    return nullptr;
}
uint32_t stamp(Stream& st, VkCommandBuffer cmd) {
    vkCmdWriteTimestamp2(cmd, VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT, pool, st.base + st.nq);
    return st.nq++;
}

} // namespace

bool gprof_on() {
    static const bool on = [] {
        const char* a = getenv("RX_VK_PASS_TIMING");
        const char* b = getenv("RX_VK_GPU_PROFILE");
        return (a && atoi(a) != 0) || (b && atoi(b) != 0);
    }();
    return on;
}
static int level() {
    static const int v = [] {
        const char* a = getenv("RX_VK_PASS_TIMING");
        return a ? atoi(a) : 1;
    }();
    return v;
}

void gprof_begin_recording(int slot, VkCommandBuffer cmd, VkCommandBuffer upload) {
    if (!gprof_on() || slot < 0 || slot >= kSlots) return;
    if (!pool) {
        VkQueryPoolCreateInfo qi{VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO};
        qi.queryType = VK_QUERY_TYPE_TIMESTAMP;
        qi.queryCount = kSlots * 2 * kQ;
        if (vkCreateQueryPool(dev.device, &qi, nullptr, &pool) != VK_SUCCESS) return;
        logf("vk: GPU pass timing on (RX_VK_PASS_TIMING=%d): every 600 presents the spans of GPU work are logged", level());
    }
    cur = slot;
    Slot& s = slots[slot];
    s.used = true, s.up_sent = false;
    for (int k = 0; k < 2; k++) {
        Stream& st = s.s[k];
        st.cmd = k ? upload : cmd;
        st.base = (uint32_t)(slot * 2 + k) * kQ;
        st.spans.clear();
        st.outer = st.run = -1;
        if (st.dirty) vkCmdResetQueryPool(st.cmd, pool, st.base, st.dirty);   // (an upload command buffer that is not sent resets nothing: its dirty stands)
        st.nq = 0;
    }
}

void gprof_submitted(int slot, bool upload_sent) {
    if (!pool || slot < 0 || slot >= kSlots) return;
    slots[slot].up_sent = upload_sent;
}

bool gprof_begin(VkCommandBuffer cmd) {
    Stream* st = find(cmd);
    if (!st || st->outer >= 0 || st->nq + 4 > kQ) {
        if (st && st->outer < 0) dropped++;
        return false;
    }
    Span sp;
    sp.qb = stamp(*st, cmd);
    st->spans.push_back(std::move(sp));
    st->outer = (int)st->spans.size() - 1;
    return true;
}

void gprof_end(VkCommandBuffer cmd, const std::string& label, int items, uint64_t bytes) {
    Stream* st = find(cmd);
    if (!st || st->outer < 0) return;
    const uint32_t q = stamp(*st, cmd);
    if (st->run >= 0) st->spans[st->run].qe = q, st->run = -1;   // (the pass's last run ends with it)
    Span& sp = st->spans[st->outer];
    sp.qe = q, sp.label = label, sp.items = items, sp.bytes = bytes;
    st->outer = -1;
}

void gprof_run(VkCommandBuffer cmd, uint64_t key) {
    if (level() < 2) return;
    Stream* st = find(cmd);
    if (!st || st->outer < 0) return;
    if (st->run >= 0 && st->run_key == key) {
        st->spans[st->run].items++;
        return;
    }
    if (st->nq + 3 > kQ) return;
    const uint32_t q = stamp(*st, cmd);
    if (st->run >= 0) st->spans[st->run].qe = q;
    Span sp;
    char l[32];
    snprintf(l, sizeof l, "prog %016llx", (unsigned long long)key);
    sp.label = l, sp.qb = q, sp.nested = true;
    st->spans.push_back(std::move(sp));
    st->run = (int)st->spans.size() - 1, st->run_key = key;
}

void gprof_collect(int slot) {
    if (!pool || slot < 0 || slot >= kSlots) return;
    Slot& s = slots[slot];
    if (!s.used) return;
    s.used = false;
    const double period = dev.props.limits.timestampPeriod;
    for (int k = 0; k < 2; k++) {
        Stream& st = s.s[k];
        if (k == 0 || s.up_sent) st.dirty = st.nq;   // (the next use resets what this one wrote)
        if (st.spans.empty() || st.nq == 0 || (k && !s.up_sent)) {
            st.spans.clear();
            continue;
        }
        std::vector<uint64_t> t(st.nq);
        if (vkGetQueryPoolResults(dev.device, pool, st.base, st.nq, t.size() * 8, t.data(), 8, VK_QUERY_RESULT_64_BIT) != VK_SUCCESS) {
            st.spans.clear();
            continue;
        }
        uint64_t first = UINT64_MAX, last = 0;
        double sum = 0;
        for (const Span& sp : st.spans) {
            if (sp.label.empty() || sp.qb >= st.nq || sp.qe >= st.nq || t[sp.qe] <= t[sp.qb]) continue;
            const double ns = (double)(t[sp.qe] - t[sp.qb]) * period;
            Agg& a = totals[k][sp.label];
            a.ns += ns, a.n++, a.items += sp.items, a.bytes += sp.bytes;
            if (sp.nested) continue;
            sum += ns;
            first = std::min(first, t[sp.qb]), last = std::max(last, t[sp.qe]);
        }
        if (last > first) {
            active_ns[k] += (double)(last - first) * period;
            sum_ns[k] += sum;
            recs[k]++;
        }
        st.spans.clear();
    }
}

void gprof_report(int frames) {
    if (!pool) return;
    acc_frames += frames;
    if (acc_frames < 600) return;
    const double f = acc_frames, mb = 1048576.0;
    logf("vk: GPU pass timing, %d presents, per frame (each timestamp waits for the GPU to finish what came before it: spans add up to "
         "more than an unprofiled frame; read the shares):", acc_frames);
    logf("vk:   %.2f ms a frame in all (recordings' command buffers + upload command buffers; the present's blit to the window is not timed; "
         "the 'GPU time' line of an unprofiled run counts the first kind only)", (active_ns[0] + active_ns[1]) / f / 1e6);
    logf("vk:   recordings' command buffers: %.2f ms from the first timestamp to the last in %.1f a frame (%.2f ms in spans, %.2f ms "
         "between them: glue the spans do not name)", active_ns[0] / f / 1e6, recs[0] / f, sum_ns[0] / f / 1e6,
         (active_ns[0] - sum_ns[0]) / f / 1e6);
    logf("vk:   upload command buffers: %.2f ms in %.1f a frame (%.2f ms in spans, %.2f ms between them: texture uploads and "
         "decodes, the page table, glue)", active_ns[1] / f / 1e6, recs[1] / f, sum_ns[1] / f / 1e6,
         (active_ns[1] - sum_ns[1]) / f / 1e6);
    if (dropped) logf("vk:   %lld spans not timed (a command buffer's timestamps ran out)", (long long)dropped);
    struct Row {
        std::string name;
        int k;
        Agg a;
    };
    std::vector<Row> rows, cats, progs;
    std::map<std::string, Agg> by_cat[2];
    for (int k = 0; k < 2; k++)
        for (const auto& [label, a] : totals[k]) {
            if (label.compare(0, 5, "prog ") == 0) {
                progs.push_back({label, k, a});
                continue;
            }
            rows.push_back({label, k, a});
            Agg& c = by_cat[k][label.substr(0, label.find(' '))];
            c.ns += a.ns, c.n += a.n, c.items += a.items, c.bytes += a.bytes;
        }
    for (int k = 0; k < 2; k++)
        for (const auto& [name, a] : by_cat[k]) cats.push_back({name, k, a});
    const auto by_ns = [](const Row& a, const Row& b) { return a.a.ns > b.a.ns; };
    std::sort(cats.begin(), cats.end(), by_ns);
    std::sort(rows.begin(), rows.end(), by_ns);
    std::sort(progs.begin(), progs.end(), by_ns);
    logf("vk:   by kind (cb: m = recordings' command buffers, u = upload ones; items: draws of a pass, copies of a copy batch):");
    for (const Row& c : cats)
        logf("vk:     %c %-9s %7.3f ms %5.1f%%  %7.1f spans  %8.1f items  %7.2f MB  %7.1f us a span", c.k ? 'u' : 'm', c.name.c_str(),
             c.a.ns / f / 1e6, 100.0 * c.a.ns / std::max(active_ns[c.k], 1.0), c.a.n / f, c.a.items / f, c.a.bytes / f / mb,
             c.a.ns / std::max<int64_t>(c.a.n, 1) / 1e3);
    logf("vk:   the 25 spans that took the most (ms a frame, spans a frame, us a span, items a frame, MB a frame):");
    for (size_t i = 0; i < rows.size() && i < 25; i++) {
        const Row& r = rows[i];
        logf("vk:   %c %7.3f ms  %6.1f x  %7.1f us  %8.1f items  %6.2f MB  %s", r.k ? 'u' : 'm', r.a.ns / f / 1e6, r.a.n / f,
             r.a.ns / std::max<int64_t>(r.a.n, 1) / 1e3, r.a.items / f, r.a.bytes / f / mb, r.name.c_str());
    }
    if (!progs.empty()) {
        logf("vk:   the 20 programs whose runs of draws took the most (RX_VK_PASS_TIMING=2: a timestamp at each change of program):");
        for (size_t i = 0; i < progs.size() && i < 20; i++) {
            const Row& r = progs[i];
            logf("vk:   %7.3f ms  %6.1f runs  %7.1f us a run  %8.1f draws  %6.2f us a draw  %s", r.a.ns / f / 1e6, r.a.n / f,
                 r.a.ns / std::max<int64_t>(r.a.n, 1) / 1e3, r.a.items / f, r.a.ns / std::max<int64_t>(r.a.items, 1) / 1e3,
                 r.name.c_str());
        }
    }
    for (auto& t : totals) t.clear();
    active_ns[0] = active_ns[1] = sum_ns[0] = sum_ns[1] = 0;
    recs[0] = recs[1] = dropped = 0;
    acc_frames = 0;
}

} // namespace mkwvk

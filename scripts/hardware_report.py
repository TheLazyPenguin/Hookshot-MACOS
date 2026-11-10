"""Who reports problems: the GPU vendor, card class and OS named in the issue forms (docs/workflow.md, "Reach").

    python -I scripts/hardware_report.py [--limit 1000] [--state all|open|closed]

Reads the issues with the gh CLI (logged in) and counts the "Graphics card and driver version" and "CPU, RAM and operating
system" answers. It counts reports, not players: hardware where things break shows up more. Standard library only.
"""
import argparse
import collections
import json
import re
import subprocess
import sys

REPO = "NotRexed/Hookshot"


def section(body: str, name: str) -> str:
    m = re.search(r"### " + re.escape(name) + r"[^\n]*\n+(.*?)(\n### |\Z)", body or "", re.S)
    return m.group(1).strip() if m else ""


def classify(gpu: str):
    g = gpu.lower()
    if re.search(r"nvidia|rtx|gtx|geforce", g):
        cls = ("RTX 50" if re.search(r"rtx ?50\d0", g) else "RTX 40" if re.search(r"rtx ?40\d0", g) else
               "RTX 30" if re.search(r"rtx ?30\d0", g) else "RTX 20" if re.search(r"rtx ?20\d0", g) else
               "GTX 10/16 (no mesh shaders)" if re.search(r"gtx ?1[06]\d0", g) else "NVIDIA other")
        return "NVIDIA", cls
    if re.search(r"amd|radeon|\brx ?\d|rdna|780m|680m|890m|860m|8060s|z1|steam deck|legion|ally", g):
        cls = ("AMD APU / handheld" if re.search(r"780m|680m|890m|860m|8060s|z1|steam deck|legion|ally|apu|vega", g) else
               "RX 9000" if re.search(r"9070|9060", g) else "RX 7000" if re.search(r"7900|7800|7700|7600", g) else
               "RX 6000" if re.search(r"6[5-9]\d0|6600|6650|6700|6800|6900", g) else
               "RX 5000 or older (no mesh shaders)" if re.search(r"5[5-7]00|rx ?5[78]0|rx ?4[78]0", g) else "AMD other")
        return "AMD", cls
    if re.search(r"intel|arc\b|iris|uhd", g):
        return "Intel", "Intel"
    return "unknown", "unknown"


def os_of(text: str) -> str:
    t = text.lower()
    if re.search(r"linux|ubuntu|arch|fedora|steamos|bazzite|cachy|nixos|mint|pop!?_os|steam deck", t):
        return "Linux / SteamOS"
    if re.search(r"windows|win ?1[01]", t):
        return "Windows"
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--state", default="all", choices=("all", "open", "closed"))
    a = ap.parse_args()
    out = subprocess.run(["gh", "issue", "list", "-R", REPO, "--state", a.state, "--limit", str(a.limit),
                          "--json", "number,title,body"], capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        print(out.stderr.strip() or "gh failed", file=sys.stderr)
        return 1
    issues = json.loads(out.stdout)
    vendor, cls, oses = collections.Counter(), collections.Counter(), collections.Counter()
    n = 0
    for i in issues:
        gpu = section(i["body"], "Graphics card")
        sysinfo = section(i["body"], "CPU, RAM and operating system")
        if not gpu and not sysinfo:
            continue
        n += 1
        v, c = classify(gpu + " " + i["title"])
        vendor[v] += 1
        cls[c] += 1
        oses[os_of(sysinfo + " " + gpu + " " + i["title"])] += 1
    print(f"{len(issues)} issues read, {n} with hardware fields")
    for title, counter in (("vendor", vendor), ("card class", cls), ("OS", oses)):
        print(f"\n{title}:")
        for k, v in counter.most_common():
            print(f"  {k:36s} {v:5d}  {100 * v / max(n, 1):5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())

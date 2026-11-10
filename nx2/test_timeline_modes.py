"""Exercise the actual fence allocators across ordered, dump/legacy and queued paths; no GPU/game.

python nx2/test_timeline_modes.py [--cxx clang++]
"""
import argparse
from pathlib import Path
import subprocess,tempfile

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT=Path(__file__).resolve().parents[1]
def block(text,marker):
    start=text.index(marker);end=text.index('{',start)+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',default='clang++');a=p.parse_args()
    s=(ROOT/'gpu/vk/vk_replay.cpp').read_text(encoding='utf-8')
    direct=block(s,'void do_submit(')
    start=s.index('        const uint64_t value = ',s.index('void do_present('));end=s.index('\n',s.index('        present_value = 0;',start))
    present=s[start:end]
    source_submit=block(s,'void submit_q(');source_present=block(s,'void present(')
    # (8c28ed7 takes the value first, for the queue it belongs to, then submits it: both lines, as the source has them)
    ordered_submit='\n'.join(next(l for l in source_submit.splitlines() if text in l)
                             for text in ('const uint64_t value = ++q_values;','submit_job(h, value, queue);'))
    ordered_present=next(l for l in source_present.splitlines() if 'present_value = ++q_values;' in l)
    enqueue=next(l for l in block(s,'void enqueue(').splitlines() if 'j.value = ++q_values;' in l)
    fixture=r'''#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#define CHECK(x) do{if(!(x)){std::fprintf(stderr,"FAIL:%d %s\n",__LINE__,#x);std::exit(1);}}while(0)
std::atomic<uint64_t> pushed{0},q_values{0};uint64_t present_value=0,last=0;unsigned allocations=0;
void signal(uint64_t v){CHECK(v>last);last=v;pushed=v;allocations++;}
bool run_submit(const uint64_t*,int,uint64_t value,uint64_t,bool){signal(value);return true;}
void submit_job(std::vector<uint64_t>&,uint64_t value,uint64_t){signal(value);}
''' +direct+r'''
void direct_present(){
''' +present+r'''
    signal(value);
}
void ordered_submit(){std::vector<uint64_t>h;uint64_t queue=0;
''' +ordered_submit+r'''
}
void ordered_present(){
''' +ordered_present+r'''
    const auto reserved=q_values.load();direct_present();CHECK(q_values.load()==reserved);
}
enum Kind{JOB_SUBMIT,JOB_PRESENT};struct Job{Kind kind;uint64_t value=0;};
void queued(Kind kind){Job j{kind};
''' +enqueue+r'''
    if(kind==JOB_PRESENT){present_value=j.value;const auto reserved=q_values.load();direct_present();CHECK(q_values.load()==reserved);}
    else signal(j.value);
}
int main(){
    // Normal replay -> frame dump (legacy replay) -> normal replay, repeated.
    for(unsigned frame=0;frame<100;frame++){
        ordered_submit();ordered_present();do_submit(nullptr,0);direct_present();ordered_submit();ordered_present();
    }
    CHECK(last==600 && q_values==600 && allocations==600);
    // Non-dump legacy-only setting; queued paths retain their preassigned values.
    for(unsigned i=0;i<100;i++){do_submit(nullptr,0);direct_present();queued(JOB_SUBMIT);queued(JOB_PRESENT);}
    CHECK(last==1000 && q_values==1000 && allocations==1000);
    // Allocated ordered work can be ahead of the last GPU submission.
    q_values=1100;do_submit(nullptr,0);CHECK(last==1101 && q_values==1101);
    puts("PASS: 100 dump transitions, legacy/queued paths, no present double-allocation, reserved work ahead of pushed");
}
'''
    work=ROOT/'work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='timeline-modes-',dir=work) as temp:
        d=Path(temp).resolve();d.relative_to(work.resolve());cpp=d/'fixture.cpp';exe=d/'fixture.exe';cpp.write_text(fixture,encoding='utf-8')
        subprocess.run([a.cxx,'-std=c++20','-O2',str(cpp),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
    # Both synchronous branches must retain ordering while allocating/recording, including dump mode.
    for body in (source_submit,source_present):
        branch=body[body.index('    if (!async_on()) {'):]
        assert branch.index('sync_order_mu')<branch.index('if (sync_waits_on())')
if __name__=='__main__':main()

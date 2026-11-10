/* (hookshot) setjmp / longjmp in lifted code.

   The guest's __setjmp and longjmp (sdk+0xaec40 / +0xaed50, musl's with pointer-auth hashes) run as lifted code and
   save and restore the guest registers themselves. What lifting breaks is longjmp's last instruction, BR x30 to the
   setjmp call's return address: in lifted code that address is the middle of a C function, not an entry, so the
   indirect jump trapped (OoT's UpdateTextBoxTextureThread, at 0x81681690). And the function that called setjmp may
   have returned by then: 0x81681670 is a wrapper that returns setjmp's result, which works on the console because
   its stack frame is still intact when longjmp comes back to it.

   So the lifter (a64_lift.py find_setjmp_owners) makes each setjmp return address an entry, and wraps every call of
   a function that calls setjmp (its "owner") as

       { void **sj = recomp_sj_push(c, r0..r3); if (recomp_sj_setjmp(sj) == 0) f_owner(c);
         else a64_icall(c, recomp_sj_target(sj)); recomp_sj_pop(sj); }

   in the caller's own frame, which is alive while the owner runs and after it returns. A jump that misses
   (a64_call_miss) to one of a pushed slot's return addresses is a longjmp: the guest registers are restored already
   (x0 the value, SP and x30 as setjmp saw them), so the newest such slot is taken (slots above it dropped), and
   recomp_sj_longjmp brings the host back to that caller, which runs the owner's code from the return address: what
   the owner would have done, ending in its own return to the caller.

   (recomp_sj_setjmp / recomp_sj_longjmp are this file's own, in assembly: every Win64 callee-saved register, xmm6-15
   with them, and the stack pointer and return address. clang's __builtin_setjmp, which this used first, saves the
   frame address, which on Win64 sits 128 bytes below the frame pointer clang addresses the frame's spill slots with,
   and its longjmp set rbp to it: the caller's reloads of c and the slot read garbage, and the text box thread
   called a stack address after its first longjmp.) */
#include "hos.h"
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <windows.h>
#include <string.h>

#define DEPTH 256
typedef struct { uint64_t rets[4], target; void *buf[32]; } SjSlot;   /* (buf: recomp_sj_setjmp's 248 bytes) */
typedef struct { SjSlot slot[DEPTH]; int depth, overflow; } SjStack;
static _Thread_local SjStack *stack;

#ifdef _WIN32
/* buf: rbx rbp rdi rsi r12 r13 r14 r15 at 0-56, rsp (after the return) at 64, the return address at 72, xmm6-15 at
   80-224, mxcsr at 240 and the x87 control word at 244 */
__attribute__((naked, returns_twice)) int recomp_sj_setjmp(void **buf) {
    __asm__ volatile(
        "movq %rbx, 0(%rcx)\n\t"
        "movq %rbp, 8(%rcx)\n\t"
        "movq %rdi, 16(%rcx)\n\t"
        "movq %rsi, 24(%rcx)\n\t"
        "movq %r12, 32(%rcx)\n\t"
        "movq %r13, 40(%rcx)\n\t"
        "movq %r14, 48(%rcx)\n\t"
        "movq %r15, 56(%rcx)\n\t"
        "leaq 8(%rsp), %rdx\n\t"
        "movq %rdx, 64(%rcx)\n\t"
        "movq (%rsp), %rdx\n\t"
        "movq %rdx, 72(%rcx)\n\t"
        "movdqu %xmm6, 80(%rcx)\n\t"
        "movdqu %xmm7, 96(%rcx)\n\t"
        "movdqu %xmm8, 112(%rcx)\n\t"
        "movdqu %xmm9, 128(%rcx)\n\t"
        "movdqu %xmm10, 144(%rcx)\n\t"
        "movdqu %xmm11, 160(%rcx)\n\t"
        "movdqu %xmm12, 176(%rcx)\n\t"
        "movdqu %xmm13, 192(%rcx)\n\t"
        "movdqu %xmm14, 208(%rcx)\n\t"
        "movdqu %xmm15, 224(%rcx)\n\t"
        "stmxcsr 240(%rcx)\n\t"
        "fnstcw 244(%rcx)\n\t"
        "xorl %eax, %eax\n\t"
        "ret\n\t");
}

__attribute__((naked, noreturn)) static void recomp_sj_longjmp(void **buf, int value) {
    __asm__ volatile(
        "movq 0(%rcx), %rbx\n\t"
        "movq 8(%rcx), %rbp\n\t"
        "movq 16(%rcx), %rdi\n\t"
        "movq 24(%rcx), %rsi\n\t"
        "movq 32(%rcx), %r12\n\t"
        "movq 40(%rcx), %r13\n\t"
        "movq 48(%rcx), %r14\n\t"
        "movq 56(%rcx), %r15\n\t"
        "movdqu 80(%rcx), %xmm6\n\t"
        "movdqu 96(%rcx), %xmm7\n\t"
        "movdqu 112(%rcx), %xmm8\n\t"
        "movdqu 128(%rcx), %xmm9\n\t"
        "movdqu 144(%rcx), %xmm10\n\t"
        "movdqu 160(%rcx), %xmm11\n\t"
        "movdqu 176(%rcx), %xmm12\n\t"
        "movdqu 192(%rcx), %xmm13\n\t"
        "movdqu 208(%rcx), %xmm14\n\t"
        "movdqu 224(%rcx), %xmm15\n\t"
        "ldmxcsr 240(%rcx)\n\t"
        "fldcw 244(%rcx)\n\t"
        "movl %edx, %eax\n\t"
        "testl %eax, %eax\n\t"
        "jnz 1f\n\t"
        "incl %eax\n\t"
        "1:\n\t"
        "movq 64(%rcx), %rsp\n\t"
        "jmpq *72(%rcx)\n\t");
}

#elif defined(__aarch64__)
/* (arm64 / macOS Apple Silicon) AAPCS64 callee-saved registers: x19-x28, x29 (fp), x30 (lr), sp, and d8-d15.
   buf in x0, value in w1 */
__attribute__((naked, returns_twice)) int recomp_sj_setjmp(void **buf) {
    __asm__ volatile(
        "stp x19, x20, [x0, #0]\n\t"
        "stp x21, x22, [x0, #16]\n\t"
        "stp x23, x24, [x0, #32]\n\t"
        "stp x25, x26, [x0, #48]\n\t"
        "stp x27, x28, [x0, #64]\n\t"
        "stp x29, x30, [x0, #80]\n\t"
        "mov x1, sp\n\t"
        "str x1, [x0, #96]\n\t"
        "stp d8, d9, [x0, #104]\n\t"
        "stp d10, d11, [x0, #120]\n\t"
        "stp d12, d13, [x0, #136]\n\t"
        "stp d14, d15, [x0, #152]\n\t"
        "mov w0, #0\n\t"
        "ret\n\t");
}

__attribute__((naked, noreturn)) static void recomp_sj_longjmp(void **buf, int value) {
    __asm__ volatile(
        "ldp x19, x20, [x0, #0]\n\t"
        "ldp x21, x22, [x0, #16]\n\t"
        "ldp x23, x24, [x0, #32]\n\t"
        "ldp x25, x26, [x0, #48]\n\t"
        "ldp x27, x28, [x0, #64]\n\t"
        "ldp x29, x30, [x0, #80]\n\t"
        "ldr x2, [x0, #96]\n\t"
        "mov sp, x2\n\t"
        "ldp d8, d9, [x0, #104]\n\t"
        "ldp d10, d11, [x0, #120]\n\t"
        "ldp d12, d13, [x0, #136]\n\t"
        "ldp d14, d15, [x0, #152]\n\t"
        "cmp w1, #0\n\t"
        "csinc w0, w1, wzr, ne\n\t"
        "ret\n\t");
}

#else
/* (linux x86-64) the System V ABI's: the buffer as above, its callee-saved registers only (rbx rbp r12-r15: rdi, rsi and the
   xmm registers are the caller's to keep there), buf in rdi and the value in esi */
__attribute__((naked, returns_twice)) int recomp_sj_setjmp(void **buf) {
    __asm__ volatile(
        "movq %rbx, 0(%rdi)\n\t"
        "movq %rbp, 8(%rdi)\n\t"
        "movq %r12, 32(%rdi)\n\t"
        "movq %r13, 40(%rdi)\n\t"
        "movq %r14, 48(%rdi)\n\t"
        "movq %r15, 56(%rdi)\n\t"
        "leaq 8(%rsp), %rdx\n\t"
        "movq %rdx, 64(%rdi)\n\t"
        "movq (%rsp), %rdx\n\t"
        "movq %rdx, 72(%rdi)\n\t"
        "stmxcsr 240(%rdi)\n\t"
        "fnstcw 244(%rdi)\n\t"
        "xorl %eax, %eax\n\t"
        "ret\n\t");
}

__attribute__((naked, noreturn)) static void recomp_sj_longjmp(void **buf, int value) {
    __asm__ volatile(
        "movq 0(%rdi), %rbx\n\t"
        "movq 8(%rdi), %rbp\n\t"
        "movq 32(%rdi), %r12\n\t"
        "movq 40(%rdi), %r13\n\t"
        "movq 48(%rdi), %r14\n\t"
        "movq 56(%rdi), %r15\n\t"
        "ldmxcsr 240(%rdi)\n\t"
        "fldcw 244(%rdi)\n\t"
        "movl %esi, %eax\n\t"
        "testl %eax, %eax\n\t"
        "jnz 1f\n\t"
        "incl %eax\n\t"
        "1:\n\t"
        "movq 64(%rdi), %rsp\n\t"
        "jmpq *72(%rdi)\n\t");
}

#endif

void **recomp_sj_push(Ctx *c, uint64_t r0, uint64_t r1, uint64_t r2, uint64_t r3) {
    (void)c;
    if (!stack) stack = (SjStack *)calloc(1, sizeof *stack);
    if (stack->depth >= DEPTH) {   /* (too deep: the outermost slots go, as they are the least likely targets) */
        memmove(&stack->slot[0], &stack->slot[1], sizeof stack->slot[0] * (DEPTH - 1));
        stack->depth = DEPTH - 1;
        if (!stack->overflow++) hos_log("setjmp: more than %d nested setjmp owners on this thread", DEPTH);
    }
    SjSlot *s = &stack->slot[stack->depth++];
    s->rets[0] = r0, s->rets[1] = r1, s->rets[2] = r2, s->rets[3] = r3, s->target = 0;
    return s->buf;
}

uint64_t recomp_sj_target(void **buf) { return ((SjSlot *)((char *)buf - offsetof(SjSlot, buf)))->target; }

void recomp_sj_pop(void **buf) {
    if (!stack) return;
    const int i = (int)(((SjSlot *)((char *)buf - offsetof(SjSlot, buf))) - stack->slot);
    if (i >= 0 && i < DEPTH && i < stack->depth) stack->depth = i;
}

/* a64_call_miss's first question: a longjmp to a pushed setjmp owner? (does not return when it is) */
void hos_setjmp_return(Ctx *c, uint64_t target) {
    if (!stack || !stack->depth || !target) return;
    for (int i = stack->depth - 1; i >= 0; i--) {
        SjSlot *s = &stack->slot[i];
        if (s->rets[0] != target && s->rets[1] != target && s->rets[2] != target && s->rets[3] != target) continue;
        static volatile LONG logged;
        if (InterlockedIncrement(&logged) <= 4)
            hos_log("longjmp to %#llx (value %llu, %d slots above dropped)", (unsigned long long)target,
                    (unsigned long long)c->x[0], stack->depth - 1 - i);
        s->target = target;
        stack->depth = i + 1;
        recomp_sj_longjmp(s->buf, 1);
    }
}

/* ...and every indirect jump's (third_party/a64-kit/rt a64_ijump_hook): the setjmp return addresses are entries too
   (the callers run them, recomp_sj_target), so the longjmp's BR finds a function there and never missed: it called
   the owner's code inside longjmp's own frame, which returned into longjmp's caller (0x8168215c, the UDF after OoT's
   BL longjmp: the text box thread's "branch to a non-function") */
void a64_ijump_hook(Ctx *c, uint64_t target) { hos_setjmp_return(c, target); }

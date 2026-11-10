# Device loss during native presentation

The replay already treats `VK_ERROR_DEVICE_LOST` as terminal: `device_lost()`
writes its checkpoint report once, then `replay_fatal()` flushes the host log
before exiting. Continuing cannot complete GPU work and can retain captures and
staging allocations indefinitely.

Native presentation uses the same policy for the frame-fence wait/reset,
command-pool reset, command-buffer begin/end, image acquisition, blit submission
and presentation. The check precedes dependent work: a failed fence wait cannot
lead to readback, a failed submission cannot enqueue a present waiting for its
unsignaled semaphore, and a failed present cannot be counted as completed by
Reflex. Both the shared and dedicated presentation queues are covered.

This does not recover a lost device, change successful presentation, or replace
the existing out-of-date/suboptimal/Wayland-timeout handling. Other error classes
retain their existing behavior, including allocation errors; this is not a
general submission-recovery mechanism.

`tests/test_present_device_loss.py` executes the actual call/guard sites with
injected return values. It covers nine sites (two presentation queues), checks
that loss reports before the site continues, and supplies non-loss controls.
It tests routing rather than simulating an entire Vulkan implementation. The
existing `test_device_lost_exit.py` separately exercises the real concurrent
report-once and host-log-flush/exit contract. Hardware-reset recovery is not
claimed, and no physical driver reset is needed to run these tests.

#!/usr/bin/env python3
"""Flashlight: the flash LED of the N900 as a torch (python3 torch.py start|stop|status).

The ADP1653 flash driver lets the torch burn only while the camera device is open, so `start` leaves a small process that holds /dev/video0 open
(the same way the flashlight applet of Maemo does) and `stop` ends it, which puts the LED out. The process also puts it out when it is killed.
The controls are V4L2: V4L2_CID_TORCH_INTENSITY (0 = off, 1 = on) on the camera device, which the group `video` may open."""
import fcntl
import os
import signal
import struct
import sys
import time

DEVICE = os.environ.get("GOTHI_TORCH_DEVICE", "/dev/video0")
PIDFILE = os.path.join(os.path.expanduser("~"), ".cache", "gothi", "torch.pid")
MARK = b"torch.py"                           # what the command line of our process contains (a pid file may be left over from before a reboot)
V4L2_CID_TORCH_INTENSITY = 0x009a0910        # V4L2_CID_CAMERA_CLASS_BASE + 16
VIDIOC_S_CTRL = 0xC008561C                   # _IOWR('V', 28, struct v4l2_control)
VIDIOC_G_CTRL = 0xC008561B


def set_torch(fd, value):
    fcntl.ioctl(fd, VIDIOC_S_CTRL, struct.pack("Ii", V4L2_CID_TORCH_INTENSITY, value))


def read_pid(path=None):
    """The pid of the running holder, None when there is none (a stale file is removed)."""
    path = path or PIDFILE
    try:
        with open(path) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if MARK not in f.read():
                raise OSError("not ours")           # the pid was reused by another process
        return pid
    except (OSError, ValueError):
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def holder(ready):
    """The detached process: LED on, tell the parent, wait for SIGTERM, LED off."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    fd = os.open(DEVICE, os.O_RDWR)
    try:
        set_torch(fd, 1)
        with open(PIDFILE, "w") as f:
            f.write(str(os.getpid()))
        os.write(ready, b"1")
        while True:
            time.sleep(3600)
    finally:
        try:
            set_torch(fd, 0)
        except OSError:
            pass
        os.close(fd)
        try:
            os.remove(PIDFILE)
        except OSError:
            pass


def start():
    if read_pid():
        return 0
    os.makedirs(os.path.dirname(PIDFILE), exist_ok=True)
    r, w = os.pipe()
    if os.fork() == 0:
        os.close(r)
        os.setsid()
        for n in (0, 1, 2):
            os.close(n)
        os.open(os.devnull, os.O_RDWR)
        os.dup2(0, 1)
        os.dup2(0, 2)
        try:
            holder(w)
        except SystemExit:
            pass
        except BaseException:
            pass
        os._exit(0)
    os.close(w)
    import select
    ok = select.select([r], [], [], 3)[0] and os.read(r, 1) == b"1"
    return 0 if ok else 1


def stop():
    pid = read_pid()
    if pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if read_pid() is None:
                break
            time.sleep(0.1)
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "start":
        return start()
    if cmd == "stop":
        return stop()
    if cmd == "status":
        return 0 if read_pid() else 1
    print("usage: torch.py start|stop|status", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

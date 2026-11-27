import importlib.util
import json
import os
import shutil
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "modules", "flashlight", "torch.py")


def load():
    spec = importlib.util.spec_from_file_location("torch_helper", PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Torch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.t = load()
        self.t.PIDFILE = os.path.join(self.tmp, "torch.pid")
        self.t.DEVICE = os.devnull
        self.t.MARK = b"unittest"                  # the forked holder has the command line of this test run
        self.log = os.path.join(self.tmp, "calls")

        def fake(fd, value):                       # the LED is not there: the calls are written down instead
            with open(self.log, "a") as f:
                f.write(f"{value}\n")
        self.t.set_torch = fake

    def tearDown(self):
        self.t.stop()
        shutil.rmtree(self.tmp)

    def calls(self):
        try:
            with open(self.log) as f:
                return f.read().split()
        except OSError:
            return []

    def test_no_pid_file_means_off(self):
        self.assertIsNone(self.t.read_pid())
        self.assertEqual(self.t.main(["torch.py", "status"]), 1)

    def test_stale_pid_file_is_removed(self):
        with open(self.t.PIDFILE, "w") as f:
            f.write("999999")
        self.assertIsNone(self.t.read_pid())
        self.assertFalse(os.path.exists(self.t.PIDFILE))

    def test_pid_of_a_foreign_process_is_not_ours(self):
        self.t.MARK = b"no-such-program"
        with open(self.t.PIDFILE, "w") as f:
            f.write(str(os.getpid()))
        self.assertIsNone(self.t.read_pid())

    def test_garbage_pid_file(self):
        with open(self.t.PIDFILE, "w") as f:
            f.write("abc")
        self.assertIsNone(self.t.read_pid())

    def test_start_lights_and_stop_puts_out(self):
        self.assertEqual(self.t.start(), 0)
        self.assertIsNotNone(self.t.read_pid())
        self.assertEqual(self.t.main(["torch.py", "status"]), 0)
        self.assertEqual(self.t.start(), 0)         # a second start changes nothing
        self.assertEqual(self.calls(), ["1"])
        self.t.stop()
        for _ in range(30):
            if self.calls() == ["1", "0"]:
                break
            time.sleep(0.1)
        self.assertEqual(self.calls(), ["1", "0"])
        self.assertIsNone(self.t.read_pid())

    def test_start_fails_without_the_device(self):
        self.t.DEVICE = os.path.join(self.tmp, "missing")
        self.assertEqual(self.t.start(), 1)
        self.assertIsNone(self.t.read_pid())

    def test_stop_without_start_is_fine(self):
        self.assertEqual(self.t.stop(), 0)

    def test_usage(self):
        self.assertEqual(self.t.main(["torch.py"]), 2)

    def test_the_ioctl_arguments(self):
        import struct
        self.assertEqual(struct.calcsize("Ii"), 8)
        self.assertEqual(self.t.V4L2_CID_TORCH_INTENSITY, 0x009a0900 + 16)


class Manifest(unittest.TestCase):
    def test_loads_as_a_switch(self):
        import sys
        sys.path.insert(0, os.path.join(HERE, ".."))
        from gothi import modules
        path = os.path.join(HERE, "..", "modules", "flashlight")
        with open(os.path.join(path, "module.json")) as f:
            data = json.load(f)
        data["requires"] = []                      # the camera device is not on this computer
        m = modules.Module(path, data)
        self.assertEqual(m.kind, "switch")
        self.assertTrue(m.cmds["start"].endswith("torch.py start"))
        self.assertIn("/modules/flashlight/", m.cmds["start"])
        self.assertTrue(m.auto_off)


if __name__ == "__main__":
    unittest.main()

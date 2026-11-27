"""Tests of gothi/bluetooth.py (the text of hcitool and of the files in /var/lib/bluetooth), all with made-up devices:  python3 -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gothi import bluetooth as bt  # noqa: E402

SCAN = """Scanning ...

BD Address:\t00:11:22:33:44:01 [mode 1, clkoffset 0x0d08]
Device name:\tLiving Room TV [cached]
Device class:\tAudio/Video, Video Display and Loudspeaker (0x0c243c)

BD Address:\t00:11:22:33:44:02 [mode 1, clkoffset 0x0e39]
Device name:\tPocket Phone
Device class:\tPhone, Smart phone (0x5a020c)

BD Address:\t00:11:22:33:44:03 [mode 1, clkoffset 0x0001]
Device name:\tn/a
Device class:\tPeripheral, Keyboard (0x002540)

BD Address:\t00:11:22:33:44:04 [mode 1, clkoffset 0x0002]
Device name:\tBlue Buds
Device class:\tAudio/Video, Headphones (0x240418)
"""

NAMES = "00:11:22:33:44:02 Pocket Phone\n00:11:22:33:44:05 Old Laptop\n00:11:22:33:44:06 car-kit\nbroken line\n"
LINKKEYS = "00:11:22:33:44:02 0123456789ABCDEF0123456789ABCDEF 4 0\n00:11:22:33:44:06 FEDCBA9876543210FEDCBA9876543210 0 4\n"
LASTSEEN = "00:11:22:33:44:02 2026-11-27 15:54:08 GMT\n00:11:22:33:44:05 2012-09-29 20:05:07 GMT\n"
KNOWN_FILES = {"names": NAMES, "linkkeys": LINKKEYS, "lastseen": LASTSEEN}


class ParseTest(unittest.TestCase):
    def test_parse_scan(self):
        d = bt.parse_scan(SCAN)
        self.assertEqual([x["addr"] for x in d], ["00:11:22:33:44:0" + str(i) for i in (1, 2, 3, 4)])
        self.assertEqual(d[0]["name"], "Living Room TV")
        self.assertTrue(d[0]["cached"])
        self.assertFalse(d[1]["cached"])
        self.assertEqual(d[0]["cls"], 0x0c243c)
        self.assertEqual(d[2]["name"], "")                    # n/a: the device did not answer the name request

    def test_empty_and_garbage(self):
        self.assertEqual(bt.parse_scan(""), [])
        self.assertEqual(bt.parse_scan("Scanning ...\n"), [])
        self.assertEqual(bt.parse_scan("Inquiry failed: Input/output error\n"), [])

    def test_a_device_without_a_class(self):
        d = bt.parse_scan("BD Address:\t00:11:22:33:44:09 [mode 1]\nDevice name:\tX\n")
        self.assertEqual((d[0]["name"], d[0]["cls"]), ("X", None))

    def test_kinds(self):
        d = bt.parse_scan(SCAN)
        self.assertEqual([bt.kind(x["cls"]) for x in d], ["video display", "phone", "keyboard", "headphones"])
        self.assertEqual([bt.short_kind(x["cls"]) for x in d], ["tv", "phone", "input", "audio"])
        self.assertEqual((bt.kind(None), bt.short_kind(None)), ("unknown", "?"))
        self.assertTrue(all(len(bt.short_kind(c)) <= 5 for c in range(0, 0x200000, 0x0104)))

    def test_label_falls_back_to_the_end_of_the_address(self):
        d = bt.parse_scan(SCAN)
        self.assertEqual(bt.label(d[2]), "33:44:03")
        self.assertEqual(bt.label(d[1]), "Pocket Phone")


class MergeTest(unittest.TestCase):
    def test_counts_scans_and_keeps_names(self):
        known = {}
        self.assertEqual(bt.merge(known, bt.parse_scan(SCAN)), 4)
        self.assertEqual(bt.merge(known, bt.parse_scan(SCAN)[:1]), 0)
        self.assertEqual(known["00:11:22:33:44:01"]["seen"], 2)
        self.assertEqual(known["00:11:22:33:44:02"]["seen"], 1)
        more = bt.parse_scan(SCAN.replace("n/a", "Typist"))
        bt.merge(known, more)
        self.assertEqual(known["00:11:22:33:44:03"]["name"], "Typist")
        bt.merge(known, bt.parse_scan(SCAN))                  # a later scan without the name does not delete it
        self.assertEqual(known["00:11:22:33:44:03"]["name"], "Typist")

    def test_summary(self):
        s = bt.summary(bt.parse_scan(SCAN))
        self.assertEqual((s["count"], s["named"]), (4, 3))
        self.assertEqual(s["kinds"], {"video display": 1, "phone": 1, "keyboard": 1, "headphones": 1})


class KnownTest(unittest.TestCase):
    def test_paired_addresses_never_look_at_the_keys(self):
        self.assertEqual(bt.paired_addresses(LINKKEYS), {"00:11:22:33:44:02", "00:11:22:33:44:06"})
        self.assertEqual(bt.paired_addresses("garbage\n\n"), set())

    def test_known_devices(self):
        d = bt.known_devices(NAMES, LINKKEYS, LASTSEEN)
        self.assertEqual([x["name"] for x in d], ["car-kit", "Pocket Phone", "Old Laptop"])      # paired first, then by name
        self.assertEqual([x["paired"] for x in d], [True, True, False])
        self.assertEqual(d[1]["last"], "2026-11-27")
        self.assertEqual(d[0]["last"], "")

    def test_read_known_with_a_reader(self):
        files = {"names": NAMES, "linkkeys": LINKKEYS, "lastseen": LASTSEEN}
        self.assertEqual(len(bt.read_known(files.get)), 3)
        self.assertEqual(bt.read_known(lambda n: ""), [])

    def test_ago(self):
        import time
        now = time.mktime(time.strptime("2026-11-27", "%Y-%m-%d")) + 3600
        self.assertEqual(bt.ago("2026-11-27", now), "today")
        self.assertEqual(bt.ago("2026-11-20", now), "7 d")
        self.assertEqual(bt.ago("2026-06-27", now), "5 mo")
        self.assertEqual(bt.ago("2012-09-29", now), "14 y")
        self.assertEqual(bt.ago("", now), "")


class AdapterTest(unittest.TestCase):
    def test_adapter_up(self):
        self.assertTrue(bt.adapter_up(lambda: "hci0:\tType: UART\n\tUP RUNNING PSCAN ISCAN \n"))
        self.assertFalse(bt.adapter_up(lambda: "hci0:\tType: UART\n\tDOWN \n"))
        self.assertFalse(bt.adapter_up(lambda: ""))

    def test_scan_with_a_runner_and_a_failing_one(self):
        self.assertEqual(len(bt.scan(lambda: SCAN)), 4)

        def broken():
            raise OSError("no hcitool")
        self.assertEqual(bt.scan(broken), [])

    def test_the_inquiry_command(self):
        self.assertEqual(bt.INQUIRY[:2], ["hcitool", "scan"])
        self.assertIn("--class", bt.INQUIRY)


if __name__ == "__main__":
    unittest.main()

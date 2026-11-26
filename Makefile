# n900-gothi: a Flipper Zero style interface for the N900 as the package gothi. Targets and conventions: ../../mk/app.mk
#   make -C apps/n900-gothi deb       the package (needs network once: the firmware graphics are fetched at the pinned commit)
#   make -C apps/n900-gothi install   to the phone (install python3-pysdl2 first: make -C apps/pysdl2 install)
override APP := n900-gothi
PKG      := gothi
VERSION ?= 0.3.0
RUN_CMD  := DISPLAY=:0 /usr/bin/gothi
include ../../mk/app.mk

# the sources are in a folder (the folder itself changes rarely): rebuild and repackage when a .py changes
$(STAMP): $(wildcard $(ROOT)/apps/$(APP)/gothi/*.py $(ROOT)/apps/$(APP)/gothi/*.json)

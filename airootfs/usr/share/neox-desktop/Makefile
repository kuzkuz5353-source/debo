PREFIX ?= /usr
DESTDIR ?=
PYTHON ?= python3

.PHONY: all check install uninstall clean package-arch

all:
	@echo "NEOX is a Python/Hyprland desktop shell; run 'make install' to install."

check:
	$(PYTHON) -m py_compile shell/*.py widgets/*.py themes/theme-engine.py dbus/neox-dbus-service.py
	bash -n scripts/install.sh scripts/neox-session.sh scripts/neox-autostart.sh scripts/uninstall.sh

install:
	PREFIX=$(PREFIX) DESTDIR=$(DESTDIR) bash scripts/install.sh

uninstall:
	PREFIX=$(PREFIX) DESTDIR=$(DESTDIR) bash scripts/uninstall.sh

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete

package-arch:
	cd packaging/arch && makepkg -sf

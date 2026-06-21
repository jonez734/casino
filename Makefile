PROJECT = casino
all:

clean:
	-rm *~
	-$(MAKE) -C casino clean
	-$(MAKE) -C sql clean

backup:
	rsync --recursive --verbose --exclude=.venv . /run/media/jam/AEAB-CF37/projects/$(PROJECT)/

# All variables inherited from parent: PROJECT, STAGE, SKINDIR, HOST, SCSS, RSYNC

all:

clean:
	-rm *~
	$(MAKE) -C php clean
	$(MAKE) -C skin clean

prod:
	mkdir -p $(STAGE)
	$(MAKE) -C php stage
	$(MAKE) -C skin stage
	$(RSYNC) htaccess-prod $(STAGE).htaccess
	$(RSYNC) config-prod.php $(STAGE)config.php

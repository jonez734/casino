all:

clean:
	-rm *~
	$(MAKE) -C scss clean
	$(MAKE) -C tmpl clean

stage:
	mkdir -p $(SKINDIR)tmpl/
	mkdir -p $(SKINDIR)scss/
	$(MAKE) -C scss stage
	$(MAKE) -C tmpl stage

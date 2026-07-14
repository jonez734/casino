all:

clean:
	-rm *~

stage:
	mkdir -p $(SKINDIR)tmpl/
	$(RSYNC) *.tmpl $(SKINDIR)tmpl/

.PHONY: clean stage

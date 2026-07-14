all:

.scss.css:
	$(SCSS) $< $@

stage:
	$(SCSS) --update .:$(SKINDIR)css/

clean:
	-rm *~ *.css *.css.map

.SUFFIXES: .scss .css

.PHONY: clean stage

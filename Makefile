all:

clean:
	-rm *~
	-$(MAKE) -C casino clean
	-$(MAKE) -C sql clean

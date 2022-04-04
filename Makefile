all:

clean:
	-rm *~
	-$(MAKE) -C blackjack clean
	-$(MAKE) -C poker clean

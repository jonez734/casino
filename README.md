# casino

## Python 2 → Python 3 Migration Notes
- Python 2 had `ttk` as a separate package (`import ttk`). Python 3 ships `ttk` as part of tkinter (`from tkinter import ttk`). This matters when migrating code or creating dependency lists.

## blackjack
- account for players standing, still give dealer a chance to draw cards and win
- blackjack should not keep drawing cards to bust the player or the dealer
- https://bicyclecards.com/how-to-play/blackjack/
- if player and dealer both have blackjack, what happens? currently, player wins: "push"
- if player and dealer have the same value, it's called a "push" and no bets are paid.
- https://www.casinocenter.com/rules-strategy-blackjack/
- if player has < 21, don't end hand
- [ ] handle 'push' properly.. check only at end of hand
  * http://www.casinostrategy.org/blackjack/blackjack-terminology.htm
  * https://www.quora.com/What-is-a-push-in-blackjack
- [ ] handle "split" of a pair-- player now plays two hands at the same time
- [ ] double down
- [ ] https://stackoverflow.com/questions/11068872/pil-imagetk-equivalent-in-python-3-x @since 20221117

## poker
- https://bicyclecards.com/how-to-play/basics-of-poker/

```If the dealer goes over 21, the dealer pays each player who has stood the
amount of that player's bet.  If the dealer stands at 21 or less, the dealer
pays the bet of any player having a higher total (not exceeding 21) and
collects the bet of any player having a lower total.```

```If both the player and the dealer have a tie—including with a
blackjack—the bet is a tie or “push” and money is neither lost, nor paid.```

```[~/<1>casino/blackjack] [9:28pm] [jam@cyclops] % ./blackjack
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 blackjack                                                                                 │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
 Shoe.shuffle.100: running.. 
 Shoe.shuffle.100: running.. 
 Shoe.shuffle.100: running.. 
player: Q♥ 9♦  [19]
dealer: 1♠ 1♣  [2]
player status: play
dealer status: play
player [H]it or [S]tand: stand
player: Q♥ 9♦  [19]
dealer: 1♠ 1♣  [2]
 dealer < 17, hit 
Traceback (most recent call last):
  File "/usr/lib64/python3.9/runpy.py", line 197, in _run_module_as_main
    return _run_code(code, main_globals, None,
  File "/usr/lib64/python3.9/runpy.py", line 87, in _run_code
    exec(code, run_globals)
  File "/home/jam/projects/casino/blackjack/blackjack.py", line 252, in <module>
    main()
  File "/home/jam/projects/casino/blackjack/blackjack.py", line 247, in main
    play(shoe, dealerhand, playerhand)
  File "/home/jam/projects/casino/blackjack/blackjack.py", line 180, in play
    dealervalue = dealerhand.value()
TypeError: 'int' object is not callable
```

```
[~/<1>casino/blackjack] [9:47pm] [jam@cyclops] % ./blackjack
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 blackjack                                                                                 │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
 Shoe.shuffle.100: running.. 
 Shoe.shuffle.100: running.. 
 Shoe.shuffle.100: running.. 
player: 2♥ 10♠  [12]
dealer: 2♠ 7♠  [9]
player status: play
dealer status: play
player [H]it or [S]tand: hit
player: 2♥ 10♠ 1♥  [13]
dealer: 2♠ 7♠  [9]
 dealer < 17, hit 
end hand
player: 2♥ 10♠ 1♥  [13]
dealer: 2♠ 7♠ K♥  [19]
dealer: win, player: loss
```

- in this case, player would have won if adjustaces() was working:

```
[~/<1>casino/blackjack] [7:09pm] [jam@cyclops] % ./blackjack
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 blackjack                                                                                 │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
 Shoe.shuffle.100: running.. 
 Shoe.shuffle.100: running.. 
 Shoe.shuffle.100: running.. 
player: 5♦ 4♥   [9] 
dealer: 3♣ ██   [6] 
player status: play
dealer status: play
player [H]it or [S]tand: hit
player: 5♦ 4♥ 7♥   [16] 
dealer: 3♣ ██   [6] 
 dealer < 17, hit 
player: 5♦ 4♥ 7♥   [16] 
dealer: 3♣ 3♦ 7♥   [13] 
player status: play
dealer status: play
player [H]it or [S]tand: hit
player: 5♦ 4♥ 7♥ A♣   [30] 
dealer: 3♣ 3♦ 7♥   [13] 
end hand
player: 5♦ 4♥ 7♥ A♣   [30] 
dealer: 3♣ 3♦ 7♥   [13] 
dealer: win, player: bust
another hand? [Yn]: No
```

- when encountering an ace and total > 21, dealer always uses 1. should player be given a choice?
- https://www.letsgambleusa.com/federal-gambling-laws/
- [15 U.S. Code CHAPTER 24—TRANSPORTATION OF GAMBLING DEVICES](https://www.law.cornell.edu/uscode/text/15/chapter-24)
- every player gets two cards face up, dealer's 2nd card is face down - [Blackjack Tournament Magic May 5th 2018](https://youtu.be/r0urRi_zQGk)
- it would be interesting to collect stats re: hands, wins, losses, etc
- dealer and player have a "12".. what should happen?
- there can be *no* remuneration from the games.. and make up a new currency for every game?
  * tax fraud?
  * wire fraud?
  * there will always be somebody trying to game the system. (@ty pscug)
- [ ] allow player surrender (drop out of hand, refund 50% of total bets on the hand)
- [ ] player may have multiple hands (splits)
- [ ] mapping table which tracks playerid, inetaddr, and gameid
- [ ] slots are complex.
  * stigg has a 3 wheel slots game on his board
- 'greed' for image bbs 3.0 has a yes/no prompt for each dice you can replace. might work for yahtzee if cursor keys not viable.
- https://stackoverflow.com/a/43794884 -- answers how to do subpackages using setuptools (@since 20220404)
- [ ] make a way to decide who can play what games and/or which tables (security) (@since 20220404)
- handle table min/max

"""
Under traditional rules, a natural blackjack (the player draws an ace and a ten-value card) pays three to two, meaning a $100 bet returns $150. All other bets pay even money;
"""

https://www.google.com/url?sa=t&rct=j&q=&esrc=s&source=web&cd=&cad=rja&uact=8&ved=2ahUKEwiAx-Xaxsz5AhVqmmoFHXYNATMQFnoECBUQAw&url=https%3A%2F%2Fwww.forbes.com%2Fsites%2Fdavidschwartz%2F2018%2F07%2F16%2Fblackjacks-rise-and-fall-shows-what-drives-customers-away%2F&usg=AOvVaw0sUpI0_IDl6oScfj9Q2nE_
https://www.google.com/search?client=firefox-b-1-d&q=what+is+a+draw+in+blackjack
https://www.google.com/search?client=firefox-b-1-d&q=calculate+probabilty+of+winning+blackjack+hand

- there is no card w value one other than an ace @since 20221112 @ty chuck

- if player splits aces, they only get one card on each ace, they cannot hit
  again. only with aces. if it is anything other than aces, player can keep hitting.
- always bet same amount on both side of split
- dealer does not bet
- some tables have a rule that says dealer must hit on soft 17 (A+6)
- if player has blackjack, dealer stops playing, redeal
- if player gets blackjack, dealer has 2 cards, player has 2 cards, dealer does not have blackjack, payout is 1.5x

- if player gets 5 cards without a bust, player wins

- https://opengameart.org/content/playing-cards-vector-png
- https://techvidvan.com/tutorials/python-image-viewer/
- [ ] find a way to resize() png files which represent card faces (@since 20221121)
- https://www.geeksforgeeks.org/how-to-set-font-for-text-in-tkinter/ (@since 20221124)

- https://stackoverflow.com/questions/52875751/is-their-a-grid-remember-reversible-grid-forget
- https://www.geeksforgeeks.org/python-forget_pack-and-forget_grid-method-in-tkinter/
- https://www.google.com/search?client=firefox-b-1-d&q=what+is+the+C+FILE+structure
- https://www.geeksforgeeks.org/python-pack-method-in-tkinter/
- (https://youtu.be/bi42B7RW_wI)[Using Structs and Classes with Python Ctypes]
- https://edge.twinspires.com/blackjack-terms-explained-blackjack-glossary-and-terminology/
- (https://youtu.be/gBS2pYAGUgA)[Build A Blackjack Card Game - Python Tkinter GUI Tutorial 208]

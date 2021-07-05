import ttyio4 as ttyio
import random

def getcardtablelocations():
    cardtablelocations = [
      'Arnhem - Netherlands',
      'Barcelona - Spain',
      'Birmingham - England',
      'Budapest - Hungary',
      'Helsinki - Finland',
      'Munich - Germany',
      'Sicily - Italy',
      'Oslo - Norway',
      'Vienna - Austria',
      'Cape Town - South Africa'
    ]
    return cardtablelocations

def initshoe(decks=3):
  shoe = []
  for d in range(0, decks):
    deck = []
    for suit in [ "{spade}", "{diamond}", "{club}", "{heart}" ]:
      for v in ["A", "K", "Q", "J", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
        card = "%s%s" % (v, suit)
        deck.append(card)
    shoe += deck
#  ttyio.echo("shoe=%r" % (shoe))
  return shoe

def shuffleshoe(shoe):
#  ttyio.echo("shuffleshoe.100: shoe=%r" % (shoe))
  random.shuffle(shoe)
  return

def drawcard(shoe):
#  ttyio.echo("before. shoe=%r" % (shoe))
#  ttyio.echo("drawcard.100: shoe=%r" % (shoe))
  card = shoe.pop(-1)
#  ttyio.echo("card=%r" % (card))
#  ttyio.echo("after. shoe=%r" % (shoe))
  return card

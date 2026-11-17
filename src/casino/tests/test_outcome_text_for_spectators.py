"""A round's outcome text is in the second person only for the player it is about.

The settlement writes "you busted" for the seat. A table broadcast reaches every watcher, so a watcher reads "you"
for another player's hand. Each outcome carries a third-person line for everyone else.
"""

from casino.blackjack import settle


def test_the_player_reads_their_own_line_in_the_second_person():
    text = settle.describe("player_bust", player_cards=["10S", "5D", "JD"], dealer_cards=["QC", "9C"], bet=2, net=-2)
    assert text.startswith("you busted")


def test_a_spectator_line_names_the_player_not_you():
    line = settle.describe_for_others("alice", "player_bust", player_cards=["10S", "5D", "JD"],
                                      dealer_cards=["QC", "9C"], bet=2, net=-2)
    assert line.startswith("alice busted")
    assert "you" not in line.lower()


def test_the_table_broadcast_names_the_player_and_the_reply_keeps_you():
    from casino.api.handler import _round_settled_payload

    settled = {"dealer_total": 18, "dealer_cards": ["QC", "8D"], "outcomes": [{
        "player": "alice", "net": -2, "result": "bust",
        "text": "you busted with 22, bet 2, net -2",
        "others_text": "alice busted with 22, bet 2, net -2",
    }]}
    broadcast = _round_settled_payload(settled, None)
    own = _round_settled_payload(settled, "alice")
    assert broadcast["outcomes"][0]["text"] == "alice busted with 22, bet 2, net -2"
    assert own["outcomes"][0]["text"] == "you busted with 22, bet 2, net -2"

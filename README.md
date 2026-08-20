# casino

> **Casino-style games for the bbsengine6 BBS stack.**

`casino` is a Python package that ships five casino-style games
(blackjack, poker, slots, yahtzee, tic-tac-toe) as a
[bbsengine6](../bbsengine6/) BBS module and as a separate
WebSocket-driven real-time game server. It runs in three modes:

1. **Door-mode BBS module** (`python -m casino`) — interactive ttyio
   menu in a BBS session.
2. **WebSocket game server** — registered with bed via
   `casino.api.handler.MessageRouter`.
3. **Standalone TUI client** (`casino`, default branch) — long-lived
   WebSocket client for sysops and CI.

> **See [`SPEC.md`](SPEC.md)** for the architecture: the layered
> services / DAL / games stack, the message types, the poker variant
> plugin system, and the per-game READMEs.
>
> **`CHANGELOG.md`** records user-visible changes. **`TODO.md`** is
> the open work + line-numbered cross-references.
> **`TODO_CLIENT.md`** is the historical client-split design doc.

## Regulatory and Legal Notice

This project is a software platform for casino-style games (blackjack,
poker, slots, yahtzee, etc.). It is **not** a licensed gambling
operator and is intended for development, testing, and demonstration
purposes only. Deploying, operating, or accepting real-money wagers
through this software may be regulated or prohibited in your
jurisdiction.

> **State jurisdiction applies.** Gambling laws are set and enforced at
> the state (and tribal) level in the United States. Each state has its
> own statutes, licensing schemes, and prohibitions; some states permit
> certain forms of gambling, others prohibit them entirely, and many
> restrict or forbid online gambling specifically. You are responsible
> for determining whether operating, hosting, or using this software is
> lawful in the relevant state(s) and tribal jurisdiction(s) before any
> deployment or use. State jurisdiction applies independently of where
> the operator, the servers, and the customers are located.

### Operator location vs. server location (US)

When the operator is in one US state and the servers are in another,
**state jurisdiction applies to each, and several federal statutes sit
on top:**

1. **Operator's home state** — the state where the business is
   conducted. Most state gambling statutes make it a crime to
   *operate* a gambling business from within the state regardless of
   where the servers sit. State jurisdiction applies.
2. **Server's state** — the state where the hardware physically
   resides. That state may license, regulate, or prohibit the
   activity. Hosting unlicensed gambling software can be a separate
   violation of the server's state law. State jurisdiction applies.
3. **Customer's state** — the state where the bettor is located when
   the bet is initiated. UIGEA (31 USC §5362) and the Wire Act (18 USC
   §1084) key off "the place where the bet is made or received" — not
   the server. State jurisdiction applies.
4. **Federal overlay** — the Wire Act (interstate transmission of
   sports-bets), UIGEA (payment processing for unlawful Internet
   gambling), and the Bank Secrecy Act (FinCEN CTRs / SARs from
   "gambling businesses") all apply on top of state law.

**Practical guidance:** pick the most-restrictive state among
{operator, server, customer} and design for that. Do not assume
server location alone answers the question. State jurisdiction applies
to each of operator, server, and customer.

### Federal statutory references

- **[UIGEA, 31 USC §§ 5361-5367](https://www.law.cornell.edu/uscode/text/31/5361)**
  — Unlawful Internet Gambling Enforcement Act of 2006.
- **[Federal Wire Act, 18 USC § 1084](https://en.wikipedia.org/wiki/Federal_Wire_Act)**
  — transmission of wagering information. Per First Circuit + R.I.
  District Court rulings, applies to sports betting only (DOJ 2018
  OLC opinion disputes).
- **[Bank Secrecy Act of 1970](https://en.wikipedia.org/wiki/Bank_Secrecy_Act)**
  — anti-money-laundering / CTR / SAR obligations; FinCEN has
  separate regulations for "gambling businesses."

See `TODO.md` § "Compliance, AML, Responsible Gambling & Data
Protection (Reference)" for the full reference list.

## Quick start

```bash
pip install -e .

# 1. Door-mode: run as a BBS module
bbsengine6    # start the BBS
# log in, choose Casino from the BBS menu

# 2. Or run casino standalone (default: bed WebSocket client)
python -m casino
# or against a non-default daemon:
python -m casino --bed-host H --bed-port P

# 3. Or run the WebSocket server (bed will load MessageRouter)
pip install -e . -e ../bbsengine6/py -e ../bed -e ../zoid6/src
zoid6 --config /etc/zoid6/bed.json   # casino block is enabled by default

# 4. Or run the door-mode CLI (talks to local Postgres directly)
python -m casino --direct
# or with overridden DB args:
python -m casino --direct --databasename foo

# 5. Legacy direct entry points (still work)
python -m casino.client_cli

# 6. Door-mode blackjack (equivalent to `bin/blackjack`)
python -m casino blackjack
```

## Games

| Game         | Module               | Wire protocol                                |
|--------------|----------------------|----------------------------------------------|
| Blackjack    | `casino.blackjack`   | `casino.tictactoe.protocol` … (shared base)  |
| Poker        | `casino.poker`       | `poker_*` (12 message types)                 |
| Slots        | `casino.slots`       | `slot_spin`, `slot_result`, …                |
| Yahtzee      | `casino.yahtzee`     | per-game protocol (see `yahtzee/README.md`)  |
| Tic-tac-toe  | `casino.tictactoe`   | per-game protocol (see `tictactoe/README.md`)|

Poker variants are pluggable via setuptools entry points under the
`casino.poker.variants` group:

- `texas_hold_em` (Texas Hold'em)
- `omaha` (Omaha)
- `omaha_hi_lo` (Omaha Hi-Lo)
- `seven_card_stud` (7-Card Stud)

Each game ships a `README.md` with its wire protocol:

- `src/casino/tictactoe/README.md`
- `src/casino/yahtzee/README.md`
- `src/casino/slots/README.md` (Stigg's cleopatra notes)

## What's in this repo

```
casino/
├── pyproject.toml                Python manifest (console scripts + 4 poker variants)
├── src/casino/                   The installable package
│   ├── __main__.py               `python -m casino` entry
│   ├── main.py                   Door-mode menu
│   ├── auth.py                   BED auth + BBS entry points
│   ├── lib.py                    Card / Hand / Shoe / Casino / CasinoPlayer + bottombar
│   ├── config.py                 Env-var config loader
│   ├── _routing.py               bed / direct backend selector
│   ├── client_cli.py             legacy `python -m casino.client_cli` entry
│   ├── startup/                  Casino-specific bootstrap subpackage
│   │   ├── __init__.py           Re-exports `init`/`access`/`buildargs`/`main` + checkcasino
│   │   ├── main.py               citext install → checkcasino → schema.sql → manage_schema_priv grants → class imports
│   │   └── checkcasino.py        Ensures `casino` schema is owned by `zoid6`; verifies the 5 SECURITY DEFINER helper owners
│   ├── api/
│   │   ├── handler.py            MessageRouter + CasinoSessionManager + all services
│   │   └── messages.py           WebSocket MessageType enum + dataclasses
│   ├── blackjack/                Door-mode blackjack
│   ├── cards/                    Card dataclass + png resource loader
│   ├── client/                   Long-lived WebSocket client (CasinoClient)
│   ├── commands/                 BBS CLI subcommands (admin, bank, chat, game, poker, table)
│   ├── dal/                      Sync + aiosql DAL (bet, game, player, slots, table)
│   ├── games/base.py             GameType / GameAction enums + BaseGame ABC
│   ├── poker/                    Hand-rank, betting, evaluator, 4 variants
│   ├── services/                 bank, game (blackjack), player, poker, slots, table
│   ├── slots/                    Slots door + dealer + game + lib + play + player
│   ├── sql/                      ~30 schema files
│   ├── tests/                    ~50 pytest modules
│   ├── tictactoe/                Tic-tac-toe door + api + dealer + lib + service
│   ├── yahtzee/                  Yahtzee door + api + dealer + lib + service
│   └── maint/                    Sysop maintenance menu
├── scripts/                      opencode.sql, poker.sql, setup_privileges.sql, tictactoe.sql
├── bin/                          casino, blackjack shims
├── www/                          Per-host landing page (Smarty)
│   ├── php/index.php
│   ├── skin/{scss,tmpl}/
│   └── Makefile                  deploy-www target
├── ascii-playing-cards.txt       1998 ejm98 ASCII card art
├── Makefile                      Build / release / deploy-www
└── TODO.md  TODO_CLIENT.md  SPEC.md  CHANGELOG.md  README.md
```

## Dependencies

- Python 3.9+
- `bbsengine6` (engine + TUI primitives + DB)
- PostgreSQL 13+

## Tests

```bash
cd casino
PYTHONPATH=src pytest src/casino/tests
```

~50 pytest modules covering unit + integration. Integration tests
require a running BED server and are marked with the `integration`
marker.

## License

GPL-2.0-or-later.
